# First OpenCode submission

This genuine submission was stopped after OpenCode rejected edits to the
intended `discount.py` target. It consumed one of the three authorized sends.
The model read the task and ran its existing tests; no successful repair or
external post-turn evaluation is claimed.

The neural policy selected Fix from 392,732 measured simulated spikes. The
permission adapter used the wrong path form for OpenCode's edit lookup.
The interrupted run and pending reservation remain preserved locally and
count toward the shared acceptance budget. A subsequent corrected run is
[reported separately](../corrected-run/README.md); this trial is not removed
from the total.

[Recorded report](pilot.md) · [Structured evidence](pilot.json)

OpenCode v1.18.27 requests worktree-relative paths for both
[edit](https://raw.githubusercontent.com/anomalyco/opencode/v1.18.27/packages/opencode/src/tool/edit.ts)
and [write](https://raw.githubusercontent.com/anomalyco/opencode/v1.18.27/packages/opencode/src/tool/write.ts).
The adapter correction allows the exact relative `discount.py` target after a
catch-all edit denial; the external-directory denial remains in force.
