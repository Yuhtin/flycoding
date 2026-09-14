"""Offline checks for the actual, packaged flybody geometry and articulation."""
import hashlib
import json
import math
from pathlib import Path
import struct


BODY = Path(__file__).parents[1] / "src/flycodex/web/body"
REVISION = "d015e9bfe441bd90ae431bac24c55cb74bdbce26"


def test_packaged_body_assets_match_recorded_provenance():
    assert (BODY / "provenance.json").is_file(), "Export the pinned flybody assets"
    provenance = json.loads((BODY / "provenance.json").read_text())
    assert provenance["revision"] == REVISION
    assert provenance["motion_kind"] == "procedural MuJoCo forward kinematics; not learned locomotion"
    assert len(provenance["sources"]) >= 80
    assert provenance["sources"] == json.loads((BODY / "sources.lock.json").read_text())
    assert all(len(item["sha256"]) == 64 for item in provenance["sources"])
    for name, expected in provenance["artifacts"].items():
        data = (BODY / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected["sha256"]
        assert len(data) == expected["bytes"]
    assert sum(item["bytes"] for item in provenance["artifacts"].values()) < 5_000_000
    assert "Apache License" in (BODY / "LICENSE.flybody").read_text()
    assert "MIT License" in (BODY / "LICENSE.three").read_text()


def test_glb_contains_detailed_anatomy_and_local_geometry():
    assert (BODY / "flybody.glb").is_file(), "The viewer requires actual mesh geometry"
    data = (BODY / "flybody.glb").read_bytes()
    magic, version, size, json_size, chunk_type = struct.unpack_from("<5I", data)
    assert (magic, version, size, chunk_type) == (0x46546C67, 2, len(data), 0x4E4F534A)
    gltf = json.loads(data[20:20 + json_size])
    assert all("uri" not in item for item in gltf["buffers"])
    names = {node["name"] for node in gltf["nodes"]}
    assert {"head", "thorax", "abdomen", "wing_left", "wing_right"} <= names
    assert all(f"tibia_T{leg}_{side}" in names for leg in (1, 2, 3) for side in ("left", "right"))
    triangles = sum(gltf["accessors"][p["indices"]]["count"] // 3
                    for mesh in gltf["meshes"] for p in mesh["primitives"])
    assert 20_000 < triangles <= 120_000
    assert len(gltf["meshes"]) >= 80
    assert "red" in {material["name"] for material in gltf["materials"]}
    binary_start = 20 + json_size + 8
    for accessor in gltf["accessors"]:
        view = gltf["bufferViews"][accessor["bufferView"]]
        if accessor["componentType"] == 5126:
            values = struct.unpack_from(f"<{accessor['count'] * 3}f", data, binary_start + view["byteOffset"])
            assert all(math.isfinite(value) for value in values)


def test_motion_has_finite_articulated_poses_inside_source_joint_limits():
    assert (BODY / "motion.json").is_file(), "Export articulated MuJoCo poses"
    motion = json.loads((BODY / "motion.json").read_text())
    assert set(motion["clips"]) == {"idle", "working", "success", "failure"}
    names = [body["name"] for body in motion["bodies"]]
    for clip in motion["clips"].values():
        assert len(clip["frames"]) >= 24
        for frame, qpos in zip(clip["frames"], clip["qpos"], strict=True):
            assert len(frame) == len(names) * 7
            assert all(math.isfinite(value) for value in frame + qpos)
            for i in range(len(names)):
                assert abs(sum(v * v for v in frame[i * 7 + 3:i * 7 + 7]) - 1) < 0.00001
            for joint in motion["joints"]:
                if joint["limited"]:
                    assert joint["range"][0] - 1e-6 <= qpos[joint["qpos_address"]] <= joint["range"][1] + 1e-6
    work = motion["clips"]["working"]["frames"]
    for name in ("head", "antenna_left"):
        index = names.index(name) * 7
        assert max(max(frame[index:index + 7][i] for frame in work)
                   - min(frame[index:index + 7][i] for frame in work) for i in range(7)) > 0.01, name


def test_motion_uses_grounded_rest_pose_and_freezes_supporting_body():
    motion = json.loads((BODY / "motion.json").read_text())
    provenance = json.loads((BODY / "provenance.json").read_text())
    ground = motion["ground"]
    support = {"claw_T1_left", "claw_T1_right", "claw_T2_left", "claw_T2_right",
               "claw_T3_left", "claw_T3_right"}
    assert set(ground["support_bodies"]) == support
    assert ground["source_z"] < 0
    assert 0 < ground["clearance"] <= 0.0001
    assert provenance["pose_label"].startswith("authored grounded rest pose")
    names = [joint["name"] for joint in motion["joints"]]
    frozen = {index for index, name in enumerate(names)
              if (name.startswith(("coxa", "femur", "tibia", "tarsus"))
                  or name.startswith("wing_"))}
    for clip in motion["clips"].values():
        reference = clip["qpos"][0]
        for qpos in clip["qpos"]:
            assert all(qpos[joint["qpos_address"]] == reference[joint["qpos_address"]]
                       for joint in motion["joints"] if names.index(joint["name"]) in frozen)


def test_motion_rest_upper_body_is_bounded():
    motion = json.loads((BODY / "motion.json").read_text())
    limits = {"head": 0.03, "antenna": 0.04, "abdomen": 0.005}
    for prefix, limit in limits.items():
        joints = [joint for joint in motion["joints"] if joint["name"].startswith(prefix)]
        for joint in joints:
            address = joint["qpos_address"]
            values = [qpos[address] for clip in motion["clips"].values() for qpos in clip["qpos"]]
            assert max(values) - min(values) <= 2 * limit + 1e-6, joint["name"]
