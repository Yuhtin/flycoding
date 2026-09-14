# Brain visualization: upstream scope and usable MaleCNS anatomy

Checked 2026-09-14. Read-only upstream audit; no simulation, bulk dataset download, or production changes. Source revisions: flybody `d015e9bfe441bd90ae431bac24c55cb74bdbce26`; stonkfly `78ef3e05ab0fa086032098558d893667068944a0`.

## What flybody actually supplies

`TuragaLab/flybody` supplies an anatomical **body** for MuJoCo and locomotion reinforcement-learning tasks. Its basic example renders the body under random actions. Its stated ambition includes embodied neural-control research, but that does not mean it includes a biological brain controller. [README](https://github.com/TuragaLab/flybody/blob/d015e9bfe441bd90ae431bac24c55cb74bdbce26/README.md)

The shipped D4PG/DMPO policy factories build LayerNorm MLPs, with default policy layers `(256, 256, 256)`. Vision-guided flight adds a convolutional visual network and a high-level MLP controlling a frozen locomotion policy. These are artificial policy networks, not MaleCNS neurons or connectome wiring. [Policy factory](https://github.com/TuragaLab/flybody/blob/d015e9bfe441bd90ae431bac24c55cb74bdbce26/flybody/agents/network_factory.py), [vision controller](https://github.com/TuragaLab/flybody/blob/d015e9bfe441bd90ae431bac24c55cb74bdbce26/flybody/agents/network_factory_vis.py)

The inspected README, recursive source tree and notebooks provide body rendering, rollout tasks and sensory/action tracking; I found no included biological brain/connectome viewer. Its tracking notebook is useful for instrumenting body observations and actions, not a ready-made visualization of connectome activity. [Tracking notebook](https://github.com/TuragaLab/flybody/blob/d015e9bfe441bd90ae431bac24c55cb74bdbce26/docs/sensory-input-tracking.ipynb)

Pretrained policies are offered, beyond training code: the official [download helper](https://github.com/TuragaLab/flybody/blob/d015e9bfe441bd90ae431bac24c55cb74bdbce26/flybody/download_data.py) points to `trained-policies`; [Figshare metadata](https://api.figshare.com/v2/articles/25309105) lists `trained-fly-policies.zip` (6,537,720 bytes). The [environment notebook](https://github.com/TuragaLab/flybody/blob/d015e9bfe441bd90ae431bac24c55cb74bdbce26/docs/fly-env-examples.ipynb) explicitly loads a walking SavedModel. The separate walking-imitation dataset is approximately 3 GB. Archive contents and runtime compatibility were not tested; a download-URL HEAD probe ended in HTTP 403. Therefore a published walking-policy path exists, but successful retrieval/execution here is not established. It would remain a learned motor controller, not proof that MaleCNS directly controls locomotion.

Stonkfly is a separate wiring-constrained LIF simulation. Its documented retained MaleCNS graph contains 166,700 neurons and 25,582,938 directed connections. Its physiology and action decoder are engineered approximations; its documentation explicitly distinguishes anatomy from validated biological dynamics. Its `visual.py` implements retinal display sampling, not a spatial brain renderer. [Model](https://github.com/nftechie/stonkfly/blob/78ef3e05ab0fa086032098558d893667068944a0/docs/model.md), [visual adapter](https://github.com/nftechie/stonkfly/blob/78ef3e05ab0fa086032098558d893667068944a0/stonkfly/neural/visual.py)

## First-party anatomy and viewers

MaleCNS offers actual reconstructed morphology. The official download page documents per-body SWC skeletons in MaleCNS coordinates with **8 nm units**, Neuroglancer skeletons with **1 nm units**, and transformed skeletons in JRC2018 unisex space with **micron units**. NeuPrint/navis can fetch selected neurons; neuPrint requires an account/token. Bulk synaptic coordinates exist but are unnecessary for an initial viewer. The dataset is CC-BY. [Download documentation](https://male-cns.janelia.org/download/)

The official Neuroglancer scene exposes these useful sources (prefix `gs://flyem-male-cns/`):

| Asset | Source path |
| --- | --- |
| Individual neuron skeleton | `v1.0/segmentation/skeletons-malecns/skeletons-swc/{bodyId}.swc` |
| Native neuron meshes | `v1.0/segmentation/meshes-malecns/single-res-meshes` |
| Brain outline | `rois/brain-shell-v2.2` |
| Major brain neuropil outlines | `rois/fullbrain-major-shells` |
| VNC outline | `rois/vnc-shell-v2` |
| Soma annotations, linked to body IDs | `v1.0/malecns-v1.0-soma-points` |

Paths were inspected in the [official scene JSON](https://storage.googleapis.com/flyem-male-cns/v1.0/male-cns-v1.0.json). Soma [metadata](https://storage.googleapis.com/flyem-male-cns/v1.0/malecns-v1.0-soma-points/info) distinguishes nucleus and `tosoma` point kinds and provides a `body` relationship; do not treat every annotation as an interchangeable soma.

An unauthenticated HTTP HEAD check returned 200 for [neuron 12781's SWC](https://storage.googleapis.com/flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/12781.swc), reporting 552,929 bytes. Skeleton and segmentation metadata also returned 200. This confirms selective public access; it does not establish coverage for every retained neuron. A HEAD request with a localhost Origin did not return an allow-origin header, so browser fetching remains unverified; preprocessing or serving selected assets locally avoids depending on browser CORS.

For an immediate anatomical reference, use the [official Neuroglancer scene](https://neuroglancer-demo.appspot.com/#!gs://flyem-male-cns/v1.0/male-cns-v1.0.json). It supports morphology, neuropil outlines and selected synaptic sites. [Official viewer guide](https://male-cns.janelia.org/explore/). The first-party [Cell Type Explorer](https://reiserlab.github.io/celltype-explorer-drosophila-male-cns/) adds searchable morphology, connectivity and spatial distributions. These display structural data; none supplies Flycodex's runtime activity.

## Local audit supplied by the parent agent

The existing `data/annotations.feather` already contains `bodyId`, `superclass`, and `somaLocation`. Joining the retained 166,700 IDs gives **139,662 valid anatomical positions and 27,038 missing**. All four current descending-neuron outputs have positions. An initial anatomical point cloud therefore needs no additional download. Missing positions must remain explicitly unplaced. The parent agent generated a [static anatomical preview](brain-anatomy-preview.png) from these coordinates; it depicts anatomy only, with no activity data.

The runtime computes per-neuron counts in 10 ms windows but returns an aggregate; exported policy traces retain total counts, hashes and output-group IDs, not temporal per-neuron activity. The brain advances around decision calls and pauses during the coding runner. Existing recordings therefore cannot support a faithful full-brain spike animation. See [runtime](../../src/flycodex/neural/runtime.py), [policy](../../src/flycodex/neural/policy.py), and [pilot](../../src/flycodex/pilot.py); these findings are from the parallel local audit, not independently rerun here.

## Recommendation

Make the brain the primary interactive view: existing measured soma positions, a real anatomical outline, and selected-neuron skeletons on demand. Show identity/type on selection and highlight the actual input/output groups. Keep body visualization as a separate consequence of the controller.

Instrument bounded per-neuron spike-count bins with body IDs and simulation timestamps before animating activity. Brightness can encode measured simulated firing rate; show its units and bin width. Surface current input, neural response and decoded action together. Distinguish running, paused and recorded playback, and label this as simulated activity over reconstructed anatomy.

A point-neuron spike can color its anatomical skeleton as a display convention; it cannot establish where a spike travels along branches. Skeleton parent-child order is not reliable physiological direction. [neuPrint skeleton documentation](https://connectome-neuprint.github.io/neuprint-python/docs/skeleton.html). Avoid traveling synaptic particles without recorded/modelled propagation, arbitrary coordinates presented as anatomy, and pulses generated from total-spike counts or a fixed narrative. Historical aggregate traces should show the aggregate they contain.

Unresolved implementation checks: local coordinate units/orientation; soma-versus-neuropil coverage; missing-position handling; per-body geometry coverage and licensing attribution; telemetry payload/storage limits; and the transform needed to place MaleCNS anatomy inside the separate flybody model. No registration between those specimens was established by this audit.
