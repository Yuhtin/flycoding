# Live Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** Show real neural computation choosing prompts through a live anatomical brain viewer, an explicit lab and a connected coding observer.
**Architecture:** Optional numerical observers emit immutable10ms bins; a bounded lab service and coding recorder expose identity-bound events; a browser renderer consumes actual anatomy and activity. Body motion remains separately labeled.
**Tech Stack:** Existing Python/NumPy/C++ runtime, local HTTP, Three.js, vanilla JS; optional MuJoCo exporter.
**Spec:** docs/superpowers/specs/2026-09-14-live-brain-design.md

## Global Constraints

- All agents gpt-5.6-luna, per explicit user instruction (overrides skill tier suggestions).
- All shell commands start rtk; work only in isolated flycodex-brain checkout.
- Original /Users/daviduarte/development/flycodex/runs/pilot and source data read-only. Prepared data may be read for real neural validation; runtime build caches only if code hash already matches, otherwise use owned cache/data links safely.
- No actual Codex calls while implementing/testing. Synthetic coding boundary only. No original pilot resume.
- English UI/docs; numerical invariance; original hashes/records preserved; no fake brain activity.
- One implementing agent at a time; independent read-only research may overlap. Root owns docs/results/media and release integration.

### Task 1: Neural measurement, anatomical export and bounded lab service
**Files:** runtime.py, policy.py; new neural/activity.py, lab.py; tools/export_brain.py; web/brain assets; focused tests.
**Produces:** `NeuralPolicy(..., on_activity=None)` backward-compatible optional callback; `FullGraphRuntime.window(..., on_bin=None)` callback after each10ms bin. Bin dictionaries: `{type:'bin', start_ms, end_ms, indices:[int], counts:[int], total_spikes:int}`; indices are retained graph offsets, copied counts; callback runs after existing bin updates. Preserve aggregate trace by default.
`LabService(data_dir, policy_factory=NeuralPolicy)` with `observe({kind:'task'|'dark'|'light',passed:0..5})`, `cancel()`, `state()`, `events(after:int)`, `close()`. Nonblocking observe returns job_id; conflict raises bounded error; state records status idle/loading/running/completed/cancelled/error, job_id, input, choice and error. All events have seq, job_id, type (started/bin/choice/completed/cancelled/error); sparse bins carry above payload. Keep at most one job's <=256events; expose oldest/latest seq and reset indication for lagged cursors. lab performs one frozen500ms observation per request, reset before each independent experiment, no runner or automatic loop. UI must be able to distinguish loading vs emitting bins. Cancel while loading takes effect before first bin.
Anatomy export: manifest.json with version, total_neurons, positioned_neurons, missing_neurons, source/order hashes, coordinate disclaimer, readout indices and file hashes; positions.bin little-endianfloat32 XYZ; indices.bin little-endianuint32 corresponding retained offsets; neurons.json contains retained-order ids/types/classes. All valid positioned rows retained, no invented coordinates. Explicit source inputs CLI --data-dir; export local pinned annotations; normal app imports no exporter dependency.
- [ ] Add red tests proving callbackbin counts sum to baseline outputs using small owned neural fixtures and LabService concurrency/cancel/events with fake policy.
- [ ] Implement optional callback without changing kernel or calculations, copied sparsebins, fixed-size lab/event state with locks and worker lifecycle.
- [ ] Export actual local anatomy to packaged assets and source hashes; verify 139662 positions,166700 IDs,4 output positions, byte layout and mapping.
- [ ] Run focused tests and report contract/commands; commit only owned code/assets/tests.

### Task 2: OpenCode runner and durable capped execution
**Files:** new opencode.py and runner-focusedtests; pilot.py/cli.py/storage.py only where backend/maxcalls contractsrequire; existingCodexadapterpreserved.
**Authorization:** Userallowsmaximum3actualOpenCodepromptsubmissions usingexactfreeMuseSpark1.3 model; rootacceptance onlyafterreview, workersfakeprocessonly. NoactualCodex calls.
**Produces:** `OpenCodeRunner(workspace, model=..., timeout=300).run(prompt, session_id, on_event)` matchingexistingrunneroutcome shape and truthfully normalizedliveevents withbackend field/originalrawrecord. Explicitmodel/session/cwd; process-groupdeadline/cancel anduncertainprocessfailclosed as existingCodexadapter. `Pilot(..., backend='codex', max_calls=None)` and CLI flags `--backend codex|opencode --max-calls N` withimmutablemanifest/totalcap; defaultsbackwardcompatible. Acceptancecallerchoosesopencode/freeMuse/maxcalls3 andfreshdirectory. No fallbackorautomaticretriesoutsidecap.
- [ ] Inspect installedOpenCode1.18.27CLIhelp andprimarydocs. Verifyfreecatalog withoutsendingprompts; use--pure, --formatjson, explicitmodel, explicitresumeID; no--continue/share. Scoped taskpermissions/config do notmodifyuserglobalconfig.
- [ ] Add syntheticprocess tests forJSONevents/sessioncapture/resume/malformed/error/deadline/config/modelpin; reserve-before-send and3cap/resume tests withinjectedrunner; compatibilityexistingCodexsuite.
- [ ] Implement separateadapter and persistedbackend/capmetadata; normalizeevents preservingrawidentity/labels; distinguishtoolpermissionsfromOSsandbox, neverclaimequivalence.
- [ ] Commit/report exactbackendCLI/configprotocol,3-cap semantics andtestresults. Rootrecordsnewrunlater; do notspendanyrequests.

