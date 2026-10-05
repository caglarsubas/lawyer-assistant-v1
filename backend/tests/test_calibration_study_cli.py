"""Recompute study results from physical artifacts; never trust supplied reports."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = load_script("study_cli_test", "qualify_roadmap.py")


@pytest.fixture
def bundle(tmp_path):
    dossier = tmp_path / "dossier"
    shutil.copytree(ROOT / "qualification", dossier)
    destination = tmp_path / "bundle"
    builder = load_script("study_builder_cli_test", "build_calibration_study_fixture.py")
    builder.build_fixture(destination, dossier)
    return destination, dossier


def args(bundle):
    destination, dossier = bundle
    return ["study", str(destination / "study"), "--dossier-dir", str(dossier),
            "--artifacts-dir", str(destination / "artifacts")]


def snapshot(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def test_study_is_reproducible_non_authorizing_and_does_not_write(bundle, capsys):
    destination, dossier = bundle
    before = snapshot(destination), snapshot(dossier)
    assert cli.main(args(bundle)) == 0
    first = capsys.readouterr().out
    report = json.loads(first)
    assert report["all_declared_checks_passed"] is True
    assert report["all_full_reference_comparisons_passed"] is True
    assert report["runtime_authorization"] == "none"
    assert report["production_qualified"] is False
    assert report["sample_independence"] == "not_established"
    assert report["study_sha256"] == hashlib.sha256((destination / "study/study.json").read_bytes()).hexdigest()
    assert cli.main(args(bundle)) == 0
    assert capsys.readouterr().out == first
    assert (snapshot(destination), snapshot(dossier)) == before


@pytest.mark.parametrize("kind", ["dossier", "artifact", "extra_artifact", "extra_manifest"])
def test_invalid_or_changed_inputs_produce_no_partial_report(bundle, capsys, kind):
    destination, dossier = bundle
    marker = "PRIVATE-INPUT-MUST-NOT-APPEAR"
    if kind == "dossier":
        target = dossier / "research-dossier.json"
        target.write_bytes(target.read_bytes() + b"\n")
    elif kind == "artifact":
        target = next((destination / "artifacts").iterdir())
        target.write_text(marker)
    else:
        directory = destination / ("artifacts" if kind == "extra_artifact" else "study")
        (directory / "private-note.txt").write_text(marker)
    assert cli.main(args(bundle)) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert marker not in captured.err and str(destination) not in captured.err
    assert json.loads(captured.err)["runtime_authorization"] == "none"


def test_ancestor_link_is_not_followed(bundle, tmp_path, capsys):
    destination, dossier = bundle
    alias = tmp_path / "alias"
    alias.symlink_to(destination, target_is_directory=True)
    assert cli.main(["study", str(alias / "study"), "--dossier-dir", str(dossier),
                     "--artifacts-dir", str(alias / "artifacts")]) == 2
    assert not capsys.readouterr().out


def test_capture_rechecks_study_manifest_before_printing(bundle, monkeypatch, capsys):
    from app import calibration_study_io

    original = calibration_study_io.read_exact_directory
    calls = 0

    def changed(directory, specifications, total_limit):
        nonlocal calls
        result = original(directory, specifications, total_limit)
        if "study.json" in result:
            calls += 1
            if calls > 1:
                result["study.json"] += b"\n"
        return result

    monkeypatch.setattr(calibration_study_io, "read_exact_directory", changed)
    assert cli.main(args(bundle)) == 2
    assert not capsys.readouterr().out


def test_rehashed_negation_change_has_distinct_comparison_failure(bundle, capsys):
    destination, _ = bundle
    manifest_path = destination / "study/study.json"
    manifest = json.loads(manifest_path.read_bytes())
    entry = manifest["entries"][0]
    artifacts = destination / "artifacts"
    reference = json.loads((artifacts / (entry["reference_sha256"] + ".bin")).read_bytes())
    old_extraction = artifacts / (entry["extraction_sha256"] + ".bin")
    extraction = json.loads(old_extraction.read_bytes())
    passage = next(p for p in reference["passages"] if any(s["category"] == "negation" for s in p["critical_spans"]))
    span = next(s for s in passage["critical_spans"] if s["category"] == "negation")
    actual = extraction["passages"][passage["ordinal"]]
    actual["text"] = actual["text"][:span["start"]] + "X" + actual["text"][span["start"] + 1:]
    changed = json.dumps(extraction, ensure_ascii=False).encode()
    entry["extraction_sha256"] = hashlib.sha256(changed).hexdigest()
    (artifacts / (entry["extraction_sha256"] + ".bin")).write_bytes(changed)
    old_extraction.unlink()
    old_sample = artifacts / (entry["sample_sha256"] + ".bin")
    sample = json.loads(old_sample.read_bytes())
    sample["extraction_sha256"] = entry["extraction_sha256"]
    changed_sample = json.dumps(sample).encode()
    entry["sample_sha256"] = hashlib.sha256(changed_sample).hexdigest()
    (artifacts / (entry["sample_sha256"] + ".bin")).write_bytes(changed_sample)
    old_sample.unlink()
    manifest_path.write_text(json.dumps(manifest))
    assert cli.main(args(bundle)) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["all_declared_checks_passed"] is False
    negation = report["cohorts"]["synthetic"]["totals"]["critical_categories"]["negation"]
    assert negation == {"expected": 3, "matched": 2, "match_rate": 2 / 3}


def test_study_schema_and_invalid_arguments_do_not_echo_inputs(capsys):
    assert cli.main(["study-schemas"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["runtime_authorization"] == "none"
    assert set(report["components"]) == {"study.json"}
    with pytest.raises(SystemExit) as stopped:
        cli.main(["study-schemas", "--key", "SECRET-MUST-NOT-ECHO"])
    assert stopped.value.code == 2
    assert "SECRET-MUST-NOT-ECHO" not in capsys.readouterr().err


def test_inspection_imports_no_runtime_or_network_services(bundle):
    destination, dossier = bundle
    program = """
import sys
from pathlib import Path
from app.calibration_study_io import inspect_study
report = inspect_study(*(Path(value) for value in sys.argv[1:]))
assert report['runtime_authorization'] == 'none'
assert not {'app.config', 'app.db', 'app.auth', 'app.provider', 'httpx', 'sqlalchemy'} & sys.modules.keys()
"""
    subprocess.run([sys.executable, "-c", program, str(destination / "study"), str(dossier),
                    str(destination / "artifacts")], cwd=ROOT / "backend",
                   check=True, capture_output=True, timeout=30)
