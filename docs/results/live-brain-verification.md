# Live brain verification

This record separates local neural validation from coding-backend acceptance.
The original September 13 Codex pilot is unchanged; its historical summaries do
not contain temporal per-neuron activity.

## Neural measurements

The optional observer was compared with the original frozen-network 1/5 task
input on the full retained graph. All 50 measured 10 ms bins sum exactly to the
normal aggregate of **392,732 spikes**, with the same spike hash, input hash,
and decoded instruction as both the observer-disabled run and the original
pilot. The readout was left DNp20 **28 Hz**, right DNp20 **32 Hz**, and **14 gate
spikes**, selecting **Fix**. No coding backend was invoked by this check.

Three fresh `LabService` requests also completed with distinct input hashes and
single-job event identities:

| Input | Measured spikes | Bins | Selected instruction |
| --- | ---: | ---: | --- |
| Uniform dark | 135,364 | 50 | Fix |
| Uniform light | 416,674 | 50 | Fix |
| Task state, 1/5 tests | 392,732 | 50 | Fix |

Every request passed through loading, running, and completed states; its bin
sum matched its reported aggregate. Different sensory activity did not imply
a different selected instruction. These checks establish instrumentation
consistency, not biological validity or a learning advantage.

## Full-size integration fixture

A separate one-attempt fixture used the real local neural policy and a clearly
synthetic coding executor. It made **zero model calls**. Its 50 choice bins and
20 feedback bins were recorded without sparse-array truncation. Their sums and
spike hashes matched the normal aggregates: **392,732** choice spikes and
**199,794** feedback spikes. The five task tests passed after the fixture edit;
this is integration validation, not evidence of a coding model's performance.

Both full-size documents passed the activity reader's shape validation. Actual
HTTP checks accepted the exact panel origin, rejected a missing/wrong port and
a mismatched loopback alias, and served the measured activity plus the separate
bundled archive. No model invocation occurred in these checks.

## Anatomical mapping

An independent comparison checked all **139,662** exported float32 XYZ positions
and retained indices against the pinned annotation source, in the graph's
**166,700-neuron** order. All four output neurons have valid positions. The
**27,038** unplaced neurons receive no invented coordinates. The four anatomy
assets were also found byte-for-byte in the built Python wheel.

See [machine-readable neural and anatomy checks](live-brain-check.json).

## OpenCode configuration

A read-only diagnostic of the installed OpenCode **1.18.27** was captured and
parsed in memory, without printing or saving the resolved configuration. The
safe checks confirmed the exact `opencode/muse-spark-1.3-contributor-free` model
and small model, disabled sharing, empty MCP/plugins/instructions, matching
task permissions, and disabled LSP/formatting. No prompt was submitted by the
diagnostic. Tool permissions are application-level controls, not an OS sandbox.

Coding acceptance and final interface checks are recorded separately after
the corresponding implementation is reviewed.

## Grounded body presentation

The resting pose was checked against the pinned MuJoCo model and the unchanged
85-component GLB. All six claw supports meet a common plane within the recorded
source/export tolerances. The simplified rendered meshes differ by at most
0.000123 scene units in support height; the platform top uses the same model
scale and a small rendering clearance. Camera framing no longer determines
the floor.

All lower-body joints and folded wings remain fixed across the procedural
clips. Idle is static; work and feedback use restrained head, antenna and
abdomen movement. The exporter checked 87 source hashes and 192 poses. This is
forward-kinematic pose verification, not a physics rollout or trained gait.
See [grounded body measurements and hashes](grounded-body-check.json).
## Missing-data behavior

A real local server started with absent neural data returned HTTP 503 and
`Prepared neural data is unavailable` for both state inspection and observation.
It remained idle, created no run directory, and made no coding calls.
