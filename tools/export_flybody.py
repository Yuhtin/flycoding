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
GROUND_CLEARANCE = 0.0001
SUPPORT_BODIES = ("claw_T1_left", "claw_T1_right", "claw_T2_left", "claw_T2_right",
                  "claw_T3_left", "claw_T3_right")

# Explicit authored rest qpos values.  The map is intentionally joint-name based
# so the source model remains the authority for qpos addresses and limits.
REST_JOINT_VALUES = {
    "antenna_abduct_left": 0.087513, "antenna_twist_left": 0.087513, "antenna_left": 0.087513,
    "antenna_abduct_right": -0.087513, "antenna_twist_right": -0.087513, "antenna_right": -0.087513,
    "wing_yaw_left": 1.4, "wing_roll_left": 0.8, "wing_pitch_left": 0.7,
    "wing_yaw_right": 1.4, "wing_roll_right": 0.8, "wing_pitch_right": 0.7,
    "coxa_abduct_T1_left": 0.0172165, "coxa_twist_T1_left": 0.0172165, "coxa_T1_left": 0.0172165,
    "femur_twist_T1_left": 0.0258248, "femur_T1_left": 0.0258248, "tibia_T1_left": 0.0409184,
    "tarsus_T1_left": 0.0091847, "tarsus2_T1_left": 0.0121583, "tarsus3_T1_left": 0.0121583,
    "tarsus4_T1_left": 0.0121583, "tarsus5_T1_left": 0.0121583,
    "coxa_abduct_T1_right": -0.0172165, "coxa_twist_T1_right": -0.0172165, "coxa_T1_right": -0.0172165,
    "femur_twist_T1_right": -0.0258248, "femur_T1_right": -0.0258248, "tibia_T1_right": 0.0175238,
    "tarsus_T1_right": -0.1028945, "tarsus2_T1_right": 0.0129124, "tarsus3_T1_right": 0.0129124,
    "tarsus4_T1_right": 0.0129124, "tarsus5_T1_right": 0.0129124,
    "coxa_abduct_T2_left": 0.005742, "coxa_twist_T2_left": 0.005742, "coxa_T2_left": 0.005742,
    "femur_twist_T2_left": 0.008613, "femur_T2_left": 0.008613, "tibia_T2_left": -0.0368225,
    "tarsus_T2_left": 0.098665, "tarsus2_T2_left": -0.0175955, "tarsus3_T2_left": -0.0175955,
    "tarsus4_T2_left": -0.0175955, "tarsus5_T2_left": -0.0175955,
    "coxa_abduct_T2_right": 0.0231254, "coxa_twist_T2_right": 0.0231254, "coxa_T2_right": 0.0231254,
    "femur_twist_T2_right": 0.0346881, "femur_T2_right": 0.0346881, "tibia_T2_right": 0.0269312,
    "tarsus_T2_right": 0.0076255, "tarsus2_T2_right": 0.0043065, "tarsus3_T2_right": 0.0043065,
    "tarsus4_T2_right": 0.0043065, "tarsus5_T2_right": 0.0043065,
    "coxa_abduct_T3_left": -0.0230142, "coxa_twist_T3_left": -0.0230142, "coxa_T3_left": -0.0230142,
    "femur_twist_T3_left": -0.0345213, "femur_T3_left": -0.0345213, "tibia_T3_left": -0.003739,
    "tarsus_T3_left": -0.0129939, "tarsus2_T3_left": 0.0056077, "tarsus3_T3_left": 0.0056077,
    "tarsus4_T3_left": 0.0056077, "tarsus5_T3_left": 0.0056077,
    "coxa_abduct_T3_right": -0.006133, "coxa_twist_T3_right": -0.006133, "coxa_T3_right": -0.006133,
    "femur_twist_T3_right": -0.0091995, "femur_T3_right": -0.0091995, "tibia_T3_right": -0.0447161,
    "tarsus_T3_right": 0.0887588, "tarsus2_T3_right": -0.0172606, "tarsus3_T3_right": -0.0172606,
    "tarsus4_T3_right": -0.0172606, "tarsus5_T3_right": -0.0172606,
}


