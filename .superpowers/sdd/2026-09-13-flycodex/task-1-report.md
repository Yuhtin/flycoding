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
