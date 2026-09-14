# Measured results

These files record the genuine pilot and neural mechanism checks performed on
September 13, 2026, on a 16 GiB ARM64 Mac. The English flybody presentation was
added afterward; it does not change those measurements.

## Codex pilot

All six attempts succeeded, using nine reservations, all completed. Each
attempt started with 1/5 tests passing and finished at 5/5 with no violation.
The adaptive condition used two calls, frozen weights used two, and uniform
random choice used five. Every neural attempt chose Fix immediately. Random
attempts followed Test → Investigate → Fix and Investigate → Fix.

Adaptive memory persisted between attempts and frozen weights remained
identical. Adaptation showed no advantage over the frozen control. Weight
changes alone do not demonstrate task learning.

- [verification.md](verification.md): verification of the original pilot release.
- [pilot.md](pilot.md): attempt outcomes.
- [pilot.json](pilot.json): choices, feedback, evaluations, usage, and hashes.
- [pilot-checks.json](pilot-checks.json): audit of nine reservations, six dedicated sessions, continuation, weights, and 18 images.
- [inputs/](inputs/): original observation and feedback PNGs. Both file and pixel hashes were verified; exported filenames refer to this directory.
- [dashboard.png](dashboard.png): dashboard presentation. The current screenshot may show the later flybody interface; the measurements retain their original source revision.
- [browser-check.json](browser-check.json): browser verification from the original release.

CLI records confirmed `gpt-6-astra`, approval `never`, and sandbox
`workspace-write` in dedicated workspaces. Every attempt used a different
session; turns within an attempt resumed its explicit ID. Full raw events,
session IDs, checkpoints, and volumetric data stay local. The viewing demo
includes only selected, sanitized events from these sessions.

Historical prompts and original agent messages remain in their recorded
language. English display translations are presentation aids, not replacement
source records.

## Source and numerical reference

The checks below sent no instructions to Codex.

[reference-check.json](reference-check.json) contains hashes for all three
source files and 11 compiled arrays. The retained graph has 166,700 neurons
and 25,582,938 edges, representing 124,177,617 synaptic contacts.

With uniform RGB 240 input, frozen weights, and 500 ms of simulated time, the
adaptation exactly reproduced the pinned original implementation's 388,867
spikes. The spike hash was
`776c33e872595a635845b0c3719c8343e425ee47ea968a242f2ba0cb79230704`.
This verifies one numerical trajectory; it does not validate the modeled
physiology or every possible trajectory.

## Input, feedback, and memory

[neural-probe.json](neural-probe.json) compares uniform images from the same
initial state. Each observation advances 500 ms of simulated time.

| Input | Left | Right | Gate | Choice |
| --- | ---: | ---: | ---: | --- |
| RGB 0 | 14 Hz | 22 Hz | 13 spikes | Fix |
| RGB 255 | 30 Hz | 32 Hz | 17 spikes | Fix |

The input changed activity, but both images produced the same instruction.
The probe also recorded separate 200 ms positive and negative feedback
intervals, changes to adaptive weights, identical frozen weights after both
stimuli, and complete restoration of saved state.

The upstream rule can change weights during observation before any external
feedback. Consequently, weight changes alone do not show that feedback taught
the task. These checks do not establish learning, language understanding, or
an ability to program.
