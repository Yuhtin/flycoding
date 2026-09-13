"""Serial six-attempt pilot; durable boundaries never replay sends or feedback."""
from __future__ import annotations

import gc
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess

import numpy as np

from .codex import CodexRunner, PROMPTS
from .neural import NeuralPolicy
from .panel import render_panel
from .storage import ATTEMPT_ORDER, ATTEMPT_CONDITIONS, RunStore, atomic_save_json, load_json
from .task import DiscountTask


class RecoveryError(RuntimeError):
    """Persisted state cannot safely support another attempt."""


_EDITABLE_CHECKOUT_MESSAGE = (
    "Genuine runs require an editable Git checkout of Flycodex whose Git root "
    "owns src/flycodex/pilot.py. Install it with: git clone "
    "https://github.com/Yuhtin/flycodex && cd flycodex && uv sync"
)


def verify_data(data_dir: Path) -> dict:
    """Read-only verification of every dataset input used by the runtime."""
    from .neural import policy
    root = Path(data_dir)
    for name, expected in policy._locks().items():
        source = root / name
        if not source.is_file():
            raise FileNotFoundError(f"Prepared source required: {source}")
        if source.stat().st_size != expected["bytes"] or policy._sha256(source) != expected["sha256"]:
            raise ValueError(f"Source provenance mismatch: {name}")
    policy._verify_graph(root)
    return {"verified": True, "graph_sha256": policy._sha256(root / "graph.npz"),
            "sources": policy._locks(), "upstream_revision": policy.UPSTREAM_REVISION}


def _command_output(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=30).stdout.strip()


def _source_checkout(source_file: Path | None = None) -> Path:
    """Return the editable checkout that owns this module or reject the install."""
    module = Path(source_file or __file__).resolve()
    try:
        candidate = module.parents[2]
    except IndexError as exc:
        raise RuntimeError(_EDITABLE_CHECKOUT_MESSAGE) from exc
    try:
        root = Path(_command_output(["git", "-C", str(candidate), "rev-parse", "--show-toplevel"])).resolve()
        tracked = _command_output([
            "git", "-C", str(root), "ls-files", "--error-unmatch", "--", "src/flycodex/pilot.py",
        ])
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(_EDITABLE_CHECKOUT_MESSAGE) from exc
    if root != candidate or tracked != "src/flycodex/pilot.py" or (root / tracked).resolve() != module:
        raise RuntimeError(_EDITABLE_CHECKOUT_MESSAGE)
    return root


def _settings(data_dir, model, evidence):
    if not model:
        raise ValueError("An explicit Codex model is required")
    if evidence == "genuine":
        if not shutil.which("git"):
            raise RuntimeError("Required executable missing: git")
        source = _source_checkout()
        data = verify_data(data_dir)
        for executable in ("codex", "rtk", "python", "c++"):
            if not shutil.which(executable):
                raise RuntimeError(f"Required executable missing: {executable}")
        version = _command_output(["codex", "--version"])
    else:
        data, version = {"verified": False, "label": "synthetic fixture"}, "synthetic executable fixture"
        source = Path(__file__).resolve().parents[2]
    revision = _command_output(["git", "-C", str(source), "rev-parse", "HEAD"])
    dirty = bool(_command_output(["git", "-C", str(source), "status", "--porcelain"]))
    return {"model": model, "codex_version": version, "source_revision": revision,
            "source_dirty": dirty, "evidence": evidence, "data": data,
            "codex_flags": ["-a", "never", "exec", "--sandbox", "workspace-write", "--ignore-user-config", "--json", "--color", "never"],
            "turn_deadline_seconds": 300, "evaluation_deadline_seconds": 30,
            "decision_ms": 500, "feedback_ms": 200, "feedback_mV_equivalent": 20,
            "threshold_hz": 2, "random_seeds": {"random-1": 1729, "random-2": 1730}}


def _budget(store):
    records = list(store.snapshot()["reservations"].values())
    return {"used": len(records), "limit": 30, "remaining": 30 - len(records),
            "per_attempt_limit": 5, "per_condition_limit": 10,
            "conditions": {name: sum(r["condition"] == name for r in records) for name in ("adaptive", "frozen", "random")}}


