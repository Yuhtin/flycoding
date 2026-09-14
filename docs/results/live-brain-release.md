# Live observatory release verification

The release adds measured neural activity, a separate local brain lab, a live
coding observer, an OpenCode adapter, and a grounded flybody presentation.
The [Muse acceptance](muse-live-brain/README.md) succeeded with two total prompt
submissions, including one interrupted permission trial. Synthetic checks and
local neural observations made no coding calls.

## Recorded checks

- Full Python suite: 130 passed, 1 optional test skipped before release.
- OpenCode and pilot boundary checks after the permission correction: 31 passed.
- Pinned body exporter checks: 4 passed.
- Existing browser state tests: 14 passed.
- Actual browser checks: consecutive dark/light neural observations rendered
  measured bins; completed jobs cleared firing; archive, missing-run state,
  English labels, and a 390 px viewport passed with no JavaScript errors.
- Actual acceptance capture: no JavaScript errors; genuine choice, backend
  execution, feedback, and external outcome were recorded in the same run.
- Final live-panel check: missing snapshot changed to connected when the actual
  run became available; the panel showed the exact Muse backend, 5/5 external
  tests, and its local 1/2 allocation, with no JavaScript errors or model calls.
- Pinned viewer rebuilds were byte-exact. The built wheel included all 65
  tracked package files, including 44 web files, byte-for-byte.
- All 68 original Codex-run files and the three original presentation assets
  remained unchanged.

[Browser evidence](live-brain-browser-check.json) ·
[Final live-panel check](live-brain-final-browser-check.json) ·
[Package evidence](live-brain-package-check.json) ·
[Original-file audit](live-brain-originals-check.json)

## Bounded workflow rulings

Three explicit rulings allowed necessary corrections after the planned final
fix wave. Implementation and review work used Luna agents.

1. **Correct isolated presentation labels.** The selected Archive footer, and
   later the missing-to-available live connection label, contradicted the
   displayed source. Finishing the authorized English panel required correcting
   them. The cost if wrong was a localized text regression; browser checks
   covered the affected states.
2. **Allow cold fixture startup.** Measured first execution exceeded an old
   500 ms fixture deadline before the test program started. The test-only
   startup allowance increased. A final run also exposed an empty readiness
   file before its PID write completed; the fixture now publishes that marker
   atomically. Strict post-ready descendant cleanup assertions and production
   deadlines stayed intact. The cost if wrong is slower detection of a fixture
   startup hang or an incorrect readiness signal.
3. **Repair OpenCode permissions and use the remaining allocation.** Actual
   acceptance exposed a worktree-relative edit-path contract. The exact-file
   rule was corrected and independently reviewed. A fresh run preserved the
   first manifest while receiving at most the remaining two sends. The cost
   if wrong is an overly broad permission or budget-accounting error; scoped
   path tests and summed reservations checked both boundaries.

The app's OpenCode permissions are not an operating-system sandbox. The brain
selects one of three fixed instructions; Muse writes the code; flybody motion
is procedural. These boundaries remain explicit in the panel and README.
