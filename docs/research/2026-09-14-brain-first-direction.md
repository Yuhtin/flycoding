# Brain-first Flycodex: proposed direction

Research/design recommendation, not an implemented or approved new experiment.
The current public pilot and its records remain unchanged. No new Codex calls
or neural runs were made during this investigation.

## What the current interface obscures

The default dashboard replays a recording. The measured pilot contains four
neural choices (all Fix) and five random-control choices. The neural controller
receives colored task-state pixels, chooses one of three fixed instructions,
and pauses while Codex executes. It does not read terminal text, compose
language, or demonstrate learned programming. The body moves procedurally.

All four neural choices recorded 392,732 spikes and the same action. Their
native compute time was about 0.93 seconds for 500 ms of simulated time, excluding
loading and other overhead. The identical/simple starting task makes a weak
visual demonstration of decision-making, even though the recorded choices are
real outputs of the model.

## Recommended experience

1. Make an actually running neural session the primary experience. Keep a
   clearly named archived recording as a secondary view. A local brain lab can
   accept explicitly chosen sensory images and compute fresh output without
   calling Codex; it must be labeled as a lab, not an active coding session.
2. Put an enlarged anatomical brain beside the flybody, with a link from the
   head rather than an unverified claim of anatomical registration. Overlay
   per-neuron firing measured in bounded 10 ms simulation bins. Show simulation
   time, neuron identity, the input frame, and recording/live state. Missing
   soma positions remain unplaced, with aggregate activity disclosed separately.
3. Show the actual readout: left/right DNp20 rates, DNpe017 gate, the fixed
   threshold rule, and the resulting instruction. Do not invent three action
   probabilities or claim the neural simulation wrote the text.
4. Make the causal sequence visible: sensory pixels -> simulated neural activity
   -> fixed readout -> selected prompt -> actual Codex process -> external tests
   -> neural feedback. Associate each stage with the same run and turn IDs.
5. During Codex execution, say `Codex is working · neural simulation paused`.
   Neural activity must not continue flashing unless the model is actually
   advancing. Body posture/motion can illustrate phases, with its origin clear.
6. Replace the current airborne-looking joint loops with a stable grounded
   specimen, credible foot contacts, weight and head motion. Evaluate actual
   MuJoCo locomotion rollout separately before claiming physical or learned
   motion; a trained locomotion controller would still be separate from the
   connectome's prompt readout.
7. Show new task states that genuinely call for different actions only through
   a defined experiment. If this fixed decoder still chooses Fix every time,
   display that behavior. Never script diverse choices to improve the clip.

## Data and evidence boundary

Existing annotations supply 139,662 valid soma positions among 166,700 retained
neurons. The [static anatomy preview](brain-anatomy-preview.png) plots 124,290
positioned neurons in annotated brain, optic/visual and descending classes.
Orange markers are the four readout neurons. This image contains no activity
animation; its two views are dataset coordinate projections, not asserted
registered anatomical orientations.

Existing published traces contain spike totals and hashes, not temporal
whole-brain spike bins. Instrument and record future neural windows before
presenting them as activity. Recomputing from a checkpoint would be a separately
identified reconstruction and must be checked against original aggregates; it
cannot silently become an original recording.

See the [primary-source investigation](2026-09-14-brain-visualization.md) for
flybody scope, real MaleCNS anatomy, available viewers and unresolved geometry
registration checks. This proposal makes no changes to the live demo, core
runner, prompts, original records, or public repository.
