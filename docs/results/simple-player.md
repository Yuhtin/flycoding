# One-button player

The September 14 redesign replaces the default dashboard with a small player:
Play/Pause, the actual flybody specimen, a compact CNS view, the fly's selected
instruction in amber, and OpenCode's response in blue. Metrics, hashes, filters,
and diagnostic logs are absent from the initial screen. The full lab and live
observer remain available at `/observatory`.

This is a new presentation of the [successful Muse run](muse-live-brain/README.md),
not another coding experiment. Replay submits no prompts. The decision, model
messages, tool results, external evaluation, and neural bins all come from that
same preserved run. The player keeps a visible **Recorded run** label.

The fly's instruction appears only after the measured choice. Model output
follows its original timing; the external score is withheld until evaluation.
The brain overlay clears while OpenCode is working and after the recording
finishes. The fly's body motion remains procedural.

Play pauses and resumes the recording clock and body. The completed recording
can be replayed. Backend strings are rendered as text, with technical tool
details collapsed for readability.

[Player screenshot](simple-player-dashboard.png) ·
[Player video](../demo/simple-player.mp4)

The original Muse live capture, original Codex archive, neural anatomy, body
geometry, and source run directories remain preserved separately.

## Verification

The initial desktop view has **30 visible words**. Browser checks exercised
Play, Pause, resume, replay, late decision/result reveal, data retry, a missing
body asset, recovery after reload, and the retained advanced observer. No
JavaScript errors or POST requests occurred. A 390 px viewport has no horizontal
overflow; its body and CNS use separate space.

The final Python suite passed **134 tests**, with **2 optional checks skipped**.
The player state suite passed **6 tests**. Both scoped Luna reviews approved
the final implementation.

All **70 bins** match the preserved source arrays and timestamps: 392,732 choice
spikes and 199,794 feedback spikes. Compact serialization keeps the activity
payload at approximately 4.3 MB. All **71 tracked package files**, including the
new player and recording, were byte-exact in the wheel.

The video is a **49.8-second continuous screen recording**, including a brief
Pause/Play demonstration. The underlying recorded timeline lasts 43.696 seconds;
it plays at its original speed.

[Browser checks](simple-player-browser-check.json) ·
[Mobile screenshot](simple-player-mobile.png) ·
[Preserved source checks](simple-player-source-check.json) ·
[Release and media hashes](simple-player-release-check.json)
