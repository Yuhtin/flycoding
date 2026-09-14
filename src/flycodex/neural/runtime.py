"""Explicit-data-dir wrapper around the vendored full-graph C++ integrator."""

from __future__ import annotations

import ctypes as C
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.feather as feather

from .rule import advance
from .activity import make_bin, neuron_order_sha256


def _digest(array: np.ndarray) -> str:
    return hashlib.sha256(array.tobytes()).hexdigest()


def _build(data_dir: Path) -> tuple[Path, dict]:
    source = Path(__file__).with_name("kernel.cpp")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    library = data_dir / "cache" / ("libmemory.dylib" if sys.platform == "darwin" else "libmemory.so")
    record = library.with_suffix(library.suffix + ".json")
    if library.exists() and record.exists():
        metadata = json.loads(record.read_text())
        if metadata.get("source_sha256") == digest and metadata.get("binary_sha256") == hashlib.sha256(library.read_bytes()).hexdigest():
            return library, metadata
    library.parent.mkdir(parents=True, exist_ok=True)
    partial = library.with_suffix(library.suffix + ".partial")
    subprocess.run(["c++", "-O3", "-std=c++17", "-shared", "-fPIC", str(source), "-o", str(partial)], check=True)
    partial.replace(library)
    metadata = {"source_sha256": digest, "binary_sha256": hashlib.sha256(library.read_bytes()).hexdigest(), "flags": ["-O3", "-std=c++17", "-shared", "-fPIC"]}
    temporary = record.with_suffix(record.suffix + ".partial")
    temporary.write_text(json.dumps(metadata, indent=2) + "\n")
    temporary.replace(record)
    return library, metadata


