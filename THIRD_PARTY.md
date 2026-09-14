# Third-party notices

- The neural importer, graph compiler, visual projection, C++ spiking kernel,
  and candidate plasticity rule are adapted from Stonkfly revision
  `78ef3e05ab0fa086032098558d893667068944a0`, itself derived from DOOMFLY.
  Copyright © 2026 nftechie and DOOMFLY contributors; MIT licence in
  [LICENSE](LICENSE). Exact file provenance and adaptations are in
  [`src/flycodex/neural/PROVENANCE.md`](src/flycodex/neural/PROVENANCE.md).
- The full [MaleCNS v1.0](https://male-cns.janelia.org/) graph is downloaded separately
  from the MaleCNS collaboration (FlyEM at HHMI Janelia, University of
  Cambridge, MRC Laboratory of Molecular Biology, and Google Research)
  under the release's [CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/).
  The project page links the [associated Cell publication](https://www.cell.com/cell/fulltext/S0092-8674%2826%2900942-6).
  The source URLs, byte lengths, and
  SHA-256 hashes are pinned in `src/flycodex/neural/sources.lock.json`.
  The compiled graph and experimental dynamics are derived interpretations,
  not an official dataset product. The package includes derived soma positions
  and neuron metadata under the same CC BY 4.0 terms; attribution and export
  changes are documented in [brain provenance](src/flycodex/web/brain/PROVENANCE.md).
- No trading, brokerage, market-data, or Codex client dependency is included.
- The articulated browser model uses the actual visual meshes from
  [TuragaLab/flybody](https://github.com/TuragaLab/flybody), revision
  `d015e9bfe441bd90ae431bac24c55cb74bdbce26`, under Apache-2.0.
  Source hashes, geometry changes, motion conventions and the full license are
  in [`src/flycodex/web/body/`](src/flycodex/web/body/PROVENANCE.md).
  Its motion is procedural MuJoCo forward kinematics, not learned locomotion.
- The local browser bundle includes Three.js 0.180.0 and its GLTFLoader and
  OrbitControls modules under the MIT license, retained in
  [`LICENSE.three`](src/flycodex/web/body/LICENSE.three). The optional build tool
  uses esbuild 0.25.10. Neither npm nor MuJoCo is needed to view the dashboard.
