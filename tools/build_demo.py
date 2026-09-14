"""Build the read-only demo from an explicitly supplied genuine public snapshot.

Usage: python tools/build_demo.py SOURCE_PUBLIC --translations CURATED_JSON
Never imports the pilot or runner. Original-language messages remain untouched.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil


def sha(data):
    return hashlib.sha256(data).hexdigest()


def event_sha(event):
    return sha(json.dumps(event, sort_keys=True, ensure_ascii=True).encode())


def build(source, translations, destination):
    raw = (source / "snapshot.json").read_bytes()
    snapshot = json.loads(raw)
    if snapshot["evidence"] != "genuine" or snapshot["status"] != "completed":
        raise ValueError("Demo requires a completed genuine snapshot")
    curated = json.loads(translations.read_text())
    messages = {e["item"]["text"] for a in snapshot["attempts"].values()
                for t in a["turns"] for e in t["events"]
                if e.get("item", {}).get("type") == "agent_message"}
    for entry in curated:
        if entry["original"] not in messages or sha(entry["original"].encode()) != entry["source_sha256"]:
            raise ValueError("Translation must match a genuine message and hash")
    result = {k: copy.deepcopy(snapshot[k]) for k in
              ("version", "evidence", "status", "busy", "budget", "active_attempt")}
    result["settings"] = {k: copy.deepcopy(snapshot["settings"][k]) for k in
                          ("model", "source_revision", "source_dirty", "decision_ms", "feedback_ms", "threshold_hz", "data")}
    result["presentation"] = {"mode": "demo", "label": "Bundled genuine pilot", "source_snapshot_sha256": sha(raw)}
    result["attempts"] = {}
    images = {}
    destination.mkdir(parents=True, exist_ok=True)
    for name, attempt in snapshot["attempts"].items():
        target = {k: copy.deepcopy(v) for k, v in attempt.items()
                  if k in {"id", "condition", "status", "phase", "baseline", "memory_start", "seed"}}
        target["turns"] = []
        for turn in attempt["turns"]:
            record = {k: copy.deepcopy(v) for k, v in turn.items() if k in {
                "step", "choice", "prompt", "evaluation", "feedback", "input", "feedback_input",
                "weights_before", "weights_after_choice", "weights_after_feedback"}}
            record["reserved"] = bool(turn.get("send_id"))
            record["codex"] = {k: v for k, v in turn["codex"].items() if k in {"status", "error", "usage"}}
            record["events"] = []
            for event in turn["events"]:
                item = event.get("item", {})
                keep = event["type"] in {"turn.started", "turn.completed"}
                keep |= event["type"] == "item.completed" and (
                    item.get("type") == "agent_message"
                    or item.get("type") == "command_execution" and "-m unittest" in item.get("command", "")
                    or item.get("type") == "file_change" and all(Path(c["path"]).name == "discount.py" for c in item.get("changes", [])))
                if not keep:
                    continue
                projected = copy.deepcopy(event)
                if item.get("type") == "file_change":
                    for change in projected["item"]["changes"]:
                        change["path"] = Path(change["path"]).name
                # Preserve text and outputs exactly, except explicit workspace paths.
                workspace = f"/attempts/{name}/workspace/"
                for key in ("command", "aggregated_output"):
                    value = projected.get("item", {}).get(key)
                    if value and workspace in value:
                        import re
                        projected["item"][key] = re.sub(r"/(?:[^\s\"']+/)*attempts/" + re.escape(name) + r"/workspace/", "", value)
                projected["source_sha256"] = event_sha(event)
                record["events"].append(projected)
            for key in ("input", "feedback_input"):
                image = record[key]
                filename = image["file"]
                if Path(filename).name != filename:
                    raise ValueError("Image must be a direct child of the source")
                image_bytes = (source / filename).read_bytes()
                if sha(image_bytes) != image["png_sha256"]:
                    raise ValueError("Recorded image hash mismatch")
                images[filename] = sha(image_bytes)
                shutil.copyfile(source / filename, destination / filename)
            target["turns"].append(record)
        result["attempts"][name] = target
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if any(secret in encoded for secret in ("/Users/", "session_id", "thread_id", ".npz")):
        raise ValueError("Unexpected private metadata in demo")
    (destination / "snapshot.json").write_text(encoded)
    (destination / "translations.json").write_text(json.dumps(curated, indent=2, ensure_ascii=False) + "\n")
    provenance = {"source_revision": snapshot["settings"]["source_revision"], "source_snapshot_sha256": sha(raw),
                  "snapshot_sha256": sha(encoded.encode()), "images": images,
                  "event_hash_encoding": "SHA-256 of json.dumps(original_event, sort_keys=True, ensure_ascii=True)",
                  "selection": "Completed agent messages, unittest commands, discount.py file changes and turn boundaries.",
                  "sanitization": "Session IDs, reservation IDs, checkpoints, private metadata and unrelated events omitted. Workspace paths made relative. Original agent text retained.",
                  "translations": "Curated English presentation only; exact original message SHA-256 matches required."}
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "src/flycodex/web/demo")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Output must differ from source")
    build(args.source, args.translations, args.output)