class Pilot:
    def __init__(self, run_dir: Path, data_dir: Path, *, model: str,
                 evidence="genuine", policy_factory=None, runner_factory=None, task_factory=None):
        if evidence not in {"genuine", "synthetic"}:
            raise ValueError("Unknown evidence type")
        if evidence != "synthetic" and any((policy_factory, runner_factory, task_factory)):
            raise ValueError("Injected boundaries must be labeled synthetic")
        self.root = Path(run_dir).expanduser().resolve()
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.model, self.evidence = model, evidence
        self.policy_factory = policy_factory or NeuralPolicy
        self.runner_factory = runner_factory or (lambda workspace, model: CodexRunner(workspace, model=model))
        self.task_factory = task_factory or DiscountTask
        self.state = None

    def _persist(self, store, event, **fields):
        self.state["budget"] = _budget(store)
        atomic_save_json(self.root / "controller.json", self.state)
        store._append_event({"event": event, **fields})
        # A separate atomic, explicitly enumerated public artifact; no writer lock in HTTP.
        atomic_save_json(self.root / "public/snapshot.json", self.state)

    def _phase(self, store, attempt, phase):
        attempt["phase"] = phase
        self._persist(store, phase, attempt=attempt["id"])

    def _image(self, image, filename):
        public = self.root / "public"
        public.mkdir(parents=True, exist_ok=True)
        target = public / filename
        temporary = target.with_suffix(".partial")
        image.save(temporary, format="PNG")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(target)
        return {"file": filename, "rgb_sha256": hashlib.sha256(np.asarray(image).tobytes()).hexdigest(),
                "png_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    def run(self, *, stop_after_attempts=None):
        settings = _settings(self.data_dir, self.model, self.evidence)
        with RunStore(self.root) as store:
            if store.manifest_path.exists():
                original = load_json(store.manifest_path)["settings"]
                if original != settings:
                    raise ValueError("Run settings/provenance changed; existing run cannot be resumed")
            else:
                store.initialize(settings)
            if (self.root / "controller.json").exists():
                self.state = load_json(self.root / "controller.json")
            else:
                if store.snapshot()["reservations"]:
                    raise RuntimeError("Recovery error: reservations exist without controller state")
                self.state = {"version": 1, "evidence": self.evidence, "status": "running",
                              "settings": settings, "attempts": {}, "events": [], "adaptive_checkpoint": None}
            for attempt in self.state["attempts"].values():
                if attempt["status"] == "interrupted" and attempt.get("process_quiescent"):
                    attempt["status"] = "aborted_interrupted"
                    attempt["phase"] = "complete"
                    self._persist(store, "attempt_aborted_after_interrupt", attempt=attempt["id"])
                elif attempt["phase"] != "complete":
                    self.state["status"] = "recovery_error"
                    self.state["error"] = "Uncertain process or side-effect boundary; no automatic replay. Inspect journals before manual reconciliation."
                    self._persist(store, "recovery_refused", attempt=attempt["id"])
                    return self.state
            if self.state["status"] == "completed":
                return self.state
            self.state["status"] = "running"
            finished = 0
            for name in ATTEMPT_ORDER:
                if name in self.state["attempts"]:
                    continue
                attempt = {"id": name, "condition": ATTEMPT_CONDITIONS[name], "status": "running",
                           "phase": "reset_start", "turns": [], "session_id": None}
                self.state["attempts"][name] = attempt
                self.state["active_attempt"] = name
                self._persist(store, "reset_start", attempt=name)
                try:
                    self._attempt(store, attempt)
                except RecoveryError as exc:
                    self.state.update(status="recovery_error", error=str(exc))
                    attempt.update(status="recovery_error", error=str(exc))
                    self._persist(store, "recovery_refused", attempt=name)
                    return self.state
                except KeyboardInterrupt:
                    self.state["busy"] = False
                    # CodexRunner's BaseException cleanup reaps the owned process group.
                    attempt.update(status="interrupted", process_quiescent=True)
                    self.state["status"] = "interrupted"
                    self._persist(store, "interrupted", attempt=name)
                    raise
                except Exception as exc:
                    attempt.update(status="infrastructure_failure", error=f"{type(exc).__name__}: {exc}")
                    self._phase(store, attempt, "complete")
                finished += 1
                if stop_after_attempts and finished >= stop_after_attempts:
                    self.state["status"] = "paused"
                    self._persist(store, "paused")
                    return self.state
            self.state["status"] = "completed"
            self._persist(store, "pilot_completed")
            return self.state

    def _attempt(self, store, attempt):
        name, condition = attempt["id"], attempt["condition"]
        task = self.task_factory(self.root / "attempts" / name)
        attempt["workspace"] = str(task.workspace)
        policy = None
        try:
            task.reset()
            self._phase(store, attempt, "baseline_evaluation_start")
            before = task.evaluate()
            attempt["baseline"] = before
            if before["violation"]:
                raise RuntimeError("Pristine task has a scope violation")
            if condition != "random":
                policy = self.policy_factory(self.data_dir, learning=condition == "adaptive")
                prior = self.state["adaptive_checkpoint"] if condition == "adaptive" else None
                if prior:
                    checkpoint = self.root / prior["file"]
                    if not checkpoint.exists() or hashlib.sha256(checkpoint.read_bytes()).hexdigest() != prior["sha256"]:
                        raise RecoveryError("Recovery error: committed adaptive checkpoint missing or changed")
                    try:
                        policy.restore(checkpoint)
                    except (OSError, ValueError) as exc:
                        raise RecoveryError(f"Adaptive checkpoint incompatible: {exc}") from exc
                    policy.reset(keep_memory=True)
                else:
                    policy.reset()
                initial = task.root / "initial.npz"
                self._phase(store, attempt, "initial_checkpoint_start")
                policy.save(initial)  # also materializes the lazy graph before baseline weights.
                attempt["memory_start"] = policy.memory()
            else:
                attempt["seed"] = self.state["settings"]["random_seeds"][name]
                rng = random.Random(attempt["seed"])
            runner = self.runner_factory(task.workspace, self.model)
            for step in range(1, 6):
                turn = {"step": step, "events": []}
                attempt["turns"].append(turn)
                self._phase(store, attempt, "input_start")
                observation = render_panel(before["passed"], before["total"])
                turn["input"] = self._image(observation, f"{name}-{step}-input.png")
                self._phase(store, attempt, "choice_start")
                if policy:
                    turn["weights_before"] = policy.memory()
                    choice = policy.choose(np.asarray(observation))
                    turn["weights_after_choice"] = policy.memory()
                    if choice["input_sha256"] != turn["input"]["rgb_sha256"]:
                        raise RuntimeError("Neural input hash mismatch")
                    self._check_frozen(condition, turn["weights_before"], turn["weights_after_choice"])
                else:
                    choice = {"action": rng.choice(list(PROMPTS)), "reason": "seeded_uniform_random", "seed": attempt["seed"]}
                turn["choice"] = choice
                turn["prompt"] = PROMPTS[choice["action"]]
                self._phase(store, attempt, "reserve_start")
                send_id = store.reserve(name)
                turn["send_id"] = send_id
                self._phase(store, attempt, "send_start")
                self.state["busy"] = True
                self._persist(store, "codex_busy", attempt=name)
                def on_event(event):
                    turn["events"].append(event)
                    turn["events"] = turn["events"][-200:]
                    self.state["events"].append(event)
                    self.state["events"] = self.state["events"][-200:]
                    self._persist(store, "codex_event", attempt=name, send_id=send_id, payload=event)
                outcome = runner.run(turn["prompt"], attempt["session_id"], on_event)
                self.state["busy"] = False
                turn["codex"] = outcome
                attempt["session_id"] = outcome["session_id"]
                self._phase(store, attempt, "turn_settled")
                if outcome["status"] != "completed":
                    attempt["status"] = "execution_failure"
                    self._phase(store, attempt, "reservation_completion_start")
                    store.complete(send_id, turn)
                    break
                self._phase(store, attempt, "external_evaluation_start")
                try:
                    evaluation = task.evaluate()
                except RuntimeError as exc:
                    turn["infrastructure_error"] = str(exc)
                    attempt["status"] = "infrastructure_failure"
                    self._phase(store, attempt, "reservation_completion_start")
                    store.complete(send_id, turn)
                    break
                turn["evaluation"] = evaluation
                delta = evaluation["passed"] - before["passed"]
                signal = (delta > 0) - (delta < 0)
                self._phase(store, attempt, "feedback_start")
                feedback_image = render_panel(evaluation["passed"], evaluation["total"])
                turn["feedback_input"] = self._image(feedback_image, f"{name}-{step}-feedback.png")
                if policy:
                    turn["feedback"] = {**policy.feedback(np.asarray(feedback_image), signal), "delivered_to_neural": True}
                    turn["weights_after_feedback"] = policy.memory()
                    self._check_frozen(condition, turn["weights_after_choice"], turn["weights_after_feedback"])
                    self._phase(store, attempt, "checkpoint_start")
                    checkpoint = task.root / f"step-{step}.npz"
                    policy.save(checkpoint)
                    turn["checkpoint"] = {"file": str(checkpoint.relative_to(self.root)), "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
                else:
                    turn["feedback"] = {"signal": signal, "delivered_to_neural": False, "reason": "random_control"}
                self._phase(store, attempt, "reservation_completion_start")
                store.complete(send_id, turn)
                # Pointer changes only after the turn's feedback and checkpoint are demonstrably committed.
                if condition == "adaptive":
                    self.state["adaptive_checkpoint"] = turn["checkpoint"]
                self._phase(store, attempt, "turn_committed")
                before = evaluation
                if evaluation["violation"]:
                    attempt["status"] = "violation"
                    break
                if evaluation["passed"] == evaluation["total"]:
                    attempt["status"] = "success"
                    break
            else:
                attempt["status"] = "budget_exhausted"
            self._phase(store, attempt, "complete")
        finally:
            # Drop the only loaded graph before constructing the next condition.
            policy = None
            gc.collect()

    @staticmethod
    def _check_frozen(condition, before, after):
        if condition == "frozen" and before["sha256"] != after["sha256"]:
            raise RuntimeError("Frozen weights changed")


def write_report(run_dir: Path, output_dir: Path) -> dict:
    """Export a compact report without model event text, session IDs or local paths."""
    state = load_json(Path(run_dir) / "public/snapshot.json")
    settings = state["settings"]
    report = {"evidence": state["evidence"], "status": state["status"], "budget": state["budget"],
              "model": settings["model"], "codex_version": settings["codex_version"],
              "source_revision": settings["source_revision"], "source_dirty": settings["source_dirty"],
              "attempts": {}, "limitations": "Six attempts measure mechanism operation only; they do not demonstrate task learning, generalization, statistical significance, language ability or cognition."}
    if state.get("error"):
        report["error"] = state["error"]
    for name in ATTEMPT_ORDER:
        if name not in state["attempts"]:
            continue
        attempt = state["attempts"][name]
        report["attempts"][name] = {"status": attempt["status"], "condition": attempt["condition"],
                                    "seed": attempt.get("seed"), "baseline": attempt.get("baseline"),
                                    "error": attempt.get("error"), "turns": []}
        for turn in attempt["turns"]:
            report["attempts"][name]["turns"].append({key: turn[key] for key in (
                "step", "send_id", "input", "feedback_input", "choice", "prompt", "evaluation", "feedback", "infrastructure_error",
                "weights_before", "weights_after_choice", "weights_after_feedback") if key in turn})
            if "codex" in turn:
                report["attempts"][name]["turns"][-1]["execution"] = {key: turn["codex"].get(key) for key in ("status", "error", "usage")}
    # Remove machine-local root paths from diagnostic strings; raw events are never exported.
    serialized = json.dumps(report).replace(str(Path(run_dir).resolve()), "<run>").replace(str(Path.home()), "<home>")
    report = json.loads(serialized)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    atomic_save_json(output / "pilot.json", report)
    lines = ["# Flycodex pilot", "", f"Evidence: **{report['evidence']}**. Status: **{report['status']}**.",
             f"Model: `{report['model']}`. Reserved sends: {report['budget']['used']}/30."]
    if report.get("error"):
        lines.extend(["", f"Recovery error: {report['error']}"])
    lines.extend(["", "| Attempt | Result | Instructions | Final passing tests |", "| --- | --- | ---: | ---: |"])
    for name, attempt in report["attempts"].items():
        evaluated = [t["evaluation"] for t in attempt["turns"] if "evaluation" in t]
        score = evaluated[-1]["passed"] if evaluated else "—"
        lines.append(f"| {name} | {attempt['status']} | {sum('send_id' in t for t in attempt['turns'])} | {score} |")
    lines.extend(["", report["limitations"], "", "Detailed traces: [pilot.json](pilot.json). Raw local events and checkpoints remain in the run directory.", ""])
    (output / "pilot.md").write_text("\n".join(lines))
    return report
