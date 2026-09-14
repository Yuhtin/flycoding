"""Optional exporter integration checks: run in the exporter dependency environment."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("fast_simplification")


@pytest.fixture
def exporter(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "tools/export_flybody.py"
    spec = importlib.util.spec_from_file_location("export_flybody", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out, cache = tmp_path / "body", tmp_path / "cache"
    out.mkdir()
    xml = cache / module.ASSETS / "fruitfly.xml"
    xml.parent.mkdir(parents=True)
    xml.write_text('<mujoco><asset/><worldbody><body name="thorax"><geom size="1"/></body></worldbody></mujoco>')
    (cache / "LICENSE").write_text("Locked source license")
    sources = [{"path": name, "bytes": len((cache / name).read_bytes()),
                "sha256": hashlib.sha256((cache / name).read_bytes()).hexdigest()}
               for name in (module.ASSETS + "fruitfly.xml", "LICENSE")]
    (out / "sources.lock.json").write_text(json.dumps(sources))
    (out / "motion.json").write_text('{"clips":{}}')
    (out / "provenance.json").write_text('{"artifacts":{}}')
    monkeypatch.setattr(module, "OUT", out)
    monkeypatch.setattr(sys, "argv", [str(path), "--cache", str(cache), "--check"])
    return module, out, cache


@pytest.mark.parametrize("contents", [None, "Changed packaged license"])
def test_check_rejects_missing_or_changed_license_without_writes(exporter, contents):
    module, out, _ = exporter
    if contents is not None:
        (out / "LICENSE.flybody").write_text(contents)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()}
    with pytest.raises((ValueError, FileNotFoundError), match="[Ll][Ii][Cc][Ee][Nn][Ss][Ee]"):
        module.main()
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()} == before


def test_valid_check_preserves_artifacts_and_export_copies_license(exporter, monkeypatch):
    module, out, cache = exporter
    (out / "LICENSE.flybody").write_bytes((cache / "LICENSE").read_bytes())
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()}
    module.main()
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()} == before
    (out / "LICENSE.flybody").unlink()
    monkeypatch.setattr(sys, "argv", ["export_flybody.py", "--cache", str(cache)])
    module.main()
    assert (out / "LICENSE.flybody").read_bytes() == b"Locked source license"


def test_check_cannot_rewrite_source_lock(exporter, monkeypatch):
    module, out, cache = exporter
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    monkeypatch.setattr(sys, "argv", ["export_flybody.py", "--cache", str(cache), "--check", "--write-source-lock"])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
