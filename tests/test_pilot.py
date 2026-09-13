"""Synthetic integration only: no genuine Codex or neural computation."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

from flycodex.codex import CodexRunner
from flycodex import pilot as pilot_module
from flycodex.pilot import Pilot, verify_data, write_report
from flycodex.storage import RunStore, atomic_save_json
from flycodex.task import DiscountTask


class SyntheticPolicy:
    def __init__(self, data_dir, learning):
        self.learning = learning
        self.weight = 0
        self.clock = 0

    def choose(self, rgb):
        self.clock += 500
        return {"action": "fix", "reason": "synthetic_policy", "input_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(), "window_ms": 500, "memory": self.memory()}

    def feedback(self, rgb, signal):
        self.clock += 200
        if self.learning:
            self.weight += signal
        return {"signal": signal, "window_ms": 200, "stimulus_ms": 200 if signal else 0, "memory": self.memory()}

    def reset(self, keep_memory=False):
        self.clock = 0
        if not keep_memory:
            self.weight = 0

    def memory(self):
        return {"sha256": str(self.weight), "clock": self.clock, "weights_frozen": not self.learning}

    def save(self, path):
        Path(path).write_text(json.dumps([self.weight, self.clock]))

    def restore(self, path):
        self.weight, self.clock = json.loads(Path(path).read_text())


@pytest.fixture
def controlled_codex(tmp_path):
    executable = tmp_path / "synthetic-codex"
    executable.write_text(f"#!{sys.executable}\n" + r'''import json, pathlib, sys
if "--version" in sys.argv:
    print("synthetic-codex 1")
    raise SystemExit
workspace = pathlib.Path(sys.argv[sys.argv.index("-C") + 1])
prompt = sys.stdin.read()
with (workspace.parent / "submissions.jsonl").open("a") as f:
    f.write(json.dumps({"prompt": prompt, "argv": sys.argv, "before": (workspace / "discount.py").read_text()}) + "\n")
print(json.dumps({"type": "thread.started", "thread_id": "synthetic-" + workspace.parent.name}), flush=True)
if "fixture_failure" in str(workspace):
    print(json.dumps({"type": "error", "message": "synthetic infrastructure failure"}), flush=True)
    raise SystemExit(1)
if "fixture_noop" not in str(workspace):
    (workspace / "discount.py").write_text("def discounted_total(subtotal_cents, discount_percent):\n    return subtotal_cents * (100 - discount_percent) // 100\n")
if "fixture_violation" in str(workspace):
    (workspace / "test_discount.py").write_text("# modified by synthetic fixture\n")
print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "<script>window.injected = true</script> synthetic result"}}), flush=True)
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}), flush=True)
''')
    executable.chmod(0o755)
    return str(executable)


def synthetic_pilot(tmp_path, executable, **kwargs):
    return Pilot(tmp_path / "run", tmp_path / "unused-data", model="synthetic-model", evidence="synthetic", policy_factory=SyntheticPolicy, runner_factory=lambda workspace, model: CodexRunner(workspace, model=model, executable=executable), **kwargs)


def test_six_pristine_attempts_final_feedback_and_memory_retention(tmp_path, controlled_codex):
    result = synthetic_pilot(tmp_path, controlled_codex).run()
    assert result["status"] == "completed"
    assert result["evidence"] == "synthetic"
    attempts = result["attempts"]
    assert list(attempts) == ["adaptive-1", "frozen-1", "random-1", "adaptive-2", "frozen-2", "random-2"]
    assert result["budget"]["used"] == 6
    for name, attempt in attempts.items():
        assert attempt["status"] == "success"
        assert attempt["workspace"] == str((tmp_path / "run/attempts" / name / "workspace").resolve())
        assert attempt["baseline"]["passed"] == 1
        assert len(attempt["turns"]) == 1
        turn = attempt["turns"][0]
        assert turn["feedback"]["signal"] == 1
        assert turn["evaluation"]["passed"] == 5
        image = Image.open(tmp_path / "run" / "public" / turn["input"]["file"])
        assert image.size == (320, 180)
        assert hashlib.sha256(np.asarray(image).tobytes()).hexdigest() == turn["input"]["rgb_sha256"]
        if name.startswith("frozen"):
            assert turn["weights_before"]["sha256"] == turn["weights_after_choice"]["sha256"] == turn["weights_after_feedback"]["sha256"]
        if name.startswith("random"):
            assert turn["choice"]["reason"] == "seeded_uniform_random"
            assert turn["feedback"]["delivered_to_neural"] is False
            assert "total_spikes" not in turn["choice"]
    assert attempts["adaptive-1"]["memory_start"]["sha256"] == "0"
    assert attempts["adaptive-2"]["memory_start"]["sha256"] == "1"
    assert attempts["adaptive-2"]["memory_start"]["clock"] == 0
    public = json.loads((tmp_path / "run/public/snapshot.json").read_text())
    assert public["events"][-2]["item"]["text"].startswith("<script>")
    report = write_report(tmp_path / "run", tmp_path / "report")
    assert report["evidence"] == "synthetic"
    assert "events" not in report
    for name, attempt in report["attempts"].items():
        assert attempt["turns"][0]["feedback_input"] == result["attempts"][name]["turns"][0]["feedback_input"]


def test_report_exports_sanitized_run_recovery_error_without_completed_turns(tmp_path):
    run_dir = tmp_path / "run"
    public = run_dir / "public"
    public.mkdir(parents=True)
    raw_error = f"Inspect {run_dir.resolve()}/journal.jsonl before recovery."
    atomic_save_json(public / "snapshot.json", {
        "evidence": "synthetic",
        "status": "recovery_error",
        "error": raw_error,
        "budget": {"used": 1},
        "settings": {
            "model": "synthetic-model",
            "codex_version": "synthetic executable fixture",
            "source_revision": "fixture-revision",
            "source_dirty": False,
        },
        "attempts": {
            "adaptive-1": {
                "status": "running",
                "condition": "adaptive",
                "turns": [],
            }
        },
    })

    report = write_report(run_dir, tmp_path / "report")

    assert report["error"] == "Inspect <run>/journal.jsonl before recovery."
    assert "Recovery error: Inspect <run>/journal.jsonl before recovery." in (tmp_path / "report/pilot.md").read_text()


def test_genuine_settings_reject_an_installed_package_before_data_or_codex(tmp_path, monkeypatch):
    installed_module = tmp_path / "site-packages/flycodex/pilot.py"
    installed_module.parent.mkdir(parents=True)
    installed_module.write_text("# wheel-installed module\n")
    monkeypatch.setattr(pilot_module, "__file__", str(installed_module))
    monkeypatch.setattr(pilot_module, "verify_data", lambda _: pytest.fail("graph data was loaded"))

    with pytest.raises(RuntimeError, match="editable Git checkout") as error:
        pilot_module._settings(tmp_path / "missing-data", "must-not-run", "genuine")

    assert "git clone https://github.com/Yuhtin/flycodex" in str(error.value)


def test_noop_exhausts_equal_budgets_and_reuses_only_own_session(tmp_path, controlled_codex):
    root = tmp_path / "fixture_noop"
    result = synthetic_pilot(root, controlled_codex).run()
    assert result["budget"]["used"] == 30
    assert result["budget"]["conditions"] == {"adaptive": 10, "frozen": 10, "random": 10}
    for name, attempt in result["attempts"].items():
        assert attempt["status"] == "budget_exhausted"
        assert len(attempt["turns"]) == 5
        assert all(t["feedback"]["signal"] == 0 for t in attempt["turns"])
        sends = [json.loads(line) for line in (root / "run/attempts" / name / "submissions.jsonl").read_text().splitlines()]
        assert "resume" not in sends[0]["argv"]
        assert all("synthetic-" + name in send["argv"] for send in sends[1:])
    assert synthetic_pilot(root, controlled_codex).run()["budget"]["used"] == 30


def test_execution_failure_has_no_task_feedback(tmp_path, controlled_codex):
    result = synthetic_pilot(tmp_path / "fixture_failure", controlled_codex).run()
    assert result["budget"]["used"] == 6
    for attempt in result["attempts"].values():
        assert attempt["status"] == "execution_failure"
        assert "feedback" not in attempt["turns"][0]


def test_violation_disqualifies_success_but_delivers_delta_once(tmp_path, controlled_codex):
    result = synthetic_pilot(tmp_path / "fixture_violation", controlled_codex).run()
    for attempt in result["attempts"].values():
        assert attempt["status"] == "violation"
        assert attempt["turns"][0]["feedback"]["signal"] == 1


def test_clean_stop_resumes_at_next_attempt_without_duplicate_sends(tmp_path, controlled_codex):
    first = synthetic_pilot(tmp_path, controlled_codex).run(stop_after_attempts=1)
    assert first["status"] == "paused"
    assert first["budget"]["used"] == 1
    result = synthetic_pilot(tmp_path, controlled_codex).run()
    assert result["budget"]["used"] == 6


def test_interrupt_after_feedback_aborts_resume_without_duplicate_feedback_or_send(tmp_path, controlled_codex):
    class InterruptedPolicy(SyntheticPolicy):
        def feedback(self, rgb, signal):
            super().feedback(rgb, signal)
            raise KeyboardInterrupt
    pilot = synthetic_pilot(tmp_path, controlled_codex)
    pilot.policy_factory = InterruptedPolicy
    with pytest.raises(KeyboardInterrupt):
        pilot.run()
    resumed = synthetic_pilot(tmp_path, controlled_codex).run()
    assert resumed["status"] == "completed"
    assert resumed["attempts"]["adaptive-1"]["status"] == "aborted_interrupted"
    assert resumed["budget"]["used"] == 6
    with RunStore(tmp_path / "run") as store:
        assert len(store.snapshot()["reservations"]) == 6


def test_evaluator_infrastructure_failure_never_becomes_negative_reward(tmp_path, controlled_codex):
    class BrokenEvaluation(DiscountTask):
        def evaluate(self):
            if (self.root / "submissions.jsonl").exists():
                raise RuntimeError("synthetic evaluator unavailable")
            return super().evaluate()
    result = synthetic_pilot(tmp_path, controlled_codex, task_factory=BrokenEvaluation).run()
    for attempt in result["attempts"].values():
        assert attempt["status"] == "infrastructure_failure"
        assert "feedback" not in attempt["turns"][0]


def test_missing_data_refused_before_budget_reservation(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        Pilot(tmp_path / "run", tmp_path / "missing", model="model").run()
    assert not (tmp_path / "run/state.json").exists()


def test_annotation_identity_is_checked_before_graph(tmp_path, monkeypatch):
    from flycodex.neural import policy
    (tmp_path / "annotations.feather").write_bytes(b"tampered")
    monkeypatch.setattr(policy, "_verify_graph", lambda path: None)
    with pytest.raises(ValueError, match="annotations"):
        verify_data(tmp_path)


def test_hard_crash_refuses_recovery_without_process_quiescence(tmp_path, controlled_codex):
    synthetic_pilot(tmp_path, controlled_codex).run(stop_after_attempts=1)
    path = tmp_path / "run/controller.json"
    state = json.loads(path.read_text())
    state["attempts"]["adaptive-1"].update(status="running", phase="send_start")
    path.write_text(json.dumps(state))
    result = synthetic_pilot(tmp_path, controlled_codex).run()
    assert result["status"] == "recovery_error"
    assert result["budget"]["used"] == 1


def test_missing_committed_adaptive_checkpoint_halts_remaining_pilot(tmp_path, controlled_codex):
    first = synthetic_pilot(tmp_path, controlled_codex).run(stop_after_attempts=3)
    (tmp_path / "run" / first["adaptive_checkpoint"]["file"]).unlink()
    result = synthetic_pilot(tmp_path, controlled_codex).run()
    assert result["status"] == "recovery_error"
    assert result["budget"]["used"] == 3
    assert "random-2" not in result["attempts"]


def test_frozen_choice_weight_drift_stops_before_send(tmp_path, controlled_codex):
    class DriftingPolicy(SyntheticPolicy):
        def choose(self, rgb):
            result = super().choose(rgb)
            if not self.learning:
                self.weight += 1
            return result
    pilot = synthetic_pilot(tmp_path, controlled_codex)
    pilot.policy_factory = DriftingPolicy
    result = pilot.run()
    for name in ("frozen-1", "frozen-2"):
        assert result["attempts"][name]["status"] == "infrastructure_failure"
        assert "send_id" not in result["attempts"][name]["turns"][0]
    assert result["budget"]["used"] == 4


def test_synthetic_override_cannot_claim_genuine_evidence(tmp_path):
    with pytest.raises(ValueError, match="synthetic"):
        Pilot(tmp_path / "run", tmp_path / "data", model="model", policy_factory=SyntheticPolicy)


def test_history_preserves_each_turns_own_codex_response(tmp_path, controlled_codex):
    result = synthetic_pilot(tmp_path, controlled_codex).run()
    for name, attempt in result["attempts"].items():
        turn = attempt["turns"][0]
        assert turn["events"][0]["thread_id"] == "synthetic-" + name
        assert turn["events"][-1]["type"] == "turn.completed"
        assert turn["events"][1]["item"]["text"].startswith("<script>")
