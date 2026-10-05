"""Offline evidence/calibration CLI integration using generated synthetic inputs."""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = load_script("calibration_cli_integration", "qualify_roadmap.py")


@pytest.fixture
def dossier(tmp_path):
    destination = tmp_path / "dossier"
    shutil.copytree(ROOT / "qualification", destination)
    return destination


@pytest.fixture
def sample(tmp_path):
    builder = load_script("calibration_fixture_integration", "build_calibration_fixture.py")
    destination = tmp_path / "sample"
    builder.build_fixture(destination)
    return destination


def add_evidence(dossier, directory, content=b"SYNTHETIC ONLY: private evidence marker"):
    digest = hashlib.sha256(content).hexdigest()
    path = dossier / "research-dossier.json"
    value = json.loads(path.read_bytes())
    value["evidence_records"].append({
        "evidence_id": "confidential-source-reference", "sha256": digest,
        "sample_kind": "synthetic", "recorded_on": value["recorded_on"],
        "owner_role": "evaluation_owner",
    })
    path.write_text(json.dumps(value))
    directory.mkdir()
    evidence = directory / (digest + ".bin")
    evidence.write_bytes(content)
    return evidence


def test_empty_evidence_is_not_a_vacuous_verification(dossier, tmp_path, capsys):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    assert cli.main(["evidence", str(dossier), "--evidence-dir", str(evidence)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["research_evidence_integrity"]["status"] == "no_records"
    assert report["production_qualified"] is False
    assert report["research"]["evidence_authenticated"] is False


def test_verified_bytes_do_not_authenticate_review_or_echo_contents(dossier, tmp_path, capsys):
    directory = tmp_path / "evidence"
    content = b"SYNTHETIC CREDENTIAL TEST: sk-do-not-print-this"
    add_evidence(dossier, directory, content)
    assert cli.main(["evidence", str(dossier), "--evidence-dir", str(directory)]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert content.decode() not in output and "confidential-source-reference" not in output
    assert report["research_evidence_integrity"]["status"] == "hashes_verified"
    assert report["research_evidence_integrity"]["source_authenticity_verified"] is False
    assert report["research_evidence_integrity"]["review_authenticated"] is False
    assert report["runtime_authorization"] == "none"
    assert report["research"]["evidence_authenticated"] is False


def test_corrupt_evidence_rejects_without_partial_report(dossier, tmp_path, capsys):
    directory = tmp_path / "evidence"
    add_evidence(dossier, directory).write_bytes(b"CHANGED SECRET INPUT")
    assert cli.main(["evidence", str(dossier), "--evidence-dir", str(directory)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "CHANGED SECRET INPUT" not in captured.err and str(directory) not in captured.err


def test_generated_actual_extraction_compares_without_changing_inputs(sample, capsys):
    before = {p.name: p.read_bytes() for p in sample.iterdir()}
    assert cli.main(["calibrate", str(sample)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["comparison"]["all_declared_checks_passed"] is True
    assert report["sample_sha256"] == hashlib.sha256(before["sample.json"]).hexdigest()
    assert report["runtime_authorization"] == "none"
    assert report["production_qualified"] is False
    assert before == {p.name: p.read_bytes() for p in sample.iterdir()}


def test_semantic_text_change_reports_failure_even_with_updated_extraction_hash(sample, capsys):
    path = sample / "extraction.json"
    extraction = json.loads(path.read_bytes())
    extraction["passages"][0]["text"] += " CHANGED-SENSITIVE-TEXT"
    raw = json.dumps(extraction, ensure_ascii=False).encode()
    path.write_bytes(raw)
    manifest = sample / "sample.json"
    value = json.loads(manifest.read_bytes())
    value["extraction_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest.write_text(json.dumps(value))
    assert cli.main(["calibrate", str(sample)]) == 1
    captured = capsys.readouterr()
    assert "CHANGED-SENSITIVE-TEXT" not in captured.out
    assert json.loads(captured.out)["comparison"]["all_declared_checks_passed"] is False


def test_changed_source_without_rebinding_reference_is_invalid(sample, capsys):
    raw = (sample / "raw.bin").read_bytes() + b"CHANGED"
    (sample / "raw.bin").write_bytes(raw)
    manifest = sample / "sample.json"
    value = json.loads(manifest.read_bytes())
    value["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest.write_text(json.dumps(value))
    assert cli.main(["calibrate", str(sample)]) == 2
    assert capsys.readouterr().out == ""


def test_unknown_argument_does_not_echo_a_secret(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["schemas", "--api-key", "DO-NOT-ECHO-SECRET"])
    assert stopped.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "DO-NOT-ECHO-SECRET" not in captured.err


def test_calibration_schema_output_remains_non_authorizing(capsys):
    assert cli.main(["calibration-schemas"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["runtime_authorization"] == "none"
    assert set(report["components"]) == {"sample.json", "reference.json"}
