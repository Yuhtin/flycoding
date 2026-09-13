"""Data preparation and a full-graph policy boundary with no global data path.

The preparation code is adapted from Stonkfly revision 78ef3e05ab0fa086032098558d893667068944a0.
It retains every released edge between retained neuronal entries.  The graph and
its visual projection are experimental model inputs, not evidence of cognition
or language ability.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np


UPSTREAM_REVISION = "78ef3e05ab0fa086032098558d893667068944a0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def _locks() -> dict:
    return json.loads(Path(__file__).with_name("sources.lock.json").read_text())


def _transmitter_signs(values) -> np.ndarray:
    signs = []
    for value in values:
        tokens = set(str(value).lower().split(","))
        fast = ({1} if "acetylcholine" in tokens else set()) | ({-1} if tokens & {"gaba", "glutamate", "histamine"} else set())
        signs.append(1 if len(fast) != 1 else fast.pop())
    return np.asarray(signs, dtype=np.int8)


def _verify_graph(graph: Path) -> None:
    expected = json.loads(Path(__file__).with_name("arrays.lock.json").read_text())
    with np.load(graph, allow_pickle=False) as arrays:
        for name, value in expected.items():
            if name not in arrays or hashlib.sha256(arrays[name].tobytes()).hexdigest() != value:
                raise ValueError(f"Compiled graph array provenance mismatch: {name}")


def _obtain_sources(data_dir: Path) -> dict:
    """Verify local source files or resume an authenticated HTTPS curl download."""
    data_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, expected in _locks().items():
        target = data_dir / name
        valid = target.exists() and target.stat().st_size == expected["bytes"] and _sha256(target) == expected["sha256"]
        if not valid:
            partial = target.with_suffix(target.suffix + ".partial")
            subprocess.run(
                ["curl", "--fail", "--location", "--continue-at", "-", "--output", str(partial), expected["url"]],
                check=True,
            )
            if partial.stat().st_size != expected["bytes"] or _sha256(partial) != expected["sha256"]:
                raise ValueError(f"Downloaded {name} failed its pinned integrity check")
            partial.replace(target)
        report[name] = {"bytes": target.stat().st_size, "sha256": _sha256(target), "verified": True}
    return report


def _exact_ids(values) -> np.ndarray:
    values = np.asarray(values)
    if values.dtype.kind == "f":
        raise ValueError("Neuron IDs must be integers, never floats")
    if values.dtype.kind in "iu":
        if np.any(values < 0):
            raise ValueError("Neuron IDs cannot be negative")
        return values.astype(np.uint64)
    text = [str(value) for value in values]
    if any(not item.isascii() or not item.isdecimal() for item in text):
        raise ValueError("Neuron IDs must be nonnegative decimal integers")
    return np.asarray(text, dtype=np.uint64)


def _normalize_and_compile(data_dir: Path, source_hashes: dict) -> dict:
    """Create the retained CSR graph from pinned Arrow sources.

    This intentionally makes no node/edge-strength cut beyond the documented
    source annotations.  Its all-edge sort is resource-intensive and should be
    run only where enough RAM and disk are available.
    """
    import pandas as pd
    import pyarrow as pa
    import pyarrow.feather as feather
    import pyarrow.ipc as ipc

    normalized = data_dir / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    annotations = feather.read_table(data_dir / "annotations.feather").to_pandas()
    transmitters = feather.read_table(data_dir / "neurotransmitters.feather").to_pandas().set_index("body")
    source = _exact_ids(annotations.bodyId)
    retained = annotations.superclass.notna() & annotations.superclass.astype(str).ne("") & annotations.status.ne("Glia")
    if len(np.unique(source)) != len(source):
        raise ValueError("Duplicate source neuron IDs")
    catalog = pd.DataFrame({
        "source_id": source,
        "retained": np.asarray(retained, dtype=bool),
        "cell_type": annotations.type,
        "superclass": annotations.superclass,
        "neurotransmitter": annotations.bodyId.map(transmitters.consensus_nt),
    }).sort_values("source_id", ignore_index=True)
    nodes = catalog.loc[catalog.retained].reset_index(drop=True)
    nodes.insert(0, "node_index", np.arange(len(nodes), dtype=np.uint32))
    feather.write_feather(catalog, normalized / "catalog.feather")
    feather.write_feather(nodes, normalized / "neurons.feather")
    ids = _exact_ids(nodes.source_id)

    reader = ipc.open_file(pa.memory_map(str(data_dir / "edges.feather"), "r"))
    schema = pa.schema([("pre_index", pa.uint32()), ("post_index", pa.uint32()), ("synapse_count", pa.uint32())])
    edge_path = normalized / "edges.arrow"
    temporary = edge_path.with_suffix(".arrow.partial")
    retained_rows = 0
    contacts = 0
    with pa.OSFile(str(temporary), "wb") as sink, ipc.new_file(sink, schema) as writer:
        for number in range(reader.num_record_batches):
            batch = reader.get_batch(number)
            pre, post, count = [batch.column(batch.schema.get_field_index(name)).to_numpy(zero_copy_only=False) for name in ("body_pre", "body_post", "weight")]
            pre, post = _exact_ids(pre), _exact_ids(post)
            first, second = np.searchsorted(ids, pre), np.searchsorted(ids, post)
            keep = (first < len(ids)) & (second < len(ids))
            keep &= ids[np.minimum(first, len(ids) - 1)] == pre
            keep &= ids[np.minimum(second, len(ids) - 1)] == post
            first, second, count = first[keep].astype(np.uint32), second[keep].astype(np.uint32), count[keep].astype(np.uint32)
            retained_rows += len(first)
            contacts += int(count.sum(dtype=np.uint64))
            writer.write_batch(pa.record_batch([pa.array(first), pa.array(second), pa.array(count)], schema=schema))
    temporary.replace(edge_path)

    edges = ipc.open_file(pa.memory_map(str(edge_path), "r")).read_all()
    pre, post, count = [edges.column(name).to_numpy() for name in ("pre_index", "post_index", "synapse_count")]
    order = np.argsort(pre, kind="stable")
    signs = _transmitter_signs(nodes.neurotransmitter)
    ptr = np.r_[0, np.cumsum(np.bincount(pre, minlength=len(nodes)))].astype(np.int64)
    aligned = annotations.set_index("bodyId").loc[nodes.source_id]
    receptor = aligned.type.eq("R1-R6").to_numpy()
    anchors = aligned.type.isin(["L1", "L2", "L3"]).to_numpy() & aligned.assignedOlHex1.notna().to_numpy()
    columns: dict[int, dict[tuple[float, float], int]] = {}
    for i, j, contacts_at_edge in zip(pre[receptor[pre] & anchors[post]], post[receptor[pre] & anchors[post]], count[receptor[pre] & anchors[post]]):
        key = (float(aligned.assignedOlHex1.iloc[j]), float(aligned.assignedOlHex2.iloc[j]))
        columns.setdefault(int(i), {})[key] = columns.setdefault(int(i), {}).get(key, 0) + int(contacts_at_edge)
    retina, hexes, confidence = [], [], []
    for index, votes in sorted(columns.items()):
        retina.append(index)
        selected_hex = max(votes, key=votes.get)
        hexes.append(selected_hex)
        confidence.append(votes[selected_hex] / sum(votes.values()))
    xy = np.asarray([(a - 0.5 * b, np.sqrt(3) / 2 * b) for a, b in hexes])
    retina = np.asarray(retina, dtype=np.int32)
    uv = np.empty_like(xy, dtype=np.float32)
    for side in ("L", "R"):
        mask = aligned.rootSide.to_numpy()[retina] == side
        points = xy[mask]
        scaled = (points - points.min(axis=0)) / (points.max(axis=0) - points.min(axis=0))
        uv[mask, 0] = 0.60 * scaled[:, 0] if side == "L" else 0.40 + 0.60 * (1 - scaled[:, 0])
        uv[mask, 1] = 1 - scaled[:, 1]
    graph_path = data_dir / "graph.npz"
    graph_partial = graph_path.with_suffix(".npz.partial")
    with graph_partial.open("wb") as handle:
        np.savez(handle, ptr=ptr, post=post[order].astype(np.int32), weight=(count[order].astype(np.float32) * signs[pre[order]] * 0.275).astype(np.float32), ids=nodes.source_id.to_numpy(dtype=np.int64), retina=retina, uv=uv, confidence=np.asarray(confidence), hexes=np.asarray(hexes), lamina=np.flatnonzero(aligned.type.isin(["L1", "L2", "L3", "L5"])).astype(np.int32), sugar=np.flatnonzero(aligned.type.eq("LB3c")).astype(np.int32), superclass=np.asarray(nodes.superclass.fillna("unassigned"), dtype="U64"))
    graph_partial.replace(graph_path)
    _verify_graph(graph_path)
    report = {"dataset": "MaleCNS v1.0", "upstream_revision": UPSTREAM_REVISION, "neurons": len(nodes), "edges": retained_rows, "synaptic_contacts": contacts, "retina_mapped": len(retina), "source_hashes": source_hashes, "graph_sha256": _sha256(graph_path), "limitations": "Full retained graph with experimental visual projection and candidate dynamics; not a validated model of fly vision, learning, language, or cognition."}
    _atomic_json(data_dir / "manifest.json", report)
    return report


def prepare_data(data_dir: Path) -> dict:
    """Download, verify, normalize, compile, and verify MaleCNS into data_dir."""
    root = Path(data_dir).expanduser().resolve()
    sources = _obtain_sources(root)
    graph = root / "graph.npz"
    manifest = root / "manifest.json"
    if graph.exists():
        # A verified upstream-compatible graph is reusable even if it was
        # prepared by another process and has an upstream-format manifest.
        _verify_graph(graph)
        report = json.loads(manifest.read_text()) if manifest.exists() else {}
        return {**report, "prepared": False, "sources": sources, "graph_sha256": _sha256(graph)}
    report = _normalize_and_compile(root, sources)
    return {**report, "prepared": True, "sources": sources}


class NeuralPolicy:
    """Run one 500 ms neural observation window and separate feedback window.

    The complete native simulator is intentionally loaded only when a compiled
    graph exists.  No network access occurs during import or policy creation.
    """

    def __init__(self, data_dir: Path, learning: bool):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.learning = bool(learning)
        self._graph = self.data_dir / "graph.npz"
        if not self._graph.exists():
            raise FileNotFoundError(f"Prepared graph required: {self._graph}")
        self._runtime = None

    def _brain(self):
        if self._runtime is None:
            from .runtime import FullGraphRuntime

            self._runtime = FullGraphRuntime(self.data_dir, self.learning)
        return self._runtime

    def _observe(self, rgb: np.ndarray, duration_ms: int, stimulation=None) -> dict:
        from . import decode_counts

        brain = self._brain()
        counts, compute_seconds = brain.window(rgb, duration_ms, stimulation)
        decoded = decode_counts(
            counts, left=brain.left, right=brain.right, gate=brain.gate,
            seconds=duration_ms / 1000,
        )
        return {
            **decoded,
            "cell_ids": brain.cell_ids,
            "input_sha256": hashlib.sha256(np.asarray(rgb).tobytes()).hexdigest(),
            "spike_sha256": hashlib.sha256(counts.tobytes()).hexdigest(),
            "simulated_ms": float(brain.clock[0] * brain.dt),
            "compute_seconds": compute_seconds,
            "total_spikes": int(counts.sum()),
            "memory": brain.memory(),
        }

    def choose(self, rgb: np.ndarray) -> dict:
        """Advance one 500 ms observation window and decode its real spikes."""
        return self._observe(rgb, 500)

    def feedback(self, rgb: np.ndarray, signal: int) -> dict:
        """Deliver one separate 200 ms reward, aversive, or neutral interval."""
        if isinstance(signal, bool) or signal not in (-1, 0, 1):
            raise ValueError("feedback signal must be -1, 0, or 1")
        brain = self._brain()
        target = brain.gate[:0]
        label = "neutral"
        if signal > 0:
            target, label = brain.reward, "reward"
        elif signal < 0:
            target, label = brain.aversive, "aversive"
        result = self._observe(rgb, 200, target)
        return {**result, "signal": int(signal), "stimulus": label, "stimulus_ms": 200 if signal else 0}

    def reset(self, keep_memory: bool = False) -> None:
        if self._runtime is not None:
            self._runtime.reset(bool(keep_memory))

    def save(self, path: Path) -> None:
        brain = self._brain()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = ["weight", "v", "g", "refractory", "drive", "previous_drive", "queue", "queue_count", "clock", "counts", "active", "flags", "nactive", "last", "eligibility", "eligibility_last", "modulation", "modulation_last", "adaptation", "luminance", "r8_light", "rate_kc", "rate_dan", "memory_u", "memory_w"]
        metadata = {"model": "flycodex-full-graph-v1", "learning": self.learning, "graph_ids_sha256": hashlib.sha256(brain.ids.tobytes()).hexdigest(), "graph_ptr_sha256": hashlib.sha256(brain.ptr.tobytes()).hexdigest(), "kernel": brain.build}
        partial = path.with_suffix(path.suffix + ".partial")
        with partial.open("wb") as handle:
            np.savez_compressed(handle, metadata=json.dumps(metadata), **{name: getattr(brain, name) for name in state})
        partial.replace(path)

    def restore(self, path: Path) -> None:
        brain = self._brain()
        with np.load(path, allow_pickle=False) as saved:
            metadata = json.loads(str(saved["metadata"]))
            expected = {"model": "flycodex-full-graph-v1", "learning": self.learning, "graph_ids_sha256": hashlib.sha256(brain.ids.tobytes()).hexdigest(), "graph_ptr_sha256": hashlib.sha256(brain.ptr.tobytes()).hexdigest(), "kernel": brain.build}
            if metadata != expected:
                raise ValueError("Checkpoint provenance mismatch")
            for name in saved.files:
                if name == "metadata":
                    continue
                current = getattr(brain, name)
                if saved[name].shape != current.shape or saved[name].dtype != current.dtype:
                    raise ValueError("Checkpoint array mismatch")
                current[:] = saved[name]

    def memory(self) -> dict:
        return self._brain().memory() if self._runtime is not None else {"initialized": False, "learning": self.learning}


def probe(data_dir: Path, output_dir: Path) -> dict:
    """Probe only a prepared graph; it never invokes Codex."""
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    dark = np.zeros((180, 320, 3), dtype=np.uint8)
    bright = np.full((180, 320, 3), 255, dtype=np.uint8)
    adaptive = NeuralPolicy(data_dir, learning=True)
    dark_response = adaptive.choose(dark)
    bright_response = adaptive.choose(bright)
    before = adaptive.memory()
    feedback = adaptive.feedback(bright, 1)
    after = adaptive.memory()
    checkpoint = output / "probe-checkpoint.npz"
    adaptive.save(checkpoint)
    adaptive.reset()
    adaptive.restore(checkpoint)
    frozen = NeuralPolicy(data_dir, learning=False)
    frozen.choose(bright)
    frozen_before = frozen.memory()
    frozen.feedback(bright, -1)
    frozen_after = frozen.memory()
    report = {
        "codex_invoked": False,
        "dark": dark_response,
        "bright": bright_response,
        "feedback": feedback,
        "adaptive_weight_changed": before["sha256"] != after["sha256"],
        "frozen_weights_identical": frozen_before["sha256"] == frozen_after["sha256"],
        "checkpoint_restored": adaptive.memory()["sha256"] == after["sha256"],
        "limitations": "A response or changed candidate efficacy does not establish task learning, language ability, or cognition.",
    }
    _atomic_json(output / "probe.json", report)
    return report
