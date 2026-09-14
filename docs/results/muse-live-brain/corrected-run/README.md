# Corrected OpenCode run

**One prompt; 1/5 → 5/5 external tests; no task violation.** The attempt succeeded
and the orchestrator paused at the requested one-attempt boundary. `paused` in
the exported run status does not mean that the coding attempt was interrupted.

- Backend: OpenCode **1.18.27**.
- Model: `opencode/muse-spark-1.3-contributor-free`; no fallback.
- Clean source: `160ca8ba043a15123a5702fa01705c1db1a3b632`.
- Choice: **Fix**, left DNp20 **28 Hz**, right **32 Hz**, gate **14 spikes**.
- Observation: **500 simulated ms**, 50 measured bins, **392,732 spikes**.
- Feedback: positive, **200 simulated ms**, 20 bins, **199,794 spikes**.
- Stored allocation: **1/2** consumed; combined acceptance **2/3** consumed,
  including the earlier permission trial.

[Human-readable export](pilot.md) · [Structured export](pilot.json) ·
[Independent activity and budget checks](acceptance-check.json) ·
[Exact input and feedback images](inputs/)

The export removes session IDs and raw events. PNG file hashes were checked
before copying; only their exported relative filenames were adjusted. This is
a single bounded acceptance task, not a learning or generalization benchmark.
