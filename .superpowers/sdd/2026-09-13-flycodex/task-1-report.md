# Task 1 report — neural backend and sensory panel

## Implemented

- Packaged the fixed 320 × 180 RGB sensory panel. It represents Codex activity,
  external-result availability, and passed/failed test area without drawing
  human-readable text into the neural input.
- Added fixed-threshold readout for `investigate`, `fix`, and `test`, including
  directional rates, gate count, cell identities, input/spike hashes, simulated
  time, and memory statistics in `NeuralPolicy.choose`.
- Adapted the pinned Stonkfly full-graph integrator, candidate efficacy rule,
  loss-accounted graph preparation, visual sampling, and circuit selection to
  explicit `data_dir` paths. There is no process-global data path and no
  trading, brokerage, market, AgentKit, or Codex dependency.
- `choose` runs a 500 ms neural window; `feedback` is a distinct 200 ms
  reward/aversive/neutral window. The frozen condition skips both active
  plasticity and passive candidate-efficacy decay.
- Added atomic/resumable source download, byte/hash verification, atomic graph
  outputs, retained-array verification, native-kernel build metadata,
  provenance-checked checkpoints, and a no-Codex probe.
- Added MIT notice, third-party attribution, upstream source/data locks, and a
  provenance manifest naming upstream file hashes, revision, and adaptations.

## TDD evidence

### RED

Command:

```text
rtk uv sync --all-groups && rtk uv run pytest tests/test_neural.py tests/test_panel.py -q
```

Relevant output before implementation:

```text
ModuleNotFoundError: No module named 'flycodex.neural'
ModuleNotFoundError: No module named 'flycodex.panel'
```

The new tests named the missing public behavior: exact directional thresholds,
inactive/missing gates, frozen candidate efficacy, panel state variation, and
invalid counts. The failures were expected because neither module existed.

### GREEN

Command:

```text
rtk uv run pytest -q && rtk uv run python -m compileall -q src
```

Result:

```text
11 passed
```

The package imports, all focused behavior tests pass, and bytecode compilation
reports no errors. `rtk c++ -O3 -std=c++17 -shared -fPIC
src/flycodex/neural/kernel.cpp -o /tmp/flycodex-kernel-smoke.dylib` also built
the ARM64 native kernel successfully. A wheel build confirmed it includes the
C++ source, provenance record, and all JSON locks.

## Live-data status and limitations

I did **not** run a full neural probe or package preparation concurrently with
the parent task. The parent independently prepared the pinned upstream graph in
`data/` and reported all 11 array hashes matching `arrays.lock.json` (166,700
neurons; 25,582,938 edges; 124,177,617 contacts). `prepare_data` now reuses and
re-verifies such a graph instead of rebuilding it. I then ran one coordinated,
frozen 500 ms `choose` window with a uniform RGB value of 240. It exactly
matched the independent pinned-original regression: left/right/gate rates
30/34/29, 388,867 total spikes, and spike SHA-256
`776c33e872595a635845b0c3719c8343e425ee47ea968a242f2ba0cb79230704`.
The comparison initially failed because the adapter left KC neurons at −52 mV;
the intact implementation sets their resting potential to −60 mV. Comparing
all initial-state hashes isolated that omission, and the explicit KC rest
assignment restored exact output parity. Memory remained unchanged. A full adaptive/frozen feedback probe and
checkpoint round was intentionally deferred to avoid concurrent heavy work;
no nonzero candidate weight should be read as task learning.

## Files changed

- `pyproject.toml`, `uv.lock`, `LICENSE`, `THIRD_PARTY.md`
- `src/flycodex/__init__.py`, `src/flycodex/panel.py`
- `src/flycodex/neural/` (policy, runtime, rule, native source, locks, provenance)
- `tests/test_neural.py`, `tests/test_panel.py`

## Self-review

The test suite covers the required compact behaviors and compile/package smoke
checks. The exact frozen reference regression passed. The full feedback probe
remains intentionally deferred; the model is not claimed as validated.

## Fix round 1 — review findings

Addressed all six Important findings.

- Copied the complete upstream `arrays.lock.json` and `neurons.lock.json`
  exactly, including the corrected `weight` hash. Preparation now requires an
  exact graph field set, verifies all 11 array hashes and dimensions, and uses
  upstream's canonical transmitter JSON serialization plus normalized source-ID
  equality check.
- Added explicit free-space preflights before download and before compilation;
  failures report required and available bytes.
- Split raw neural-window traces from choice decoding. `feedback` never returns
  `action` or `reason`; it reports `window_ms=200` and neutral
  `stimulus_ms=0` because neutral feedback has no external pulse.
- Corrected Pillow's inclusive rectangle endpoints. Fully passing panels have
  no red failure pixels and fully failing panels have no green passing pixels.
- Checkpoints now bind graph post IDs, plastic-edge selection, and complete
  runtime configuration. Restore requires the exact state set, validates all
  shapes/dtypes/floating values before mutation, and rejects partial or
  nonfinite checkpoints transactionally.
- The probe records reward and aversive traces, tests frozen weights after both
  stimuli, compares complete dynamic state after restoration, and resets to an
  identical dynamic start state before comparing dark and bright input.

### Fix-round TDD evidence

RED command:

```text
rtk proxy .venv/bin/python -m pytest tests/test_neural.py tests/test_panel.py -q
```

Relevant output:

```text
FAILED test_feedback_reports_a_window_trace_without_a_policy_decision
FAILED test_restore_rejects_a_checkpoint_missing_runtime_state
FAILED test_panel_has_no_failure_color_when_every_test_passes
3 failed, 12 passed
```

GREEN command:

```text
rtk proxy .venv/bin/python -m pytest -q
```

Result: `16 passed`.

### Live preparation and probe evidence

`prepare_data(Path("data"))` reused the existing graph after verifying all
sources, all 11 compiled arrays, and normalized-neuron identity. It reported
166,700 neurons, 25,582,938 edges, and 124,177,617 synaptic contacts.

A fresh preparation used hard links to the verified raw files in an isolated
temporary directory, avoiding a duplicate 1.1 GiB download. It returned
`prepared: true` with the same counts and graph SHA-256
`346b8af85a11af13b8324e18669812c1924569e7d1adcb4e6f45cc461a2c344b`.
The temporary data was removed afterward.

`probe(Path("data"), Path("runs/task1-probe"))` reported adaptive reward
weight change, identical frozen weights after reward and aversive feedback,
complete checkpoint-state restoration, and 200 ms reward/aversive pulses. The
paired dark/bright comparison records equal initial dynamic-state digests
before the two input windows. These mechanism checks do not demonstrate task
learning or cognition.
