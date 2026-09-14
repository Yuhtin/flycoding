# Live brain observatory

Approved direction: the user requested implementation of the preceding brain-first
proposal, orchestrated exclusively through Luna agents. All product copy is English.

The primary experience is a real local neural lab, alongside a live Codex observer
and a clearly separate archived demo. The lab computes new neural decisions from
user-selected task-state pixels or uniform dark/light sensory images. It never
calls Codex and says so. The coding observer displays fresh activity from future
ordinary CLI pilot runs and actual process events. No new real Codex calls are
made automatically while implementing/testing this release; all existing pilot
records remain unchanged. The existing CLI remains the concrete way to start a
new coding pilot, with its existing budgets and dedicated workspaces.

Brain anatomy uses the existing retained graph order and actual soma coordinates:
166700 retained neurons, 139662 valid positions, 27038 unplaced. Include the whole
retained positioned CNS with class filters for brain/optic/VNC and identify unplaced
activity separately. No invented positions or registration into flybody's head.
Use a separate enlarged brain view. Bin brightness represents actual simulated
spike counts/rates in 10ms windows; it is not physiological propagation along axons.

Instrument runtime windows with an optional observer that does not change numeric
state, RNG, timestep, plasticity, output choices, or default public trace structure.
Every bin has simulation time, sequence, sparse retained-neuron indices and counts.
A window's bin sums must exactly match its normal aggregate output/hash. Identity
metadata binds anatomy and activity to the same retained neuron order. Runtime
callback snapshots must not alias mutable arrays. No temporal spikes are invented
for the historic demo, whose summaries are explicitly unavailable as full activity.

Live lab work is serialized and bounded: one graph, one observation at a time,
500ms observation, optional explicit lab feedback as a separate200ms interval.
Cancel at bin boundaries; capped events and rejection of concurrent submissions.
No automatic infinite simulation. Brain stops showing new firing while computation
is paused, idle, disconnected, in error, or waiting for Codex. Display simulation
and wall time separately and latest measurement age. Same run/job/window identity
must connect input, activity, selected fixed prompt, actual execution and feedback.

Live local lab HTTP controls accept only validated small JSON inputs, require
loopback and same-origin protection, reject arbitrary paths/commands and never
construct a coding runner. Normal read-only serve/demo mode remains read-only.
Viewer assets work offline from a Python wheel without optional build dependencies.
CLI should support `flycodex serve --lab --data-dir data --port 8767` and retain
`--run-dir` for monitoring a future separate coding run. Missing data yields a
helpful English state, not a fake moving brain.

The interface shows sensory pixels -> activity -> DNp20 left/right and DNpe017
gate -> fixed threshold -> selected instruction -> actual coding output -> tests
and feedback. Never show fabricated action probabilities, typed words as if the
brain authored them, or random control choices as neural decisions.

Improve flybody to a stable resting specimen with credible floor contact and
restrained head/antenna/wing movement. Evaluate upstream walking rollout feasibility,
but do not claim a trained or physics-simulated gait unless actually verified.
A procedural resting posture is acceptable if labeled and clearly distinct from
measured neural activity. Preserve actual flybody geometry and provenance.

Acceptance: actual local full-graph observations streamed and audited against their
aggregates; brain rendering changes for measured bins and freezes otherwise; input
changes are real (choices need not differ); clear live/lab/archive boundaries;
new coding-run telemetry tested with synthetic Codex boundary; original evidence
unchanged; mobile/desktop/WebGL/reduced-motion/error/cancel checks; all appropriate
tests and package checks pass; English README and a newly captured real-brain video.
