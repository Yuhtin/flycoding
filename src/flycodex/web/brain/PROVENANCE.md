# MaleCNS anatomical point assets

These assets are derived from the [MaleCNS v1.0 dataset](https://male-cns.janelia.org/),
a collaboration between FlyEM at HHMI Janelia, the University of Cambridge
Department of Zoology, the MRC Laboratory of Molecular Biology, and Google Research.
The dataset is provided under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
This attribution and license apply to the derived data; the project's MIT license
does not replace them. See the [associated publication](https://www.cell.com/cell/fulltext/S0092-8674%2826%2900942-6).

`tools/export_brain.py` reads the locally prepared retained graph and pinned
annotations. Source hashes, derived file hashes, the retained-order hash, and
output-neuron mappings are recorded in `manifest.json`. Original download URLs
and checksums are in `src/flycodex/neural/sources.lock.json`.

The export keeps 166,700 retained neuron IDs and their type/class metadata.
It converts the 139,662 finite source soma positions to little-endian float32
XYZ triples in `positions.bin`, with matching retained offsets as little-endian
uint32 values in `indices.bin`. The 27,038 unplaced neurons remain in metadata
but receive no position. `neurons.json` follows the full retained graph order.

These are source soma positions, not complete neuron skeletons. Coordinates
remain in the source coordinate system; they are not registered into the
flybody head or converted into its physical model units. Browser framing and
color are presentation choices. Activity is experimental simulated spike data
measured separately at runtime, not an anatomical dataset measurement.

Rebuild from verified local data:

```sh
rtk proxy uv run python tools/export_brain.py --data-dir data --output-dir src/flycodex/web/brain
```

Normal package installation includes the derived assets and does not run the
exporter or download the full connectome. No endorsement by the source authors
is implied.
