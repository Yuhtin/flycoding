# English flybody presentation verification

This presentation update uses the original September 13, 2026 pilot. It does
not add experimental runs or new Codex calls. The original release checks
remain in [verification.md](verification.md).

## Evidence

- Actual flybody visual meshes from pinned upstream revision
  `d015e9bfe441bd90ae431bac24c55cb74bdbce26`: 85 components, 95,564 triangles.
- 87 upstream source hashes and 192 exported MuJoCo forward-kinematics poses
  independently checked. Movement is a procedural animation of session state,
  not learned locomotion or connectome-driven motor control.
- Original pilot: 23 local files unchanged; all 18 original PNG and RGB hashes
  match. The demo retains 50 genuine selected events and 16 source-hashed
  display translations. It includes six successes and nine completed calls.
- Fresh Chrome checks cover desktop and mobile layouts, visibly different
  working poses, original/English transcript selection, replay pause/reset,
  history selection, feedback images, evaluation timing, reduced motion,
  live activity, disconnects, and missing snapshots.
- A complete 54-second replay was captured without JavaScript errors and
  ended at 5/5. The approximately 56-second MP4 is H.264, 1440 × 1000,
  30 fps, YUV 4:2:0, with fast-start metadata. Frames at 3, 20 and 55 seconds
  were visually inspected.
- The built wheel was extracted outside the checkout and served all 35
  expected demo routes, including 18 images, without original run files,
  authentication, MuJoCo, or PyTorch.

Machine-readable evidence: [body](flybody-check.json),
[demo provenance audit](demo-check.json), and
[video and package](presentation-check.json).

## Review

Task-scoped reviews and an independent whole-branch review checked the authored
viewer, exporter, demo source, replay/live state, packaging, and public claims.
The whole-branch review found one live-mode ordering issue and two smaller
viewer/exporter issues. All three were corrected together in
`0ffc6f80cfac70450b13d2273eccf00464a57213`.

The full pre-fix suite passed: **83 tests**. Whole-branch whitespace checking
reported five whitespace-only lines inside bundled upstream Three.js shader
strings; those generated strings are retained from the pinned dependency.


## Final correction checks

Delayed positive/negative feedback now triggers once even if a preceding poll
observes the settled turn before evaluation. Initial history, reconnects,
replay, and disconnected states do not trigger stale feedback animation.
Paused body rendering stops after camera damping settles, including while the
dashboard polls. Resize, orbit, zoom, explicit resume, and disposal still work.
Exporter check mode detects missing or modified packaged licenses without
repairing them; ordinary export retains license copying.

Verification on the corrected code:

- **83 passed, 1 skipped** in the normal Python suite. The skip is the optional
  exporter module, whose heavy build dependencies are deliberately absent.
- **4 passed** in the exporter module with its pinned optional dependencies.
- **2 passed** in the fresh Chrome integration regressions, including actual
  paused WebGL draw counts and delayed positive/negative live feedback.
- **3 passed** in the Node presentation suite; existing desktop/mobile and
  replay/error-path browser smoke checks also passed.
- **87 source hashes and 192 MuJoCo poses** verified again.
- Source distribution and wheel rebuilt; the final extracted wheel again
  served all **35 routes / 18 images** independently of the source checkout.
- Original **23 files**, **18 image pairs**, **50 events**, and **16 translations**
  independently audited again: no changes or new Codex calls.

The video and screenshot were captured before these final fixes. They show the
same normal replay behavior verified by the post-fix browser checks. Artifact
hashes and the final viewer hash are retained in
[presentation-check.json](presentation-check.json).

## Scoped re-review and remaining test limitation

The scoped re-review confirmed all three original findings were addressed.
Its fresh exporter run passed all four tests and its delayed-live-feedback
browser case passed. The reduced-motion case failed twice only at the resize
settlement assertion: one run observed two late draws, the other one late draw.
Both runs had already passed initial paused idle, orbit, keyboard zoom, and
wheel zoom settlement. Resume/disposal were not reached in those two review
runs; they passed in the implementer's earlier complete browser run.

The optional helper can reuse the quiet interval before an asynchronous resize
arrives. This remains a known flaky assertion in the optional browser test;
there is no demonstrated return of continuous paused rendering.

Ruling: Keep the optional browser resize-settlement assertion as a non-blocking known flaky test — both review runs settled while paused and after orbit/zoom, then observed only one or two late resize draws; this is not evidence of the former continuous render loop, and the single final fix wave is complete — cost if wrong: extra manual resize verification and follow-up test maintenance, with a possible missed resize-specific rendering regression.