### Task 3: Live endpoints and future coding telemetry
**Files:** web/__init__.py, cli.py, pilot.py; new activity recording/reading module as needed; tests/test_web.py and focused integration tests.
**Consumes:** Task1LabService and activity callback; actual anatomy manifest assets.
**Produces HTTP:** `GET /lab/state`, `GET /lab/events?after=N`, `POST /lab/observe` small JSON exactlykind/passed, `POST /lab/cancel`; `GET /brain/manifest.json`, positions.bin,indices.bin,neurons.json. Lab routes only enabled with --lab; localhost-only, enforce expected Host/Origin and application/json for mutations, 1KiB limit; reject unsupported fields/values. GET state response includes availability and eventcursor; errors400/409/503. Snapshot/oldbodyroutes unchanged andread-only.
Future coding runs use optional callback wiring on actual NeuralPolicy to emit bounded per-window/public neural activity files tagged run/attempt/turn/phase. Never rewrite past runs or require new callbacks from fake test policies. Expose exact safe GET `/activity.json` for observed run with cursor ifneeded; no arbitraryfiles. Missing historical telemetry returns explicit availabilityfalse. Share bin schema and retained-orderhash from Task1; document final exactschema forfrontend. API response data stays bounded and activity identity cannot mix turns.
- [ ] Add red routevalidation/read-only compatibility tests and synthetic coding integration proving bin identities match selectedprompt/phase without actualCodex.
- [ ] Wire lab ownership/server shutdown and CLI --lab --data-dir; preserve --demo behavior, add activity recording futurepilot only.
- [ ] Test limits, stalecursor, cancel/shutdown, missingdata; commit/report exactfrontendcontract.

### Task 4: Brain-first live interface
**Files:** web/index.html,app.js,style.css; new brain-view source/bundle and state module; existing buildtool ifneeded; focused JS/browser tests.
**Consumes:** Task1anatomy and Task3finalHTTPschemas.
- [ ] Implement actual Three.js Points brain anatomy with classfilters, orbit/zoom, selectedneuronidentity and actualfiring overlay mapped byretainedindex. No inventedtiming: paint receivedbins with timestamp/age, clear livefiring when paused/finished/disconnected. Handle frames arriving between polls by showing measured windows explicitly ratherthan pretending delayedplayback iscurrent. Use existing localbuilddependency pins, nobrowserCDN.
- [ ] Primary Live brain lab tab uses realPOSTobserve, task passedcount anddark/lightinputs, cancel/busy/missingdatastates; clearlystatesnoCodexcalls. Live coding tab follows realrun, fixedpromptreadoutthreshold, phaseflow and actualterminal; Archive preserves oldrealpilot withoutfakefullbrainspikes andlabelsrandomcontrols.
- [ ] Make flybody/brain/selectedpromptandphase visible together at1440x1000; physicalunits disclaimers whereuseful; allEnglish, responsive390px, keyboard/reducedmotion/WebGLfallback.
- [ ] Add focusedcontracttests and freshbrowser checks using syntheticevents +realserverdata; fix oldoptionalresize test to await newrenderafterresize beforequietperiod. Commit/report.

### Task 5: Grounded flybody and final integration
**Files:** tools/body-view/viewer.js, exporter ifneeded, generatedbodybundle/assets/provenance, relevant tests.
- [ ] Inspectactualbodygeometry/stance and upstreamwalkingavailability fromresearch; choose stablegroundedrestingposture with visiblysupportedfeet and restrainedupperbodymotion. No danglingwalkinglegs orwingflappingwhilebrainidle.
- [ ] Keep actualgeometry and scopedproceduraltruth; documentposes and any changedprovenance. Groundplane placement follows consistent stance, notarbitraryallmeshboundingboxshadow. Rebuildbundle/assets asneeded withoptionalpinnedtools.
- [ ] Browserverify groundedposes desktop/mobile and correctneural/bodyphase distinction; verifyexporthashes ifchanged; commit/report.

### Coordinator acceptance and release
- [ ] Independent full-graph lab observations fromexistingdata, compare telemetrysumsandaggregatehashes withobserver-disabledbaseline; no originalstate writes.
- [ ] Fullsuite, focusedbrowser, isolatedwheel/labmissingdata checks; auditoriginalevidence andprivatepaths.
- [ ] Root EnglishREADME/resultsdocs and recordactualbrain/OpenCodevideo (actual measured activity and backend output). Taskreviews thenwholebranchreview; onecombinedfinalfixwave andonescopedre-review.
- [ ] Merge/push existingauthorizedpublicrepo afterverification, checkCI, serve newlablocally, preserveverifiedartifacts and cleanonlyownscratch/worktree.

## Steering precedence

Latestuserauthorizationoverrides earlier no-new-calls global text only for root's
bounded OpenCode acceptance: maximum3promptsubmissions, exactfreeMuseSpark1.3,
stoponsuccess, originalsimmutable. All worker testsremain synthetic. Backend/UI
must display actual runnername/provider; modes are Live brain lab, Live coding,
and Archive. Tasknumbersshifted:1neural,2OpenCodeadapter/cap,3HTTPtelemetry,
4frontend,5groundedbody. Task1alreadyunderimplementationdoesnotchangecoreAPI.
