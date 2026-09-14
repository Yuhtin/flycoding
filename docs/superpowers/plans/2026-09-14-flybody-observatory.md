# Flybody Observatory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Ship an English observatory with visibly articulated actual flybody geometry and an honest recorded-pilot replay ready for a Twitter video.

**Architecture:** Optional MuJoCo exporter produces packaged browser assets. A local Three.js viewer consumes session/replay presentation state without touching neural or Codex execution. A read-only demo snapshot makes viewing possible without neural data or Codex login.

**Tech Stack:** Existing Python HTTP server, vanilla browser JavaScript, local Three.js, optional MuJoCo/mesh tooling.

**Spec:** docs/superpowers/specs/2026-09-14-flybody-observatory-design.md

## Global Constraints

- All user-facing new presentation copy is English. Original measured records remain untouched.
- No real Codex calls, no pilot resume, no neural data recomputation. Use existing genuine records only as read-only inputs.
- Flybody source revision `d015e9bfe441bd90ae431bac24c55cb74bdbce26`; Apache-2.0 notice and derivative provenance required.
- Browser assets are local, no runtime CDN; no MuJoCo/training dependency for normal viewing.
- Body movement is procedural session-state visualization, never claimed as learned locomotion or neural control.
- Replay is explicitly labeled, read-only, and preserves original facts/IDs of test cases and hashes.
- Every shell tool command begins with `rtk`; unsupported commands use `rtk proxy`.

### Task 1: Actual flybody assets and interactive articulated viewer

**Files:** Create `tools/export_flybody.py`, `tools/build_body_view.*` as needed, `src/flycodex/web/body-view.js`, `src/flycodex/web/body/` assets/provenance/license, `tests/test_body_assets.py`; modify dependency/build metadata and THIRD_PARTY.md only as needed. Do not edit dashboard app/index/style/server yet.

**Interfaces:** Produce ES module `createBodyView(container, options={})` -> `{setState({mode, action, leftHz, rightHz}), setPaused(boolean), dispose()}`. State modes idle/working/success/failure. Expose canvas accessible description and a visible load failure callback/status via options.onStatus(message). Keep all relative asset URLs under `/body/` plus `/body-view.js`; provide an explicit route manifest to Task2.

- [ ] Inspect pinned fruitfly XML/keyframes/materials and fetch only required source meshes into ignored build cache. Record source file SHA256 and license.
- [ ] Build an optional reproducible MuJoCo/mesh export pipeline. Use compiled visual mesh geometry and MuJoCo articulated body poses. Simplify geometry with a documented triangle budget while preserving distinctive anatomy. Generate GLB and motion assets for idle/working/success/failure. Set every procedural joint pose inside defined limits.
- [ ] Verify source/artifact hashes, finite transforms, meaningful movement of distinct leg/wing/head nodes, and compact packaging using fixture/default tests that do not fetch assets or require MuJoCo. Optional exporter checks can exercise actual MuJoCo.
- [ ] Build/bundle the Three.js viewer locally (pin Three.js version; preserve MIT license). Model must be well lit and fill the stage, allow orbit/zoom, interpolate poses smoothly, support pause/reduced motion and disposal, and degrade clearly when WebGL fails.
- [ ] Render actual geometry in a temporary isolated harness and visually inspect anatomy and at least two movement poses. Do not claim model movement based solely on API assertions.
- [ ] Commit and write task-1-report.md with exact route manifest, asset sizes/hashes, dependency build command, pose conventions, tests and concerns.

### Task 2: English dashboard, read-only replay and bundled genuine demo

**Files:** Modify `src/flycodex/web/{index.html,app.js,style.css,__init__.py}`, `src/flycodex/{cli.py,codex.py}`, affected tests; create `src/flycodex/web/demo/` sanitized snapshot/images/translations and focused replay/presentation modules as needed. Do not modify original `runs/pilot` or `docs/results/pilot.json`.

**Interfaces:** Consume Task1 createBodyView contract and route manifest. `create_server(run_dir, host=..., port=..., demo=False)` selects either existing run public directory or packaged demo directory; CLI `serve --demo` selects demo=True. No write endpoints. Replay controller supplies viewer modes and historical selection using existing turn keys.

- [ ] Write focused tests for demo flag/routes, traversal refusal, original-vs-translated transcript projection, replay play/pause/reset/history selection, and unchanged budget/source snapshots. Update exact prompt test for future English equivalents.
- [ ] Build sanitized bundled demo from existing genuine pilot at `/Users/daviduarte/development/flycodex/runs/pilot/public/snapshot.json`, using original18PNGs. Remove all session IDs/home paths/raw metadata unrelated to display. Keep only true recorded command/agent events necessary for the demo. Preserve source identity and include an explicit English-translation indicator for historical translated text. No fabricated Codex output.
- [ ] Integrate a large flybody stage beside terminal; place sensory input/choices/neural metrics/tests below or alongside while keeping first-screen body and actual response prominent. English copy and accessible controls; responsive at390px and1440px, focus states and reduced-motion.
- [ ] Implement read-only condensed replay of recorded turns, always labeled. Presentation state controls body movement, never changes experiment data or calls runner. Live state uses actual busy/feedback and settles at completion. Selecting history cancels replay; missing/offline state cannot falsely show live work.
- [ ] Translate future PROMPTS to `Analyze the failure and explain the likely cause without editing.`, `Fix the discount function while preserving the tests.`, `Run the tests and report the result.` Preserve historical stored prompts. Translate CLI text and all dashboard chrome.
- [ ] Test focused suite and fresh browser demo/live/history/replay/reduced-motion/error paths; record screenshots and return precise commands. Commit and write task-2-report.md.

### Coordinator acceptance and publication

- Translate README and public result explanations into English, document serve --demo, actual body origin/motion boundary and changed future prompt language. Preserve historical protocol and measured records.
- Independently audit published demo against genuine source; visually inspect anatomy and changing joint poses. Record desktop/mobile browser evidence, screenshot and a short H.264 MP4 of labeled replay suitable for Twitter.
- Whole-branch final independent review from7d74702, one combined final fix wave if needed, scoped re-review.
- Run appropriate full tests/build once final code settles; verify wheel includes body/demo assets and normal viewing requires no heavy exporter libraries.
- Integrate and push existing public main, verify CI. Keep user's original data/run and local dashboard available; do not post to Twitter.
