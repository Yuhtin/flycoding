#!/usr/bin/env python3
"""Export actual retained soma coordinates as offline brain viewer assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.feather as feather

from flycodex.neural.activity import neuron_order_sha256


VERSION = "flycodex-brain-anatomy-v1"
COORDINATE_DISCLAIMER = (
    "Coordinates are the source somaLocation values in the pinned MaleCNS annotation frame; "
    "they are not registered to the flybody mesh or a physiological atlas."
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and np.isnan(value):
        return ""
    return str(value)


def _readout_indices(ids: np.ndarray, annotations) -> list[dict]:
    rows = {int(row.bodyId): row for row in annotations.itertuples(index=False)}
    output = []
    for index, body_id in enumerate(ids):
        row = rows.get(int(body_id))
        if row is None or _text(getattr(row, "type", "")) not in {"DNp20", "DNpe017"}:
            continue
        output.append({
            "index": index,
            "id": str(int(body_id)),
            "type": _text(getattr(row, "type", "")),
            "side": _text(getattr(row, "somaSide", "")),
        })
    return output


def export_brain(data_dir: Path, output_dir: Path) -> dict:
    """Write manifest and binary/JSON files from an explicit local data directory."""
    data_dir = Path(data_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    graph_path = data_dir / "graph.npz"
    annotation_path = data_dir / "annotations.feather"
    if not graph_path.exists() or not annotation_path.exists():
        raise FileNotFoundError("graph.npz and annotations.feather are required")
    with np.load(graph_path, allow_pickle=False) as graph:
        ids = np.asarray(graph["ids"], dtype=np.int64)
        superclass = np.asarray(graph["superclass"], dtype=str) if "superclass" in graph else np.full(len(ids), "")
    if ids.ndim != 1 or len(superclass) != len(ids) or len(np.unique(ids)) != len(ids):
        raise ValueError("retained graph IDs and classes must be one-to-one")
    annotations = feather.read_table(annotation_path).to_pandas()
    if "bodyId" not in annotations or "somaLocation" not in annotations:
        raise ValueError("annotations must contain bodyId and somaLocation")
    by_id = annotations.drop_duplicates("bodyId").set_index("bodyId")
    normalized_path = data_dir / "normalized" / "neurons.feather"
    if normalized_path.exists():
        normalized = feather.read_table(normalized_path).to_pandas()
        if "source_id" not in normalized or not np.array_equal(normalized["source_id"].to_numpy(), ids):
            raise ValueError("normalized neuron order does not match retained graph IDs")

    positions: list[list[float]] = []
    retained_indices: list[int] = []
    neurons = []
    for index, body_id in enumerate(ids):
        row = by_id.loc[int(body_id)] if int(body_id) in by_id.index else None
        location = None if row is None else row.get("somaLocation")
        try:
            coordinates = np.asarray(location, dtype=np.float32)
        except (TypeError, ValueError):
            coordinates = np.empty(0, dtype=np.float32)
        if coordinates.shape == (3,) and np.isfinite(coordinates).all():
            positions.append([float(value) for value in coordinates])
            retained_indices.append(index)
        neurons.append({
            "id": int(body_id),
            "type": "" if row is None else _text(row.get("type")),
            "class": "" if row is None else _text(row.get("class")),
            "superclass": _text(superclass[index]),
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    positions_bytes = np.asarray(positions, dtype="<f4").reshape((-1, 3)).tobytes(order="C")
    indices_bytes = np.asarray(retained_indices, dtype="<u4").tobytes(order="C")
    (output_dir / "positions.bin").write_bytes(positions_bytes)
    (output_dir / "indices.bin").write_bytes(indices_bytes)
    neurons_bytes = (json.dumps(neurons, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    (output_dir / "neurons.json").write_bytes(neurons_bytes)

    source_paths = {
        "graph.npz": graph_path,
        "annotations.feather": annotation_path,
        "normalized/neurons.feather": data_dir / "normalized" / "neurons.feather",
    }
    source_hashes = {name: _sha256_file(path) for name, path in source_paths.items() if path.exists()}
    order_hash = neuron_order_sha256(ids)
    files = {
        name: {"bytes": (output_dir / name).stat().st_size, "sha256": _sha256_file(output_dir / name)}
        for name in ("positions.bin", "indices.bin", "neurons.json")
    }
    manifest = {
        "version": VERSION,
        "total_neurons": len(ids),
        "positioned_neurons": len(retained_indices),
        "missing_neurons": len(ids) - len(retained_indices),
        "neuron_order_sha256": order_hash,
        "order_sha256": order_hash,
        "source_hashes": source_hashes,
        "coordinate_disclaimer": COORDINATE_DISCLAIMER,
        "readout_indices": _readout_indices(ids, annotations),
        "files": files,
        "classes": sorted(set(str(value) for value in superclass if str(value))),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("src/flycodex/web/brain"))
    args = parser.parse_args(argv)
    export_brain(args.data_dir, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