def digest(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def rest_qpos(model):
    qpos = model.qpos0.copy()
    for name, value in REST_JOINT_VALUES.items():
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint >= 0:
            qpos[model.jnt_qposadr[joint]] = value
    return qpos


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
    qpos = rest_qpos(model)
    activity = {"idle": 0.0, "working": 1.0, "success": 0.7, "failure": 0.4}[mode]
    for joint in range(model.njnt):
        if model.jnt_type[joint] != mujoco.mjtJoint.mjJNT_HINGE:
            continue
        name = model.joint(joint).name
        side = 1 if "left" in name else -1
        phase_offset = (0 if "T1" in name else 2.1 if "T2" in name else 4.2) + side * 0.8
        value = qpos[model.jnt_qposadr[joint]]
        if name.startswith("head"):
            value += activity * (0.018 if name == "head" else 0.01) * np.sin(phase)
        elif name.startswith("antenna"):
            value += activity * 0.03 * np.sin(phase * 2 + side)
        elif name.startswith("abdomen"):
            value += activity * 0.004 * np.sin(phase)
        if mode == "success" and name == "head":
            value += 0.008 * np.sin(phase)
        if mode == "failure" and name == "head_twist":
            value += 0.018 * np.sin(phase * 2)
        if model.jnt_limited[joint]:
            value = np.clip(value, *model.jnt_range[joint])
        qpos[model.jnt_qposadr[joint]] = value
    return qpos


def visual_bottoms(model, data, body_names):
    """Return minimum Z for each named body's exported mesh geometry."""
    bottoms = {}
    for name in body_names:
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        if body < 0:
            continue
        values = []
        for geom in range(model.ngeom):
            if (model.geom_bodyid[geom] != body
                    or model.geom_type[geom] != mujoco.mjtGeom.mjGEOM_MESH
                    or model.geom_group[geom] != 1):
                continue
            mesh = model.geom_dataid[geom]
            va = model.mesh_vertadr[mesh]
            vn = model.mesh_vertnum[mesh]
            vertices = model.mesh_vert[va:va + vn]
            geom_rotation = np.empty(9)
            mujoco.mju_quat2Mat(geom_rotation, model.geom_quat[geom])
            body_rotation = data.xmat[body].reshape(3, 3)
            world = (data.xpos[body][:, None]
                     + body_rotation @ (model.geom_pos[geom][:, None]
                                        + geom_rotation.reshape(3, 3) @ vertices.T)).T
            values.append(float(world[:, 2].min()))
        if values:
            bottoms[name] = min(values)
    return bottoms


def grounded_metadata(model, data):
    data.qpos[:] = rest_qpos(model)
    mujoco.mj_forward(model, data)
    bottoms = visual_bottoms(model, data, SUPPORT_BODIES)
    if len(bottoms) != len(SUPPORT_BODIES):
        return {"support_bodies": sorted(bottoms), "status": "unavailable"}
    source_z = round(float(np.mean(list(bottoms.values()))), 12)
    spread = max(bottoms.values()) - min(bottoms.values())
    assert spread <= 1e-7, f"Ground support spread {spread} exceeds source tolerance"
    return {
        "source_z": source_z,
        "clearance": GROUND_CLEARANCE,
        "platform_source_z": round(source_z - GROUND_CLEARANCE, 12),
        "support_bodies": list(SUPPORT_BODIES),
        "support_tolerance_source": 1e-7,
        "support_bottoms_source_z": {name: round(value, 12) for name, value in bottoms.items()},
        "method": "minimum compiled MuJoCo source mesh vertex after forward kinematics of explicit rest_qpos",
    }


def write_motion(model):
    data = mujoco.MjData(model)
    bodies = [{"name": model.body(i).name, "parent": int(model.body_parentid[i]) - 1}
              for i in range(1, model.nbody)]
    joints = [{"name": model.joint(i).name, "qpos_address": int(model.jnt_qposadr[i]),
               "limited": bool(model.jnt_limited[i]), "range": model.jnt_range[i].tolist()}
              for i in range(model.njnt)]
    motion = {"version": 1, "convention": "parent-local XYZ, quaternion XYZW; source Z-up, centimeters",
              "bodies": bodies, "joints": joints, "ground": grounded_metadata(model, data), "clips": {}}
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
    if args.check and args.write_source_lock:
        parser.error("--check cannot rewrite the source lock")
    if not args.check:
        OUT.mkdir(parents=True, exist_ok=True)
    xml, sources = acquire(args.cache, args.write_source_lock)
    if args.check and (OUT / "LICENSE.flybody").read_bytes() != (args.cache / "LICENSE").read_bytes():
        raise ValueError("Packaged LICENSE.flybody differs from the pinned source license")
    model = mujoco.MjModel.from_xml_path(str(xml))
    if args.check:
        motion = json.loads((OUT / "motion.json").read_text())
        joints = motion.get("joints", [])
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
        if motion.get("ground", {}).get("support_bodies"):
            actual_ground = grounded_metadata(model, data)
            np.testing.assert_allclose(actual_ground["source_z"], motion["ground"]["source_z"], atol=5e-12, rtol=0)
            assert actual_ground["support_bodies"] == motion["ground"]["support_bodies"]
            assert max(actual_ground["support_bottoms_source_z"].values()) - min(
                actual_ground["support_bottoms_source_z"].values()) <= motion["ground"]["support_tolerance_source"]
            frozen = [joint["qpos_address"] for joint in joints
                      if joint["name"].startswith(("coxa", "femur", "tibia", "tarsus", "wing_"))]
            for clip in motion["clips"].values():
                reference = np.asarray(clip["qpos"][0])[frozen]
                for qpos in clip["qpos"]:
                    np.testing.assert_array_equal(np.asarray(qpos)[frozen], reference)
        provenance = json.loads((OUT / "provenance.json").read_text())
        if motion.get("ground", {}).get("support_bodies"):
            assert provenance["pose_label"].startswith("authored grounded rest pose")
            assert provenance["ground"] == motion["ground"]
        for name, expected in provenance["artifacts"].items():
            assert digest((OUT / name).read_bytes()) == expected, name
        print(f"Verified {len(sources)} pinned source hashes and {count} MuJoCo articulated poses")
        return
    prior_provenance = json.loads((OUT / "provenance.json").read_text()) if (OUT / "provenance.json").exists() else {}
    (OUT / "LICENSE.flybody").write_bytes((args.cache / "LICENSE").read_bytes())
    motion = write_motion(model)
    # The GLB is the reviewed 85-component geometry artifact.  Keep its bytes
    # stable across pose-only rebuilds; motion.json supplies the new transforms.
    geometry = prior_provenance.get("geometry") or write_glb(model, motion)
    rest_payload = json.dumps(motion["clips"]["idle"]["qpos"][0], separators=(",", ":")).encode()
    provenance = {"repository": "https://github.com/TuragaLab/flybody", "revision": REVISION,
        "license": "Apache-2.0", "motion_kind": "procedural MuJoCo forward kinematics; not learned locomotion",
        "pose_label": "authored grounded rest pose; lower body and folded wings fixed across procedural state clips",
        "ground": motion["ground"],
        "rest_qpos": digest(rest_payload),
        "dependencies": {"mujoco": "3.3.7", "numpy": "2.3.3", "fast-simplification": "0.1.12"},
        "geometry": geometry, "sources": sources,
        "artifacts": {name: digest((OUT / name).read_bytes()) for name in ("flybody.glb", "motion.json")}}
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps({"geometry": geometry, "artifacts": provenance["artifacts"]}, indent=2))


if __name__ == "__main__":
    main()
