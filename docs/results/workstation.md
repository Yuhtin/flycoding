# flycoding workstation

The September 14, 2026 presentation uses a full-screen pixelated 3D desk, an
actual flybody specimen, physical keyboard, and an OpenCode monitor. The selected
prompt stays in amber above the recorded model output. Play pauses, resumes, and
replays the same preserved run. The project is now **flycoding**, with the tagline
**The new era of vibe coding**.

[Video](../demo/workstation.mp4) · [Desktop](workstation-dashboard.png) ·
[Mobile](workstation-mobile.png) · [Validation](workstation-validation.json)

## What the HUD measures

The total is **166,700 retained neurons**. Active neurons count positive entries
in the latest revealed bin. Spikes per second divide that bin's total by its
simulated duration in seconds; these are not wall-clock rates. The last choice
bin has **6,579 active neurons and 890,100 simulated spikes/s**.

The 96-cell raster uses a deterministic subset of measured neuron indices. Each
column represents one recorded neural bin, and future columns remain blank.
Choice and feedback contain 50 and 20 bins respectively. The raster omits the
coding wait, so it is a sequence of simulation bins rather than a continuous
wall-clock chart. Paused, Waiting, and Complete labels identify held measurements.

The body motion is procedural. It presents the actual flybody meshes and poses;
the connectome does not control the displayed legs. The brain chooses among three
fixed instructions; it does not compose natural-language prompts.

## Validation

- 135 Python tests passed; two environment-dependent tests skipped.
- Desktop 1440×900 and mobile 390×844 browser checks passed without JavaScript
  errors or non-GET requests. The monitor fits both viewports.
- Prompt timing, real metric values, 5/5 result, pause, replay reset, reduced
  motion, failed payload recovery, missing body recovery, and the advanced
  observatory passed.
- A separate renderer probe verified changing body poses during playback,
  stable poses while paused, and DOM cleanup on disposal.
- The flycoding wheel contains all 73 tracked package files, matching the source
  byte for byte, and includes both the new CLI and the legacy flycodex alias.
- The [source audit](workstation-source-check.json) verified unchanged historical
  run files and 24 protected assets, including the recorded payload, anatomy,
  body, and earlier captures. All 70 exported bins match the source values.

The public video is a real-time browser capture of the recorded run, including
one pause/resume check. The mobile still uses the same recording with a browser
clock jump for visual inspection. Neither is a fresh neural or coding experiment.
This redesign used **zero new model calls**. The live Muse source remains revision
`160ca8ba043a15123a5702fa01705c1db1a3b632`; the earlier acceptance consumed two of
three authorized prompt submissions.

The previous [simple player](simple-player.md) and its artifacts remain available.
