# /// script
# requires-python = ">=3.11"
# dependencies = ["mujoco==3.3.7", "numpy==2.3.3", "fast-simplification==0.1.12"]
# ///
"""Export pinned flybody visual meshes and procedural MuJoCo forward kinematics.

Run: uv run tools/export_flybody.py
Sources are cached in ignored build/flybody-source; no training stack is required.
The source lock is verified before compilation. --write-source-lock is only for
deliberately bootstrapping a reviewed source revision, never normal rebuilding.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import xml.etree.ElementTree as ET

import fast_simplification
import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src/flycodex/web/body"
REVISION = "d015e9bfe441bd90ae431bac24c55cb74bdbce26"
BASE = f"https://raw.githubusercontent.com/TuragaLab/flybody/{REVISION}/"
ASSETS = "flybody/fruitfly/assets/"


def digest(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def acquire(cache, write_lock):
    lock_path = OUT / "sources.lock.json"
    known = {} if write_lock else {s["path"]: s for s in json.loads(lock_path.read_text())}

    def fetch(path):
        target = cache / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--retry", "3",
                            BASE + path, "--output", str(target)], check=True)
        info = {"path": path, **digest(target.read_bytes())}
        if not write_lock and info != known.get(path):
            raise ValueError(f"Source integrity mismatch: {path}")
        return info

    xml_info = fetch(ASSETS + "fruitfly.xml")
    xml_path = cache / xml_info["path"]
    xml = ET.parse(xml_path)
    paths = sorted({ASSETS + mesh.attrib["file"] for mesh in xml.findall("asset/mesh")} | {"LICENSE"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        sources = [xml_info, *pool.map(fetch, paths)]
    if write_lock:
        lock_path.write_text(json.dumps(sources, indent=2) + "\n")
    (OUT / "LICENSE.flybody").write_bytes((cache / "LICENSE").read_bytes())
    return xml_path, sources


def quaternion(matrix):
    q = np.empty(4)
    mujoco.mju_mat2Quat(q, np.asarray(matrix).reshape(9))
    return q[[1, 2, 3, 0]]


def body_pose(model, data, body):
    parent = model.body_parentid[body]
    rotation = data.xmat[body].reshape(3, 3)
    parent_rotation = data.xmat[parent].reshape(3, 3)
    return np.concatenate((parent_rotation.T @ (data.xpos[body] - data.xpos[parent]),
                           quaternion(parent_rotation.T @ rotation)))


def procedural_qpos(model, mode, phase):
    """Bounded authored joint motion; no dynamics rollout or learned policy."""
    qpos = model.qpos0.copy()
    activity = {"idle": 0.15, "working": 1.0, "success": 0.7, "failure": 0.4}[mode]
    for joint in range(model.njnt):
        if model.jnt_type[joint] != mujoco.mjtJoint.mjJNT_HINGE:
            continue
        name = model.joint(joint).name
        side = 1 if "left" in name else -1
        phase_offset = (0 if "T1" in name else 2.1 if "T2" in name else 4.2) + side * 0.8
        value = qpos[model.jnt_qposadr[joint]]
        if name.startswith("wing_"):
            if "yaw" in name:
                value = 1.25 - activity * 0.30 * (1 + np.sin(phase + side * 0.7))
            elif "roll" in name:
                value = 0.65 + activity * 0.20 * np.sin(phase + side * 0.7)
            elif "pitch" in name:
                value = -0.95 + activity * 0.18 * np.cos(phase + side * 0.7)
        elif name.startswith("head"):
            value += activity * (0.12 if name == "head" else 0.07) * np.sin(phase)
        elif name.startswith("antenna"):
            value += (0.08 + activity * 0.16) * np.sin(phase * 2 + side)
        elif name.startswith("abdomen"):
            value += (0.01 + activity * 0.015) * np.sin(phase)
        elif name.startswith("coxa"):
            value += activity * 0.16 * np.sin(phase * 2 + phase_offset)
        elif name.startswith("femur"):
            value += activity * 0.24 * np.sin(phase * 2 + phase_offset)
        elif name.startswith("tibia"):
            value += activity * 0.30 * np.sin(phase * 2 + phase_offset + 1.2)
        elif name.startswith("tarsus"):
            value += activity * 0.12 * np.sin(phase * 2 + phase_offset + 1.6)
        if mode == "success" and name == "head":
            value += 0.12 * np.sin(phase)
        if mode == "failure" and name == "head_twist":
            value += 0.15 * np.sin(phase * 2)
        if model.jnt_limited[joint]:
            value = np.clip(value, *model.jnt_range[joint])
        qpos[model.jnt_qposadr[joint]] = value
    return qpos


def write_motion(model):
    data = mujoco.MjData(model)
    bodies = [{"name": model.body(i).name, "parent": int(model.body_parentid[i]) - 1}
              for i in range(1, model.nbody)]
    joints = [{"name": model.joint(i).name, "qpos_address": int(model.jnt_qposadr[i]),
               "limited": bool(model.jnt_limited[i]), "range": model.jnt_range[i].tolist()}
              for i in range(model.njnt)]
    motion = {"version": 1, "convention": "parent-local XYZ, quaternion XYZW; source Z-up, centimeters",
              "bodies": bodies, "joints": joints, "clips": {}}
    for mode, duration in (("idle", 6), ("working", 2.4), ("success", 2.0), ("failure", 2.4)):
        frames, qposes = [], []
        for frame in range(48):
            data.qpos[:] = procedural_qpos(model, mode, frame / 48 * np.pi * 2)
            mujoco.mj_forward(model, data)
            poses = np.concatenate([body_pose(model, data, i) for i in range(1, model.nbody)])
            assert np.isfinite(poses).all()
            frames.append(poses.round(7).tolist())
            qposes.append(data.qpos.round(7).tolist())
        motion["clips"][mode] = {"duration": duration, "frames": frames, "qpos": qposes}
    (OUT / "motion.json").write_text(json.dumps(motion, separators=(",", ":")) + "\n")
    return motion


def write_glb(model, motion):
    document = {"asset": {"version": "2.0", "generator": "flycodex pinned MuJoCo exporter"},
                "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [], "meshes": [],
                "materials": [], "buffers": [], "bufferViews": [], "accessors": []}
    binary = bytearray()

    def accessor(array, kind, component, target):
        array = np.ascontiguousarray(array)
        while len(binary) % 4:
            binary.append(0)
        view = len(document["bufferViews"])
        document["bufferViews"].append({"buffer": 0, "byteOffset": len(binary),
                                         "byteLength": array.nbytes, "target": target})
        binary.extend(array.tobytes())
        info = {"bufferView": view, "componentType": component, "count": len(array), "type": kind}
        if kind == "VEC3":
            info.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        document["accessors"].append(info)
        return len(document["accessors"]) - 1

    for material in range(model.nmat):
        rgba = model.mat_rgba[material].tolist()
        document["materials"].append({"name": model.material(material).name,
            "pbrMetallicRoughness": {"baseColorFactor": rgba, "metallicFactor": 0,
                                      "roughnessFactor": 0.46 if rgba[3] == 1 else 0.28},
            "doubleSided": True, "alphaMode": "BLEND" if rgba[3] < 1 else "OPAQUE"})
    initial = motion["clips"]["idle"]["frames"][0]
    for i, body in enumerate(motion["bodies"]):
        document["nodes"].append({"name": body["name"], "translation": initial[i * 7:i * 7 + 3],
                                   "rotation": initial[i * 7 + 3:i * 7 + 7], "children": []})
    for i, body in enumerate(motion["bodies"]):
        if body["parent"] >= 0:
            document["nodes"][body["parent"]]["children"].append(i)
    visual = [i for i in range(model.ngeom) if model.geom_type[i] == mujoco.mjtGeom.mjGEOM_MESH
              and model.geom_group[i] == 1]
    source_triangles = sum(int(model.mesh_facenum[model.geom_dataid[i]]) for i in visual)
    total_triangles = 0
    for geom in visual:
        mesh = model.geom_dataid[geom]
        va, vn = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
        fa, fn = model.mesh_faceadr[mesh], model.mesh_facenum[mesh]
        vertices = model.mesh_vert[va:va + vn].astype(np.float64)
        faces = model.mesh_face[fa:fa + fn].copy()
        vertices, inverse = np.unique(vertices, axis=0, return_inverse=True)
        faces = inverse[faces]
        # Preserve every anatomical/material component, including very small claws.
        target = min(fn, max(80, int(fn / source_triangles * 95_000)))
        if target < fn:
            vertices, faces = fast_simplification.simplify(vertices, faces, target_count=target, agg=5)
        used, inverse = np.unique(faces, return_inverse=True)
        vertices, faces = vertices[used], inverse.reshape(-1, 3)
        face_normals = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]],
                                vertices[faces[:, 2]] - vertices[faces[:, 0]])
        normals = np.zeros_like(vertices)
        for corner in range(3):
            np.add.at(normals, faces[:, corner], face_normals)
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-20)
        positions = accessor(vertices.astype("<f4"), "VEC3", 5126, 34962)
        normals = accessor(normals.astype("<f4"), "VEC3", 5126, 34962)
        indices = accessor(faces.astype("<u4").reshape(-1), "SCALAR", 5125, 34963)
        document["meshes"].append({"name": model.geom(geom).name, "primitives": [{
            "attributes": {"POSITION": positions, "NORMAL": normals}, "indices": indices,
            "material": int(model.geom_matid[geom])}]})
        q = model.geom_quat[geom]
        node = {"name": "visual_" + model.geom(geom).name, "mesh": len(document["meshes"]) - 1,
                "translation": model.geom_pos[geom].tolist(), "rotation": q[[1, 2, 3, 0]].tolist()}
        document["nodes"][model.geom_bodyid[geom] - 1]["children"].append(len(document["nodes"]))
        document["nodes"].append(node)
        total_triangles += len(faces)
    document["buffers"].append({"byteLength": len(binary)})
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * (-len(payload) % 4)
    binary.extend(b"\0" * (-len(binary) % 4))
    glb = (struct.pack("<5I", 0x46546C67, 2, 12 + 8 + len(payload) + 8 + len(binary), len(payload), 0x4E4F534A)
           + payload + struct.pack("<2I", len(binary), 0x004E4942) + binary)
    (OUT / "flybody.glb").write_bytes(glb)
    return {"source_triangles": source_triangles, "exported_triangles": total_triangles,
            "visual_meshes": len(visual), "triangle_budget": 120_000}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "build/flybody-source")
    parser.add_argument("--write-source-lock", action="store_true")
    parser.add_argument("--check", action="store_true", help="Verify packaged poses against MuJoCo without rewriting artifacts")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    xml, sources = acquire(args.cache, args.write_source_lock)
    model = mujoco.MjModel.from_xml_path(str(xml))
    if args.check:
        motion = json.loads((OUT / "motion.json").read_text())
        data = mujoco.MjData(model)
        count = 0
        for mode, clip in motion["clips"].items():
            for frame, (expected, qpos) in enumerate(zip(clip["frames"], clip["qpos"], strict=True)):
                authored = procedural_qpos(model, mode, frame / len(clip["frames"]) * np.pi * 2)
                np.testing.assert_allclose(qpos, authored, atol=5.1e-8, rtol=0)
                data.qpos[:] = qpos
                mujoco.mj_forward(model, data)
                actual = np.concatenate([body_pose(model, data, i) for i in range(1, model.nbody)])
                np.testing.assert_allclose(actual, expected, atol=2e-7, rtol=0)
                count += 1
        provenance = json.loads((OUT / "provenance.json").read_text())
        for name, expected in provenance["artifacts"].items():
            assert digest((OUT / name).read_bytes()) == expected, name
        print(f"Verified {len(sources)} pinned source hashes and {count} MuJoCo articulated poses")
        return
    motion = write_motion(model)
    geometry = write_glb(model, motion)
    provenance = {"repository": "https://github.com/TuragaLab/flybody", "revision": REVISION,
        "license": "Apache-2.0", "motion_kind": "procedural MuJoCo forward kinematics; not learned locomotion",
        "dependencies": {"mujoco": "3.3.7", "numpy": "2.3.3", "fast-simplification": "0.1.12"},
        "geometry": geometry, "sources": sources,
        "artifacts": {name: digest((OUT / name).read_bytes()) for name in ("flybody.glb", "motion.json")}}
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps({"geometry": geometry, "artifacts": provenance["artifacts"]}, indent=2))


if __name__ == "__main__":
    main()
