"""Synthetic study generation binds actual parser output to independent references."""

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from app.qualification import inspect_dossier

ROOT = Path(__file__).resolve().parents[2]
DOSSIER = ROOT / "qualification"
SPEC = importlib.util.spec_from_file_location("study_fixture_test_module",
                                           ROOT / "scripts" / "build_calibration_study_fixture.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def package(root):
    manifest = json.loads((root / "study" / "study.json").read_bytes())
    artifacts = {entry.name: entry.read_bytes() for entry in (root / "artifacts").iterdir()}
    return manifest, artifacts


def test_actual_three_practice_study_is_private_synthetic_and_bound(tmp_path, monkeypatch):
    from app.calibration_study import StudyManifest, evaluate_study

    def forbidden(*args, **kwargs):
        pytest.fail("Synthetic fixture must not use the network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    original = {entry.name: entry.read_bytes() for entry in DOSSIER.iterdir()}
    destination = tmp_path.resolve() / "study-fixture"
    report = builder.build_fixture(destination, DOSSIER)
    assert report["status"] == "synthetic_study_fixture_created"
    assert report["sample_count"] == report["practice_count"] == report["observed_documents"] == 3
    assert report["artifact_count"] == 12
    assert report["critical_span_count"] == 15
    assert report["extraction_elapsed_seconds"] > 0
    assert report["real_corpus_measurements"] == 0
    assert report["runtime_authorization"] == "none"
    assert report["production_qualified"] is False
    assert report["dossier_modified"] is False
    assert {entry.name: entry.read_bytes() for entry in DOSSIER.iterdir()} == original
    assert {entry.name for entry in destination.iterdir()} == {"study", "artifacts"}
    for entry in [destination, *destination.rglob("*")]:
        assert not entry.is_symlink()
        assert stat.S_IMODE(entry.stat().st_mode) == (0o700 if entry.is_dir() else 0o600)
        if entry.is_file():
            assert entry.stat().st_nlink == 1
    manifest, artifacts = package(destination)
    assert manifest["dossier_sha256"] == report["dossier_sha256"] == inspect_dossier(DOSSIER)["dossier_sha256"]
    assert {entry["practice"] for entry in manifest["entries"]} == {"contracts", "commercial", "employment"}
    assert len({entry["raw_sha256"] for entry in manifest["entries"]}) == 3
    for entry in manifest["entries"]:
        assert entry["source_identity_sha256"] == entry["raw_sha256"]
        assert entry["unit"] == "documents" and entry["observed_units"] == 1
        assert entry["layout"] == "born_digital"
        assert entry["source_family_id"] is None
        assert entry["reviewer_seconds"] is entry["assessed_items"] is entry["disagreements"] is None
        sample = json.loads(artifacts[entry["sample_sha256"] + ".bin"])
        extraction = json.loads(artifacts[entry["extraction_sha256"] + ".bin"])
        reference = json.loads(artifacts[entry["reference_sha256"] + ".bin"])
        assert sample["sample_kind"] == "synthetic"
        assert sample["data_classification"] == "synthetic_fixture"
        assert sample["practice"] == entry["practice"]
        assert sample["extraction_elapsed_seconds"] > 0
        assert sample["extractor_version"] == builder._extractor_version()
        assert reference["reference_status"] == "unreviewed"
        assert reference["coverage"] == "complete"
        assert reference["raw_sha256"] == entry["raw_sha256"]
        assert extraction["page_count"] is None
        assert extraction["passage_count"] == 3
        assert extraction["warnings"] == []
        assert {span["category"] for passage in reference["passages"] for span in passage["critical_spans"]} == {
            "date", "amount", "identifier", "negation", "exception",
        }
    for name, content in artifacts.items():
        assert name == hashlib.sha256(content).hexdigest() + ".bin"
    evaluated = evaluate_study(StudyManifest.model_validate(manifest), artifacts, inspect_dossier(DOSSIER), set())
    assert evaluated["runtime_authorization"] == "none"
    assert evaluated["production_qualified"] is False


def test_raw_extraction_and_reference_are_deterministic_except_sample_timings(tmp_path):
    paths = [tmp_path.resolve() / name for name in ("first", "second")]
    for path in paths:
        builder.build_fixture(path, DOSSIER)
    first, first_artifacts = package(paths[0])
    second, second_artifacts = package(paths[1])
    for first_entry, second_entry in zip(first["entries"], second["entries"], strict=True):
        for field in ("raw_sha256", "extraction_sha256", "reference_sha256"):
            assert first_entry[field] == second_entry[field]
            assert first_artifacts[first_entry[field] + ".bin"] == second_artifacts[second_entry[field] + ".bin"]
        a = json.loads(first_artifacts[first_entry.pop("sample_sha256") + ".bin"])
        b = json.loads(second_artifacts[second_entry.pop("sample_sha256") + ".bin"])
        assert a.pop("extraction_elapsed_seconds") > 0
        assert b.pop("extraction_elapsed_seconds") > 0
        assert a == b
    assert first == second


@pytest.mark.parametrize("kind", ["directory", "file", "dangling_symlink", "directory_symlink"])
def test_existing_destination_is_preserved_without_parsing(tmp_path, monkeypatch, kind):
    parent = tmp_path.resolve()
    destination = parent / "existing"
    if kind == "directory":
        destination.mkdir()
        (destination / "preserve.txt").write_text("existing data")
    elif kind == "file":
        destination.write_text("existing data")
    elif kind == "dangling_symlink":
        destination.symlink_to(parent / "absent")
    else:
        (parent / "target").mkdir()
        destination.symlink_to(parent / "target", target_is_directory=True)

    def forbidden(*args):
        pytest.fail("Existing destination must fail before parsing")

    monkeypatch.setattr(builder, "_prepare_package", forbidden)
    with pytest.raises(builder.FixtureError, match="destination_must_be_new"):
        builder.build_fixture(destination, DOSSIER)
    if kind == "directory":
        assert (destination / "preserve.txt").read_text() == "existing data"
    elif kind == "file":
        assert destination.read_text() == "existing data"
    else:
        assert destination.is_symlink()


def test_symlink_ancestors_missing_parent_and_parent_traversal_fail(tmp_path):
    parent = tmp_path.resolve()
    (parent / "real").mkdir()
    (parent / "alias").symlink_to(parent / "real", target_is_directory=True)
    for destination in (parent / "alias" / "new", parent / "missing" / "new", parent / "real" / ".." / "new"):
        with pytest.raises((OSError, ValueError)):
            builder.build_fixture(destination, DOSSIER)
    assert not list((parent / "real").iterdir())


@pytest.mark.parametrize("mutation", ["text", "locator", "warnings", "page_count"])
def test_reference_cannot_silently_follow_wrong_parser_output(tmp_path, monkeypatch, mutation):
    original = builder._parse_known_text

    def incorrect(raw):
        result = copy.deepcopy(original(raw))
        if mutation == "text":
            result["passages"][2]["text"] = "Incorrect test output"
        elif mutation == "locator":
            result["passages"][0]["locator"] = "Incorrect location"
        elif mutation == "warnings":
            result["warnings"] = ["Unprocessed content"]
        else:
            result["page_count"] = 1
        return result

    monkeypatch.setattr(builder, "_parse_known_text", incorrect)
    destination = tmp_path.resolve() / "wrong"
    with pytest.raises(builder.FixtureError, match="independent_reference"):
        builder.build_fixture(destination, DOSSIER)
    assert not destination.exists()


def test_extractor_change_during_measurement_rejects_package(tmp_path, monkeypatch):
    versions = iter(["sha256-" + "a" * 64, "sha256-" + "b" * 64])
    monkeypatch.setattr(builder, "_extractor_version", lambda: next(versions))
    destination = tmp_path.resolve() / "changed"
    with pytest.raises(builder.FixtureError, match="extractor_changed"):
        builder.build_fixture(destination, DOSSIER)
    assert not destination.exists()


@pytest.mark.parametrize("point", ["during_parse", "during_write"])
def test_changed_dossier_is_not_reported_as_bound_or_modified_back(tmp_path, monkeypatch, point):
    dossier = tmp_path.resolve() / "dossier"
    shutil.copytree(DOSSIER, dossier)
    destination = tmp_path.resolve() / "changed"
    changed = dossier / "research-dossier.json"
    modified = changed.read_bytes() + b"\n"
    if point == "during_parse":
        original = builder._prepare_package

        def mutate(report):
            result = original(report)
            changed.write_bytes(modified)
            return result

        monkeypatch.setattr(builder, "_prepare_package", mutate)
    else:
        original = builder._write_new_file

        def mutate(directory_fd, name, content):
            result = original(directory_fd, name, content)
            if name == "study.json":
                changed.write_bytes(modified)
            return result

        monkeypatch.setattr(builder, "_write_new_file", mutate)
    with pytest.raises(builder.FixtureError, match="dossier_changed"):
        builder.build_fixture(destination, dossier)
    assert not destination.exists()
    assert changed.read_bytes() == modified


def test_concurrent_destination_is_never_overwritten_or_removed(tmp_path, monkeypatch):
    destination = tmp_path.resolve() / "race"
    original = builder._prepare_package

    def concurrent(report):
        result = original(report)
        destination.mkdir()
        (destination / "preserve.txt").write_text("other owner")
        return result

    monkeypatch.setattr(builder, "_prepare_package", concurrent)
    with pytest.raises(FileExistsError):
        builder.build_fixture(destination, DOSSIER)
    assert {entry.name for entry in destination.iterdir()} == {"preserve.txt"}


def test_failed_write_cleans_up_only_generated_files(tmp_path, monkeypatch):
    original = builder._write_new_file

    def failure(directory_fd, name, content):
        if name == "study.json":
            raise OSError("private diagnostic")
        return original(directory_fd, name, content)

    monkeypatch.setattr(builder, "_write_new_file", failure)
    destination = tmp_path.resolve() / "failed"
    with pytest.raises(OSError):
        builder.build_fixture(destination, DOSSIER)
    assert not destination.exists()


def test_cli_success_and_errors_never_echo_content_or_destination(tmp_path, capsys):
    destination = tmp_path.resolve() / "CONFIDENTIAL-DESTINATION"
    assert builder.main([str(destination), "--dossier-dir", str(DOSSIER)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["sample_count"] == 3
    assert captured.err == ""
    assert "CONFIDENTIAL" not in captured.out and "TEST-SOZ-010" not in captured.out
    assert builder.main([str(destination)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "CONFIDENTIAL" not in captured.err
    assert json.loads(captured.err)["runtime_authorization"] == "none"


@pytest.mark.parametrize("arguments", [[], ["--api-key=PRIVATE-MARKER"],
                                       ["/private/name", "--unknown=PRIVATE-MARKER"]])
def test_invalid_cli_arguments_do_not_echo_values(arguments, capsys):
    with pytest.raises(SystemExit) as caught:
        builder.main(arguments)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Invalid synthetic-study arguments; use --help.\n"


def test_isolated_generation_never_imports_settings_or_forwards_secrets(tmp_path):
    program = """
import importlib.util, socket, sys
from pathlib import Path
def forbidden(*args, **kwargs):
    raise AssertionError('network prohibited')
socket.socket.connect = forbidden
spec = importlib.util.spec_from_file_location('fixture_builder', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from app import extraction_worker
original = extraction_worker.subprocess.Popen
calls = []
known = [("\\n\\n".join(text for _, text in passages) + "\\n").encode()
         for _, passages, _ in module.SAMPLES]
def inspected(command, **kwargs):
    assert command[1:3] == ['-m', 'app.extract']
    assert command[4] == '.txt'
    assert Path(command[3]).read_bytes() == known[len(calls)]
    assert 'LLM_PROVIDER_API_KEY' not in kwargs['env']
    assert 'HTTP_PROXY' not in kwargs['env']
    calls.append(command)
    return original(command, **kwargs)
extraction_worker.subprocess.Popen = inspected
result = module.build_fixture(Path(sys.argv[2]), Path(sys.argv[3]))
assert result['real_corpus_measurements'] == 0
assert len(calls) == 3
assert not {'app.config', 'app.db', 'app.provider', 'app.public_sources', 'app.auth'} & sys.modules.keys()
"""
    subprocess.run([sys.executable, "-c", program, str(ROOT / "scripts" / "build_calibration_study_fixture.py"),
                    str(tmp_path.resolve() / "isolated"), str(DOSSIER)], cwd=tmp_path,
                   env={"PATH": os.environ.get("PATH", ""), "LLM_PROVIDER_API_KEY": "synthetic-never-forwarded",
                        "HTTP_PROXY": "synthetic-never-forwarded"},
                   check=True, capture_output=True, timeout=20)


@pytest.mark.parametrize("location", ["root", "study", "artifacts"])
@pytest.mark.parametrize("checkpoint", ["after_mkdir", "before_open"])
@pytest.mark.parametrize("original_mode", [0o755, 0o700])
def test_directory_replacement_never_adopts_or_changes_existing_contents(
    tmp_path, monkeypatch, location, checkpoint, original_mode,
):
    parent = tmp_path.resolve()
    destination = parent / "generated"
    victim = parent / "preexisting"
    victim.mkdir(mode=original_mode)
    victim.chmod(original_mode)
    (victim / "preserve.txt").write_text("unrelated private contents")
    original_identity = builder._identity(victim.stat())
    replacement = destination if location == "root" else destination / location
    selected_name = "generated" if location == "root" else location
    original_mkdir, original_open = builder.os.mkdir, builder.os.open
    swapped = False

    def swap():
        nonlocal swapped
        replacement.rename(parent / "displaced-new-directory")
        victim.rename(replacement)
        swapped = True

    def mkdir(name, *values, **kwargs):
        result = original_mkdir(name, *values, **kwargs)
        if checkpoint == "after_mkdir" and name == selected_name and not swapped:
            swap()
        return result

    def opened(name, *values, **kwargs):
        if checkpoint == "before_open" and name == selected_name and not swapped:
            swap()
        return original_open(name, *values, **kwargs)

    monkeypatch.setattr(builder.os, "mkdir", mkdir)
    monkeypatch.setattr(builder.os, "open", opened)
    with pytest.raises(builder.FixtureError, match="destination_changed"):
        builder.build_fixture(destination, DOSSIER)
    assert swapped
    assert builder._identity(replacement.stat()) == original_identity
    assert stat.S_IMODE(replacement.stat().st_mode) == original_mode
    assert {entry.name for entry in replacement.iterdir()} == {"preserve.txt"}
    assert (replacement / "preserve.txt").read_text() == "unrelated private contents"
