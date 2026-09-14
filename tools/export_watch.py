#!/usr/bin/env python3
"""Export one preserved genuine Muse run for the read-only simple player.

The exporter consumes an explicit completed/paused run directory and writes a
small, deterministic pair of public JSON files. It never starts a backend.
Wall-clock timestamps from the run are retained as offsets from the first
recorded choice bin; the source simulation intervals remain in each bin.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any


MODEL = "opencode/muse-spark-1.3-contributor-free"
FINAL_HOLD_MS = 2_000
_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:Users|private|tmp|var|home)/[^\s\"'`<>]+")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _timestamp_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def _number(value: Any) -> int | float:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _sanitize_text(value: Any, workspace: str) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = text.replace(workspace, "<workspace>")
    text = _ABSOLUTE_PATH.sub("<path>", text)
    # Permission diagnostics include the complete resolved ruleset. Keep the
    # actual error while dropping that raw configuration metadata.
    marker = " Here are some of the relevant rules"
    if marker in text:
        text = text.split(marker, 1)[0].rstrip() + "."
    return text


def _event_text(event: dict[str, Any], workspace: str) -> tuple[str, str | None, str | None]:
    raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}
    part = raw.get("part") if isinstance(raw.get("part"), dict) else {}
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    kind = event.get("kind")
    if kind == "text":
        return _sanitize_text(part.get("text", ""), workspace), None, None
    if kind == "error":
        error = raw.get("error", event.get("error", "OpenCode error"))
        return _sanitize_text(error, workspace), None, "error"
    tool = part.get("tool") or raw.get("tool")
    status = state.get("status") or part.get("status")
    if status == "error" and state.get("error") is not None:
        text = _sanitize_text(state["error"], workspace)
    else:
        input_value = state.get("input", part.get("input"))
        output_value = state.get("output", part.get("output"))
        pieces = []
        if isinstance(input_value, dict):
            command = input_value.get("command")
            if command:
                pieces.append(_sanitize_text(command, workspace))
            elif input_value.get("filePath"):
                pieces.append(_sanitize_text(input_value["filePath"], workspace))
        elif input_value:
            pieces.append(_sanitize_text(input_value, workspace))
        if output_value:
            pieces.append(_sanitize_text(output_value, workspace))
        if not pieces and state.get("title"):
            pieces.append(_sanitize_text(state["title"], workspace))
        text = "\n\n".join(pieces) or str(tool or "tool event")
    return text, tool, status


def _project_events(source: Path, origin_ms: int, workspace: str) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (source / "journal.jsonl").read_text().splitlines() if line]
    events = []
    for row in rows:
        if row.get("event") != "execution_event":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        kind = payload.get("kind")
        if kind not in {"text", "tool", "error"}:
            continue
        text, tool, status = _event_text(payload, workspace)
        if not text:
            continue
        output_kind = "error" if kind == "tool" and status == "error" else kind
        item = {"at_ms": _timestamp_ms(row["timestamp"]) - origin_ms,
                "kind": "message" if output_kind == "text" else output_kind,
                "text": text}
        if tool:
            item["tool"] = str(tool)
        if status:
            item["status"] = str(status)
        events.append(item)
    return events


def _activity_bins(source: Path, origin_ms: int) -> tuple[str, list[dict[str, Any]]]:
    activity_dir = source / "public" / "activity"
    files = [activity_dir / "adaptive-1-1-choice.json", activity_dir / "adaptive-1-1-feedback.json"]
    bins = []
    order_hash = None
    for path in files:
        document = json.loads(path.read_text())
        order_hash = order_hash or document.get("neuron_order_sha256")
        for event in document["window"]["events"]:
            if event.get("type") != "bin":
                continue
            bins.append({
                "at_ms": int(event["recorded_at_ms"] - origin_ms),
                "phase": document["phase"],
                "t_start_ms": _number(event["start_ms"]),
                "t_end_ms": _number(event["end_ms"]),
                "indices": list(event["indices"]),
                "counts": list(event["counts"]),
                "total_spikes": int(event["total_spikes"]),
            })
    if not order_hash or len(bins) != 70:
        raise ValueError("preserved run must provide the measured 70 activity bins")
    if any(bins[i]["at_ms"] > bins[i + 1]["at_ms"] for i in range(len(bins) - 1)):
        raise ValueError("activity bins are not ordered by recorded wall time")
    return order_hash, bins


def export_watch(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    source = Path(source_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if source == output:
        raise ValueError("output must differ from the preserved run")
    snapshot_path = source / "public" / "snapshot.json"
    activity_dir = source / "public" / "activity"
    journal_path = source / "journal.jsonl"
    if not snapshot_path.is_file() or not journal_path.is_file() or not activity_dir.is_dir():
        raise FileNotFoundError("preserved run public snapshot, activity, and journal are required")
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    settings = snapshot.get("settings", {})
    if snapshot.get("evidence") != "genuine" or settings.get("backend") != "opencode":
        raise ValueError("watch export requires a genuine OpenCode run")
    if settings.get("model") != MODEL:
        raise ValueError("watch export requires the pinned contributor-free Muse model")
    attempts = snapshot.get("attempts", {})
    attempt = attempts.get("adaptive-1")
    if not isinstance(attempt, dict) or len(attempt.get("turns", [])) != 1:
        raise ValueError("watch export requires the single preserved adaptive turn")
    turn = attempt["turns"][0]
    choice_file = activity_dir / "adaptive-1-1-choice.json"
    choice_activity = json.loads(choice_file.read_text())
    choice_bins = [event for event in choice_activity["window"]["events"] if event.get("type") == "bin"]
    if not choice_bins:
        raise ValueError("choice activity has no recorded bins")
    origin_ms = int(choice_bins[0]["recorded_at_ms"])
    order_hash, bins = _activity_bins(source, origin_ms)
    feedback_file = activity_dir / "adaptive-1-1-feedback.json"
    workspace = str(attempt.get("workspace", ""))
    rows = [json.loads(line) for line in journal_path.read_text().splitlines() if line]
    by_event = {row.get("event"): row for row in rows}
    required = ("reserve_start", "turn_settled", "feedback_start", "turn_committed")
    if any(name not in by_event for name in required):
        raise ValueError("journal lacks required turn timeline boundaries")
    choice_end = _timestamp_ms(by_event["reserve_start"]["timestamp"]) - origin_ms
    execution_end = _timestamp_ms(by_event["turn_settled"]["timestamp"]) - origin_ms
    result_at = _timestamp_ms(by_event["feedback_start"]["timestamp"]) - origin_ms
    feedback_end = _timestamp_ms(by_event["turn_committed"]["timestamp"]) - origin_ms
    evaluation = turn.get("evaluation") or {}
    baseline = attempt.get("baseline") or {}
    run = {
        "version": 1,
        "title": "Recorded Muse correction",
        "backend": "opencode",
        "model": settings["model"],
        "source_revision": settings.get("source_revision", ""),
        "duration_ms": int(feedback_end + FINAL_HOLD_MS),
        "phases": {"choice_end_ms": int(choice_end), "execution_end_ms": int(execution_end), "feedback_end_ms": int(feedback_end)},
        "decision": {"at_ms": int(choice_end), "action": turn["choice"]["action"], "text": turn["prompt"]},
        "events": _project_events(source, origin_ms, workspace),
        "result": {"at_ms": int(result_at), "passed": int(evaluation["passed"]), "total": int(evaluation["total"]), "before": int(baseline["passed"])},
        "provenance": {
            "neuron_order_sha256": order_hash,
            "recording": "Genuine preserved OpenCode run with recorded neural activity",
            "source_snapshot_sha256": _sha256(snapshot_bytes),
            "source_activity_sha256": {
                "choice": _sha256(choice_file.read_bytes()),
                "feedback": _sha256(feedback_file.read_bytes()),
            },
            "sanitization": "Session IDs, local paths, raw event metadata, and bookkeeping omitted; model text and tool output retained.",
        },
    }
    activity = {"version": 1, "neuron_order_sha256": order_hash, "bins": bins}
    encoded_run = (json.dumps(run, indent=2, ensure_ascii=False) + "\n").encode()
    encoded_activity = (json.dumps(activity, indent=2, ensure_ascii=False) + "\n").encode()
    serialized = encoded_run.decode() + encoded_activity.decode()
    for secret in ("session_id", "sessionID", "send_id", "thread_id", "/Users/", "/private/"):
        if secret in serialized:
            raise ValueError(f"watch export contains private metadata: {secret}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "run.json").write_bytes(encoded_run)
    (output / "activity.json").write_bytes(encoded_activity)
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="preserved genuine run directory")
    parser.add_argument("--output", type=Path, default=Path("src/flycodex/web/watch"))
    args = parser.parse_args(argv)
    export_watch(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
