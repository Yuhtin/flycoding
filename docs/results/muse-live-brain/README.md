# Muse Spark live acceptance

On September 14, 2026, a measured neural choice drove an actual OpenCode
submission using `opencode/muse-spark-1.3-contributor-free` on CLI **1.18.27**.
The corrected attempt went from **1/5 to 5/5 external tests** with one prompt.
The complete acceptance used **two of three authorized prompt submissions**;
the third was not used. No new Codex prompts were sent.

| Run | Prompt submissions | Outcome |
| --- | ---: | --- |
| [Permission trial](permission-trial/README.md) | 1 | Interrupted after the adapter denied the intended edit; no repair result claimed. |
| [Corrected run](corrected-run/README.md) | 1 | Fix selected; backend completed; 5/5 external tests, no violation. |
| Total | **2 / 3 authorized** | Stopped after the successful attempt. |

The second run's stored cap is 2 because it received only the unused allocation.
Its dashboard shows 1/2 for that run. The first interrupted reservation remains
consumed in the shared local ledger; creating a second source-bound run did not
reset the authorization. A prompt submission can contain several model/tool
steps, so these figures are not counts of provider inference requests.

The network received task-state pixels and selected the fixed English prompt
“Fix the discount function while preserving the tests.” Muse performed the
coding. The 50 choice bins contain **392,732 simulated spikes**; the 20 positive
feedback bins contain **199,794**. Every bin's sparse counts sum to its recorded
total, and each window sums to its ordinary aggregate.

The resting fly uses actual flybody geometry and procedural movement. The CNS
uses source soma coordinates with measured simulated firing. Neither the body
animation nor this single task establishes learned locomotion, language
understanding, or task learning.

- [Continuous live capture](../../demo/live-brain-opencode.mp4)
- [English post draft](../../demo/live-brain-tweet.txt)
- [Release verification](../live-brain-release.md)

The video removes only waiting time before and after the recorded interaction;
its retained interval plays continuously at normal speed. The capture predates
the final connection-label correction: its top bar can still say “Waiting for a
coding run” while the main status, measured windows, and terminal show the run.
The final panel corrects that label. Raw recordings, session IDs, events,
checkpoints, and the cross-run budget ledger remain local.
