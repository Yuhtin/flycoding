# flycoding workstation

The September 14, 2026 presentation uses a full-screen pixelated 3D desk, an
actual flybody specimen, physical keyboard, and an OpenCode monitor. The selected
prompt stays in amber above the recorded model output. Play pauses, resumes, and
replays the same preserved run. The project is now **flycoding**, with the tagline
**The new era of vibe coding**.

The fly now faces the monitor, with its front claws over the keyboard. Alternating
leg lifts and synthesized mechanical key sounds share the replay clock. Mouse
clicks mark the decision and recorded terminal events. Play unlocks browser audio;
the compact **Sound on/off** control mutes it. Pause and hidden tabs silence audio.

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

The body motion and sound effects are procedural. It presents the actual flybody meshes and poses;
the connectome does not control the displayed legs. The brain chooses among three
fixed instructions; it does not compose natural-language prompts.

## Validation

- 136 Python tests passed; two environment-dependent tests skipped.
- Desktop 1440×900 and mobile 390×844 browser checks passed without JavaScript
  errors or non-GET requests. The monitor fits both viewports.
- Prompt timing, real metric values, 5/5 result, pause, replay reset, reduced
  motion, failed payload recovery, missing body recovery, and the advanced
  observatory passed.
- A separate renderer probe verified changing body poses during playback,
  stable poses while paused, and DOM cleanup on disposal.
- The flycoding wheel contains all 74 tracked package files, matching the source
  byte for byte, and includes both the new CLI and the legacy flycodex alias.
- The [source audit](workstation-source-check.json) verified unchanged historical
  run files and 24 protected assets, including the recorded payload, anatomy,
  body, and earlier captures. All 70 exported bins match the source values.
- The [sound and typing checks](workstation-sound-validation.json) verified no
  audio before Play, audible cue scheduling, pause, mute/unmute, and disposal.
  Front claws moved more than 0.2 world units during the sampled typing sequence
  and held their pose while paused. Desktop framing survived a mobile resize.
  The rendered audio contains 47 key/mouse cues without clipping.

The public video is a real-time browser capture of the recorded run. Its audio
track renders the same procedural cue plan through Web Audio offline, aligned to
the captured replay clock. The recorder preserves cumulative frame timestamps;
Play and completion transitions verify the captured duration. The mobile still
uses a browser clock jump through the same recording for visual inspection. Neither
is a fresh neural or coding experiment.
This redesign used **zero new model calls**. The live Muse source remains revision
`160ca8ba043a15123a5702fa01705c1db1a3b632`; the earlier acceptance consumed two of
three authorized prompt submissions.

The previous [simple player](simple-player.md) and its artifacts remain available.
