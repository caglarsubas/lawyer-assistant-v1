"""R01 inspection is offline, bounded and never a runtime approval mechanism."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app import qualification, qualification_evidence

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("qualification_cli_tests", ROOT / "scripts/qualify_roadmap.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


@pytest.fixture
def dossier(tmp_path):
    destination = tmp_path / "dossier"
    shutil.copytree(ROOT / "qualification", destination)
    return destination


def test_seed_report_is_deterministic_non_authorizing_and_content_free():
    first = qualification.inspect_dossier(ROOT / "qualification")
    assert first == qualification.inspect_dossier(ROOT / "qualification")
    assert first["structurally_valid"] is True
    assert first["production_qualified"] is False
    assert first["runtime_authorization"] == "none"
    assert first["r01_exit_gate"] == "independent_review_and_evidence_required"
    assert set(first["components"]) == set(qualification.COMPONENTS)
    assert len(first["dossier_sha256"]) == 64


def test_captured_bytes_not_pretty_printing_define_snapshot(dossier):
    first = qualification.inspect_dossier(dossier)
    path = dossier / "research-dossier.json"
    path.write_bytes(path.read_bytes() + b"\n")
    second = qualification.inspect_dossier(dossier)
    assert first["dossier_sha256"] != second["dossier_sha256"]
    assert first["research"] == second["research"]


@pytest.mark.parametrize("name", qualification.COMPONENTS)
def test_invalid_component_never_echoes_input_or_partial_output(dossier, capsys, name):
    marker = "PRIVATE-CREDENTIAL-MARKER-DO-NOT-PRINT"
    (dossier / name).write_text(json.dumps({"unknown_secret": marker}))
    assert cli.main(["check", str(dossier)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert marker not in captured.err and str(dossier) not in captured.err
    assert json.loads(captured.err)["error"] == "invalid_r01_dossier"


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                                  b'{"a":-Infinity}', b'{"a":1e10000}', b'\xff', b'{"a":'])
def test_malformed_and_ambiguous_json_is_rejected(raw):
    with pytest.raises(ValueError):
        qualification.parse_component(raw)


def test_depth_and_size_are_bounded():
    with pytest.raises(ValueError):
        qualification.parse_component(b"[" * 45 + b"0" + b"]" * 45)
    with pytest.raises(ValueError):
        qualification.parse_component(b" " * (qualification.MAX_COMPONENT_BYTES + 1))


def test_shallow_json_node_count_is_bounded_before_work_stack_expansion():
    wide = b"[" + b"0," * qualification.MAX_JSON_NODES + b"0]"
    assert len(wide) < qualification.MAX_COMPONENT_BYTES
    with pytest.raises(ValueError, match="component_nodes_exceeded"):
        qualification.parse_component(wide)
    # The limit also counts children across separate, individually small lists.
    half = [0] * (qualification.MAX_JSON_NODES // 2)
    with pytest.raises(ValueError, match="component_nodes_exceeded"):
        qualification.parse_component(json.dumps({"left": half, "right": half}).encode())


@pytest.mark.parametrize("kind", ["missing", "symlink", "hardlink", "fifo", "directory", "oversized"])
def test_unsafe_file_types_rejected_without_blocking(dossier, tmp_path, capsys, kind):
    path = dossier / "analysis-fixture.json"
    if kind == "hardlink":
        os.link(path, tmp_path / "linked")
    else:
        path.unlink()
        if kind == "symlink":
            path.symlink_to(dossier / "scenario-fixture.json")
        elif kind == "fifo":
            os.mkfifo(path)
        elif kind == "directory":
            path.mkdir()
        elif kind == "oversized":
            with path.open("wb") as stream:
                stream.truncate(qualification.MAX_COMPONENT_BYTES + 1)
    assert cli.main(["check", str(dossier)]) == 2
    assert capsys.readouterr().out == ""


def test_linked_directory_rejected(dossier, tmp_path):
    link = tmp_path / "linked"
    link.symlink_to(dossier, target_is_directory=True)
    with pytest.raises(ValueError):
        qualification.read_components(link)


def test_changed_component_during_capture_is_rejected(dossier, monkeypatch):
    original = qualification_evidence._capture
    count = 0

    def replacement(*args, **kwargs):
        nonlocal count
        count += 1
        value = original(*args, **kwargs)
        if count == 1:
            path = dossier / "research-dossier.json"
            path.write_bytes(path.read_bytes() + b"\n")
        return value

    monkeypatch.setattr(qualification_evidence, "_capture", replacement)
    with pytest.raises(ValueError, match="qualification_evidence_invalid"):
        qualification.read_components(dossier)


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_extra_dossier_inventory_is_rejected_without_disclosure(dossier, capsys, kind):
    unexpected = dossier / "PRIVATE-UNKNOWN-ITEM"
    if kind == "file":
        unexpected.write_text("PRIVATE CONTENT")
    elif kind == "directory":
        unexpected.mkdir()
    else:
        unexpected.symlink_to(dossier / "research-dossier.json")
    assert cli.main(["check", str(dossier)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "PRIVATE" not in captured.err and str(dossier) not in captured.err
    assert json.loads(captured.err)["error"] == "invalid_r01_dossier"


def test_ancestor_replacement_during_dossier_open_is_rejected(dossier, monkeypatch):
    original_open = os.open
    replaced = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal replaced
        descriptor = original_open(path, flags, *args, **kwargs)
        if path == dossier.name and not replaced:
            replaced = True
            moved = dossier.parent / "replaced-dossier"
            dossier.rename(moved)
            dossier.symlink_to(moved, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(qualification_evidence.os, "open", racing_open)
    with pytest.raises(ValueError, match="qualification_evidence_invalid"):
        qualification.read_components(dossier)
    assert replaced


def test_private_argument_fixture_cannot_enter_shared_dossier(dossier, capsys):
    path = dossier / "analysis-fixture.json"
    value = json.loads(path.read_text())
    value["data_classification"] = "matter_private"
    path.write_text(json.dumps(value))
    assert cli.main(["check", str(dossier)]) == 2
    assert capsys.readouterr().out == ""


def test_no_application_environment_or_runtime_imports(tmp_path):
    program = """
import sys
from pathlib import Path
from app.qualification import inspect_dossier
report = inspect_dossier(Path(sys.argv[1]))
assert report['runtime_authorization'] == 'none'
assert not {'app.config', 'app.db', 'app.auth', 'app.provider', 'httpx', 'sqlalchemy'} & sys.modules.keys()
"""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), "LA_ENCRYPTION_KEY": "INVALID",
           "LA_DATABASE_URL": "not-a-database", "LLM_PROVIDER_BASE_URL": "not-a-provider"}
    subprocess.run([sys.executable, "-c", program, str(ROOT / "qualification")], cwd=tmp_path,
                   env=env, check=True, capture_output=True, timeout=15)


def test_schema_bundle_and_cli_report_never_write(dossier, capsys):
    before = {p.name: p.read_bytes() for p in dossier.iterdir() if p.is_file()}
    assert cli.main(["schemas"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["runtime_authorization"] == "none"
    assert set(schema["components"]) == set(qualification.COMPONENTS)
    assert cli.main(["check", str(dossier)]) == 0
    assert json.loads(capsys.readouterr().out)["structurally_valid"]
    assert before == {p.name: p.read_bytes() for p in dossier.iterdir() if p.is_file()}
