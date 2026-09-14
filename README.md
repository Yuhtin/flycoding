# flycoding

**The new era of vibe coding.**

**A simulated fly brain picks the prompt. OpenCode or Codex does the coding.**

A fly at a keyboard. Its chosen prompt on the monitor. OpenCode answering.
Press **Play** to watch the recorded run in a full-screen, pixelated 3D workstation.
**Amber is the fly prompt. Cyan is OpenCode.** The fly uses actual
[flybody](https://github.com/TuragaLab/flybody) geometry; the neural HUD shows
measured activity from that same run.

![flycoding: a fly at a physical keyboard with its prompt and OpenCode on the monitor](docs/results/workstation-dashboard.png)

**Latest live run:** the brain selected Fix, Muse Spark corrected the function,
and external tests improved from **1/5 to 5/5**. Acceptance used **2 of 3 authorized
prompt submissions**, including an earlier permission failure.
[Watch flycoding](docs/demo/workstation.mp4) ·
[Evidence](docs/results/muse-live-brain/README.md) ·
[English post draft](docs/demo/flycoding-tweet.txt)

## Press Play

Python 3.11+, [uv](https://docs.astral.sh/uv/), and Git are enough to view the
bundled Muse recording. You do not need model authentication, neural data, MuJoCo,
or a training setup to watch it.

```sh
rtk git clone https://github.com/Yuhtin/flycoding
cd flycoding
rtk proxy uv sync --frozen
rtk proxy uv run flycoding serve --demo --port 8765
```

Open **http://127.0.0.1:8765** and press **Play**. Pause and resume with the same
button, or replay after completion. The fly's instruction and the actual model
output appear in order. Commands and tool errors stay under **Terminal details**.

The player is labeled **Recorded run** and preserves the recorded timing. It
sends no prompts. **About this recording** links to the local lab, live
CLI observer, and historical Codex archive at `/observatory`.
[Workstation validation and media](docs/results/workstation.md).

[Original live Muse capture](docs/demo/live-brain-opencode.mp4) ·
[Earlier Codex replay](docs/demo/flycodex-demo.mp4)

Commands here use [RTK](https://github.com/rtk-ai/rtk). For the viewing-only
commands, omit the `rtk` or `rtk proxy` prefix if you do not have it installed.

## What is actually happening?

The brain selects **one of three fixed instructions**: Investigate, Fix, or
Test. It does not write natural language. OpenCode or Codex receives the selected
instruction and performs the coding work in a dedicated task workspace.

1. The task state becomes **320 × 180 RGB pixels**.
2. The simulated MaleCNS network runs a **500 ms observation**.
3. Measured DNp20 left/right activity and a DNpe017 gate determine the action.
4. The coding backend receives the corresponding fixed prompt. Neural time pauses.
5. Five external tests score the result, followed by a separate **200 ms feedback**
   interval in the neural simulation.

The advanced observatory at `/observatory` uses actual soma coordinates for
**139,662 of 166,700 retained neurons**. The other **27,038 neurons have no usable position** and
are counted separately. Each activity bin contains measured simulated spikes
from a 10 ms interval, bound to the same neuron order as the anatomy. These are
soma positions, not reconstructed axons or a brain registered inside the fly's
head. The model is experimental; activity does not establish biological fidelity,
language understanding, or task learning.

The workstation HUD shows the retained neuron count, active neurons per bin,
simulated spikes per second, and a measured 96-cell raster. It holds the last
measurement with **Paused** or **Waiting** when the neural timeline stops.

The 3D specimen uses the actual flybody geometry. Its resting motion is a
**procedural presentation**, separate from neural computation. The connectome
does not control the displayed legs, and the body is not running a trained gait.

The modes distinguish a fresh local neural experiment, an observer of a separate
coding process, and the original Codex archive. Historical recordings have no
per-neuron temporal telemetry; the viewer does not invent it. English translations
of historical Portuguese messages are identified, with original text available.

## The original Codex pilot

On September 13, 2026, all **six attempts succeeded using nine Codex calls**.
Every attempt started at **1/5 tests passing** and ended at **5/5**, with no task
violations.

| Condition | Successful attempts | Calls used |
| --- | ---: | ---: |
| Adaptive network | 2/2 | 2 |
| Frozen weights | 2/2 | 2 |
| Uniform random choice | 2/2 | 5 |

Both neural conditions selected Fix immediately. Adaptive memory changed and
was retained, but performed the same as frozen weights. **This pilot did not
demonstrate a learning advantage.** Six attempts do not establish learning,
generalization, language understanding, or statistical significance.

[Results and evidence](docs/results/README.md) ·
[Attempt summary](docs/results/pilot.md) ·
[Recorded traces](docs/results/pilot.json)

The measured pilot used Portuguese prompts on revision
`a16e1713f340a15a4e87f2d5651536f03aa9fe3a`. The English interface and flybody
presentation were added afterward. Historical records and their hashes are
preserved; the new presentation is not another experimental run.

## Run a live brain experiment

Local simulation needs macOS or Linux, Python 3.11+, `uv`, Git, `curl`, RTK,
and a C++17 compiler. Prepare the data once, then start the local lab:

```sh
rtk proxy uv sync --frozen
rtk proxy uv run flycoding prepare --data-dir data
rtk proxy uv run flycoding serve --lab --data-dir data --port 8767
```

Open **http://127.0.0.1:8767/observatory**. Choose the task's passing-test count or a uniform
dark/light input, then start one observation. Each request computes a fresh
frozen-network decision. No coding CLI or authentication is needed for the lab.
The first request loads the graph; cancellation takes effect at a neural bin
boundary. Missing data is reported explicitly.

The activity overlay shows measured windows with their simulation time and age.
It clears the firing overlay when the job finishes or disconnects. Click a
positioned neuron to inspect its measured count; activity from unplaced neurons
is counted separately. A changing input can change activity without changing
the selected instruction.

## Run a Codex pilot

Running the experiment requires macOS or Linux, Python 3.11+, `uv`, Git,
`curl`, a C++17 compiler, RTK, and an authenticated Codex CLI. The runner uses
POSIX locks and process groups; Windows has not been validated. Real runs
require an editable checkout so the manifest can identify the source revision.

```sh
rtk proxy uv sync --frozen --group dev
rtk proxy uv run flycoding prepare --data-dir data
rtk proxy uv run flycoding probe --data-dir data --output-dir runs/probe
```

`prepare` downloads the pinned MaleCNS sources, verifies their hashes, and
compiles the retained full graph: **166,700 neurons and 25,582,938 edges**.
`probe` checks neural mechanisms without calling Codex. Existing verified data
is reused. The first neural load compiles the C++ kernel locally.

Measured on a 16 GiB ARM64 Mac, the prepared data occupies about **1.57 GiB**
and `graph.npz` about **239 MiB**. Preparation needs additional temporary disk
space and checks for it. One graph is loaded at a time; compressed neural
checkpoints in the pilot were approximately 6.5 MB each.

Run the dashboard and experiment in separate terminals:

```sh
rtk proxy uv run flycoding serve --run-dir runs/pilot --port 8765
rtk proxy uv run flycoding run --data-dir data --run-dir runs/pilot --model gpt-6-astra
```

The viewer does not start the runner. The runner fixes its model, CLI version,
source revision, parameters, hashes, and permissions in the manifest before
sending instructions. Codex uses `exec --json`, explicit session-ID resume,
`--ignore-user-config`, approval `never`, and sandbox `workspace-write`.
Each turn has a 300-second deadline; external evaluation has 30 seconds.
Credentials stay in your local Codex configuration.

## Use OpenCode with Muse Spark

Install [OpenCode](https://opencode.ai/docs/cli/) and confirm the model is
available with `opencode models opencode`. This adapter was developed against
CLI **1.18.27**.
The exact model below is the **Contributor Free** variant listed by
[OpenCode Zen](https://opencode.ai/docs/zen/); availability and pricing can change.
There is no automatic model fallback.

Use a fresh run directory and start the observer in another terminal:

```sh
rtk proxy uv run flycoding serve --lab --data-dir data --run-dir runs/muse-demo --port 8767
rtk proxy uv run flycoding run --data-dir data --run-dir runs/muse-demo --backend opencode --model opencode/muse-spark-1.3-contributor-free --max-calls 3 --stop-after-attempts 1
```

The cap counts **prompt submissions**, including failed or uncertain started
sends. A submission may contain multiple model/tool steps. The stored cap,
backend, and model must match on resume. Success ends the attempt early.
Open `/observatory` and select **Live coding** before starting the run to see
its first neural window.
The observer itself never launches a coding backend. Its input, readout, prompt,
terminal, external score, feedback, and call cap follow the same recorded turn.

OpenCode runs with an explicit model and session, isolated task configuration,
restricted tool permissions, and sharing disabled. These are application-level
tool permissions, **not an OS sandbox**. The original Codex adapter retains its
`workspace-write` sandbox. Both runners record their actual backend identity
and terminate their process group on cancellation or deadline.

## Experiment contract

| Action | Current instruction |
| --- | --- |
| Investigate | Analyze the failure and explain the likely cause without editing. |
| Fix | Fix the discount function while preserving the tests. |
| Test | Run the tests and report the result. |

The original Codex pilot used Portuguese instructions. The September 14
[Muse acceptance](docs/results/muse-live-brain/README.md) used the English Fix
instruction above. This single task does not compare prompting languages.

The task is to fix `discounted_total` to compute
`subtotal_cents * (100 - discount_percent) // 100`. The initial bug subtracts
the percentage directly. Five preserved tests cover zero, partial, and full
discounts, a zero subtotal, and integer rounding. Only the implementation may
change. The external evaluator accepts a deliberately restricted integer
arithmetic return expression; it is not a general sandbox for arbitrary Python.
Changing protected files disqualifies an attempt, even if its tests pass.

Each neural choice advances **500 ms** of simulated time, with the upstream
**0.1 ms** internal step. With DNpe017 firing, the DNp20 mean right-minus-left
rate selects Fix at **≥ +2 Hz**, Test at **≤ −2 Hz**, and Investigate otherwise.
The log distinguishes low activity from a directional choice. While the coding backend
works, the neural clock pauses.

After every valid evaluation, including the final one, feedback is the sign
of the change in passing-test count. A separate **200 ms** interval applies
positive/negative stimulation at **20 mV-equivalent**, or no external pulse
for neutral feedback. Feedback spikes never create an extra instruction.
Infrastructure failures do not receive task feedback.

Attempts run in this order: adaptive, frozen, random; then repeat. Each starts
with the original bug and a fresh session. Adaptive attempts retain confirmed
memory while resetting dynamic state. Frozen attempts reset fully and verify
weight identity around every interval, including passive decay. Random
controls use seeds **1729** and **1730**.

## Budget, stopping, and recovery

The default allocation is **5 calls per attempt, 10 per condition, 30 total**.
An explicit `--max-calls` adds a lower total cap, which also survives resume.
An early success ends its attempt without transferring unused calls. Every
send reserves budget durably before starting the coding backend. Pending or uncertain sends
still count; they are never automatically resent.

```sh
rtk proxy uv run flycoding status --run-dir runs/pilot
rtk proxy uv run flycoding report --run-dir runs/pilot --output-dir docs/results
```

Ctrl-C stops the active process and preserves its reservation. Resume with the
same command and run directory. A handled interruption with confirmed process
cleanup abandons that attempt and allows remaining allocations. A crash with
an uncertain process or side-effect boundary stops with `recovery_error` and
requires manual journal reconciliation. Missing or incompatible confirmed
checkpoints also prevent continuing. Do not delete reservations or create a
new directory to reset an already authorized budget.

Use `--stop-after-attempts 1` to pause at a safe attempt boundary. Resuming
requires the same source and settings. The original completed pilot should
be viewed or exported, not resumed after this presentation update.

Report export writes `pilot.json` and `pilot.md`, omits session IDs and raw
events, and sanitizes known local paths in diagnostics. For a fresh export
destination, copy the referenced PNGs from the run's `public/` directory into
an `inputs/` subdirectory. Review artifacts before publishing them.

## Development and provenance

```sh
rtk proxy uv sync --frozen --group dev
rtk proxy .venv/bin/python -m pytest
rtk proxy uv build
```

Tests and CI use synthetic boundaries. They do not download neural data, call
the real Codex CLI, or constitute experimental results. The body assets,
workstation, and viewer ship with the package. Rebuild the workstation JavaScript with
`rtk proxy node tools/build_workstation_view.mjs`. The `flycodex` command remains
an alias; internal module names and historical records preserve their original
identity. See the [body provenance and optional rebuild instructions](src/flycodex/web/body/PROVENANCE.md) for pinned sources,
MuJoCo pose checks, and the local viewer build.

- Neural simulation: adapted from [Stonkfly at a pinned revision](https://github.com/nftechie/stonkfly/commit/78ef3e05ab0fa086032098558d893667068944a0), with its original notices retained.
- Body geometry: [TuragaLab/flybody](https://github.com/TuragaLab/flybody), developed by Google DeepMind and HHMI Janelia; Apache-2.0.
- Dataset: [MaleCNS v1.0](https://male-cns.janelia.org/), downloaded separately with its own attribution and license.

New project code is MIT. See [THIRD_PARTY.md](THIRD_PARTY.md),
[neural provenance](src/flycodex/neural/PROVENANCE.md), and the
[original pilot protocol](docs/superpowers/specs/2026-09-13-flycodex-design.md).