class FullGraphRuntime:
    """All graph dynamics live here; policy code never accesses raw arrays directly."""

    dt = 0.1

    def __init__(self, data_dir: Path, learning: bool):
        self.data_dir = data_dir
        with np.load(data_dir / "graph.npz", allow_pickle=False) as graph:
            for name in ("ptr", "post", "weight", "ids", "retina", "uv", "hexes", "lamina", "sugar"):
                setattr(self, name, np.array(graph[name], copy=True))
        self.n = len(self.ids)
        self.neuron_order_sha256 = neuron_order_sha256(self.ids)
        self.weight = self.weight.astype(np.float32, copy=False)
        if self.ptr.shape != (self.n + 1,) or self.ptr[-1] != len(self.post):
            raise ValueError("Invalid CSR graph")
        annotations = feather.read_table(data_dir / "annotations.feather").to_pandas().set_index("bodyId").loc[self.ids]
        transmitters = feather.read_table(data_dir / "normalized" / "neurons.feather").to_pandas().set_index("source_id").loc[self.ids].neurotransmitter
        types = annotations.type.fillna("")
        self.left = np.flatnonzero(types.eq("DNp20") & annotations.somaSide.fillna("").eq("L")).astype(np.int32)
        self.right = np.flatnonzero(types.eq("DNp20") & annotations.somaSide.fillna("").eq("R")).astype(np.int32)
        self.gate = np.flatnonzero(types.eq("DNpe017")).astype(np.int32)
        if not len(self.left) or not len(self.right) or not len(self.gate):
            raise ValueError("Missing annotated BCI outputs")
        self.cell_ids = {"left": [str(self.ids[i]) for i in self.left], "right": [str(self.ids[i]) for i in self.right], "gate": [str(self.ids[i]) for i in self.gate]}
        # Preserve Stonkfly's R8 display adapter. Its geometry is inferred from
        # existing contacts and the already-compiled R1-R6 viewport, never from
        # a separate arbitrary eye projection.
        known = np.flatnonzero(types.isin(["R8p", "R8y"]))
        mapped, r8_hexes = [], []
        for index in known:
            edges = np.arange(self.ptr[index], self.ptr[index + 1])
            targets = self.post[edges]
            valid = annotations.assignedOlHex1.iloc[targets].notna().to_numpy() & annotations.assignedOlHex2.iloc[targets].notna().to_numpy()
            votes = {}
            for edge, target in zip(edges[valid], targets[valid]):
                key = (float(annotations.assignedOlHex1.iloc[target]), float(annotations.assignedOlHex2.iloc[target]))
                votes[key] = votes.get(key, 0.0) + float(abs(self.weight[edge]))
            if votes:
                mapped.append(index); r8_hexes.append(max(votes, key=votes.get))
        self.r8 = np.asarray(mapped, dtype=np.int32)
        r8_xy = np.asarray([(a - 0.5 * b, np.sqrt(3) / 2 * b) for a, b in r8_hexes])
        old_xy = np.column_stack([self.hexes[:, 0] - 0.5 * self.hexes[:, 1], np.sqrt(3) / 2 * self.hexes[:, 1]])
        self.r8_uv = np.empty_like(r8_xy, dtype=np.float32)
        for side in ("L", "R"):
            original = annotations.rootSide.iloc[self.retina].eq(side).to_numpy()
            selected_side = annotations.rootSide.iloc[self.r8].eq(side).to_numpy()
            low, span = old_xy[original].min(axis=0), np.ptp(old_xy[original], axis=0)
            scaled = (r8_xy[selected_side] - low) / span
            self.r8_uv[selected_side, 0] = 0.60 * scaled[:, 0] if side == "L" else 0.40 + 0.60 * (1 - scaled[:, 0])
            self.r8_uv[selected_side, 1] = 1 - scaled[:, 1]
        self.r8_uv = np.clip(self.r8_uv, 0, 1)
        self.r8_channel = np.where(types.iloc[self.r8].eq("R8p"), 2, 1).astype(np.int32)
        self.r8_light = np.zeros(len(self.r8), dtype=np.float32)
        corrected_edges = []
        for index in np.flatnonzero(types.str.startswith("R8")):
            edges = np.arange(self.ptr[index], self.ptr[index + 1])
            corrected = edges[types.iloc[self.post[edges]].eq("aMe12").to_numpy()]
            corrected_edges.extend(corrected.tolist())
            self.weight[corrected] = np.abs(self.weight[corrected])
        self.corrected_edges = np.asarray(corrected_edges, dtype=np.int64)
        kc = np.flatnonzero(types.str.startswith("KC")).astype(np.int32)
        reward = np.flatnonzero(types.eq("PAM11")).astype(np.int32)
        aversive = np.flatnonzero(types.eq("PPL101")).astype(np.int32)
        self.reward, self.aversive = reward, aversive
        mb = np.r_[np.flatnonzero(types.eq("MBON07")), np.flatnonzero(types.eq("MBON11"))].astype(np.int32)
        selected = np.flatnonzero(np.isin(self.post, mb)).astype(np.int64)
        pre = (np.searchsorted(self.ptr, selected, side="right") - 1).astype(np.int32)
        keep = np.isin(pre, kc)
        self.plastic_edges, self.plastic_pre = selected[keep], pre[keep]
        if not len(self.plastic_edges):
            raise ValueError("Missing reconstructed KC-to-MBON plastic edges")
        self.baseline_plastic = self.weight[self.plastic_edges].copy()
        dan = np.r_[reward, aversive].astype(np.int32)
        self.gain = np.zeros((len(dan), len(self.plastic_edges)), dtype=np.float32)
        for targets, drivers in ((mb[: len(np.flatnonzero(types.eq("MBON07")))], reward), (mb[len(np.flatnonzero(types.eq("MBON07"))):], aversive)):
            for target in targets:
                contacts = np.asarray([np.abs(self.weight[self.ptr[d]:self.ptr[d + 1]][self.post[self.ptr[d]:self.ptr[d + 1]] == target]).sum() for d in drivers])
                if contacts.sum() <= 0:
                    raise ValueError("Missing direct DAN-to-MBON anatomical support")
                output = np.flatnonzero(self.post[self.plastic_edges] == target)
                for driver, value in zip(drivers, contacts / contacts.sum()):
                    self.gain[np.flatnonzero(dan == driver)[0], output] = value
        self.kc_mask = np.zeros(self.n, dtype=np.uint8); self.kc_mask[kc] = 1
        self.dan_index = np.full(self.n, -1, dtype=np.int8); self.dan_index[dan] = np.arange(len(dan))
        self.learning = learning
        self.rest = np.full(self.n, -52, dtype=np.float32); self.rest[kc] = -60
        self.v = self.rest.copy(); self.g = np.zeros(self.n, dtype=np.float32); self.refractory = np.zeros(self.n, dtype=np.int16)
        self.drive = np.zeros(self.n, dtype=np.float32); self.previous_drive = np.zeros(self.n, dtype=np.float32)
        self.queue = np.zeros((19, self.n), dtype=np.int32); self.queue_count = np.zeros(19, dtype=np.int32); self.clock = np.zeros(1, dtype=np.int64)
        self.counts = np.zeros(self.n, dtype=np.int32); self.active = np.zeros(self.n, dtype=np.int32); self.flags = np.zeros(self.n, dtype=np.uint8)
        initial = np.unique(np.r_[self.retina, self.lamina, self.sugar]); self.active[:len(initial)] = initial; self.flags[initial] = 1; self.nactive = np.asarray([len(initial)], dtype=np.int32)
        self.last = np.full(self.n, -1, dtype=np.int64); self.eligibility = np.zeros(self.n, dtype=np.float64); self.eligibility_last = np.zeros(self.n, dtype=np.int64)
        self.modulation = np.zeros(self.n, dtype=np.float32); self.modulation_last = np.zeros(self.n, dtype=np.int64); self.modulation_mask = transmitters.isin(["dopamine", "octopamine", "serotonin"]).to_numpy(dtype=np.uint8); self.adaptation = np.zeros(self.n, dtype=np.float32)
        self.luminance = np.zeros(len(self.retina), dtype=np.float32); self.rate_kc = np.zeros(len(self.plastic_edges)); self.rate_dan = np.zeros(len(dan)); self.memory_u = np.zeros(len(self.plastic_edges)); self.memory_w = np.zeros(len(self.plastic_edges)); self.initial_weight = self.weight.copy()
        library, self.build = _build(data_dir); self.advance = C.CDLL(str(library)).memory_advance
        self.advance.argtypes = [C.c_int] + [C.c_void_p] * 11 + [C.c_int, C.c_float] + [C.c_void_p] * 9 + [C.c_int] + [C.c_void_p] * 4 + [C.c_float, C.c_float, C.c_float, C.c_int] + [C.c_void_p] * 5 + [C.c_float, C.c_float]

    def _pointers(self, arrays):
        return [C.c_void_p(array.ctypes.data) for array in arrays]

    def window(
        self,
        rgb: np.ndarray,
        duration_ms: int,
        stimulation: np.ndarray | None = None,
        on_bin=None,
    ) -> tuple[np.ndarray, float]:
        frame = np.asarray(rgb)
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError("RGB uint8 frame required")
        x = np.clip((self.uv[:, 0] * (frame.shape[1] - 1)).astype(int), 0, frame.shape[1] - 1); y = np.clip((self.uv[:, 1] * (frame.shape[0] - 1)).astype(int), 0, frame.shape[0] - 1)
        pixel = frame[y, x].astype(np.float32) / 255; linear = np.where(pixel <= 0.04045, pixel / 12.92, ((pixel + 0.055) / 1.055) ** 2.4); light = linear @ np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
        r8_x = np.clip((self.r8_uv[:, 0] * (frame.shape[1] - 1)).astype(int), 0, frame.shape[1] - 1); r8_y = np.clip((self.r8_uv[:, 1] * (frame.shape[0] - 1)).astype(int), 0, frame.shape[0] - 1)
        r8_pixel = frame[r8_y, r8_x, self.r8_channel].astype(np.float32) / 255
        r8_values = np.where(r8_pixel <= 0.04045, r8_pixel / 12.92, ((r8_pixel + 0.055) / 1.055) ** 2.4)
        total = np.zeros(self.n, dtype=np.int32); elapsed = 0.0
        for _ in range(round(duration_ms / 10)):
            start_ms = float(self.clock[0] * self.dt)
            self.luminance += (1 - np.exp(-1)) * (light - self.luminance); self.r8_light += (1 - np.exp(-1)) * (r8_values - self.r8_light); self.drive.fill(0); self.drive[self.lamina] = 12; self.drive[self.retina] = 30 * self.luminance / (0.02 + self.luminance); self.drive[self.r8] += 30 * self.r8_light / (0.02 + self.r8_light)
            if stimulation is not None: self.drive[stimulation] += 20
            self.counts.fill(0); start = time.perf_counter()
            self.advance(self.n, *self._pointers([self.ptr, self.post, self.weight, self.v, self.g, self.refractory, self.drive, self.previous_drive, self.queue, self.queue_count, self.clock]), 100, self.dt, *self._pointers([self.counts, self.active, self.flags, self.nactive, self.last, self.kc_mask, self.dan_index, self.eligibility, self.eligibility_last]), len(self.plastic_edges), *self._pointers([self.plastic_edges, self.plastic_pre, self.baseline_plastic, self.gain]), 0.001, 1000.0, 0.1, 0, *self._pointers([self.modulation, self.modulation_last, self.modulation_mask, self.rest, self.adaptation]), 8.0, 200.0)
            elapsed += time.perf_counter() - start; seconds = 0.01; advance(self.rate_kc, self.rate_dan, self.memory_u, self.memory_w, self.counts[self.plastic_pre] / seconds, self.counts[np.flatnonzero(self.dan_index >= 0)] / seconds, self.gain, seconds, 0.001, learning=self.learning, frozen=not self.learning)
            if self.learning: self.weight[self.plastic_edges] = self.baseline_plastic * (1 + self.memory_w)
            total += self.counts
            if on_bin is not None:
                on_bin(make_bin(start_ms, float(self.clock[0] * self.dt), self.counts))
        return total, elapsed

    def memory(self) -> dict:
        values = self.weight[self.plastic_edges] / self.baseline_plastic
        return {"plastic_edges": len(values), "changed_edges": int(np.count_nonzero(self.weight[self.plastic_edges] != self.baseline_plastic)), "mean_efficacy": float(values.mean()), "minimum_efficacy": float(values.min()), "sha256": _digest(self.weight[self.plastic_edges]), "weights_frozen": not self.learning}

    def configuration_signature(self) -> dict:
        return {
            "initial_weight": _digest(self.initial_weight),
            "baseline_plastic": _digest(self.baseline_plastic),
            "rest": _digest(self.rest),
            "modulation_mask": _digest(self.modulation_mask),
            "retina": _digest(self.retina),
            "uv": _digest(self.uv),
            "lamina": _digest(self.lamina),
            "sugar": _digest(self.sugar),
            "r8": _digest(self.r8),
            "r8_uv": _digest(self.r8_uv),
            "r8_channel": _digest(self.r8_channel),
            "corrected_edges": _digest(self.corrected_edges),
            "plastic_pre": _digest(self.plastic_pre),
            "gain": _digest(self.gain),
            "kc_mask": _digest(self.kc_mask),
            "dan_index": _digest(self.dan_index),
            "rule_sha256": hashlib.sha256(Path(__file__).with_name("rule.py").read_bytes()).hexdigest(),
            "dt_ms": self.dt,
        }

    def reset(self, keep_memory: bool) -> None:
        saved = self.weight[self.plastic_edges].copy(), self.memory_u.copy(), self.memory_w.copy()
        self.__init__(self.data_dir, self.learning)
        if keep_memory: self.weight[self.plastic_edges], self.memory_u, self.memory_w = saved
