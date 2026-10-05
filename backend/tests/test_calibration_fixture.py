"""The synthetic producer measures the real parser without manufacturing real evidence."""

import hashlib
import importlib.util
import json
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from app.extraction_calibration import CalibrationSample, ReferenceTranscription, evaluate_calibration

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("calibration_fixture_test_module",
                                           ROOT / "scripts" / "build_calibration_fixture.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_actual_bounded_parser_matches_independent_turkish_gold(tmp_path, monkeypatch):
    destination = tmp_path.resolve() / "synthetic"

    def forbidden(*args, **kwargs):
        pytest.fail("Fixture generation must not use the network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = builder.build_fixture(destination)
    assert result["status"] == "synthetic_fixture_created"
    assert result["sample_kind"] == "synthetic"
    assert result["real_corpus_measurements"] == 0
    assert result["production_qualified"] is False
    assert result["runtime_authorization"] == "none"
    assert result["extraction_elapsed_seconds"] > 0
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert {entry.name for entry in destination.iterdir()} == set(builder.FIXED_FILES)
    for entry in destination.iterdir():
        assert stat.S_IMODE(entry.stat().st_mode) == 0o600
        assert not entry.is_symlink() and entry.stat().st_nlink == 1

    raw, extracted, reference = [(destination / name).read_bytes()
                                 for name in ("raw.bin", "extraction.json", "reference.json")]
    sample = CalibrationSample.model_validate_json((destination / "sample.json").read_bytes())
    gold = ReferenceTranscription.model_validate_json(reference)
    assert sample.sample_kind == "synthetic"
    assert sample.extraction_elapsed_seconds == result["extraction_elapsed_seconds"]
    assert sample.extractor_id == "isolated-extractor"
    assert sample.extractor_version == builder._extractor_version()
    assert gold.reference_status == "unreviewed"
    assert gold.raw_sha256 == hashlib.sha256(raw).hexdigest() == sample.raw_sha256
    assert sample.extraction_sha256 == hashlib.sha256(extracted).hexdigest()
    assert sample.reference_sha256 == hashlib.sha256(reference).hexdigest()
    assert "ı İ ş Ş ğ Ğ ü Ü ö Ö ç Ç" in raw.decode()
    critical = {(span.category, passage.text[span.start:span.end])
                for passage in gold.passages for span in passage.critical_spans}
    assert critical == {("date", "14.06.2020"), ("amount", "1.234,56 TL"),
                        ("negation", "ödeme yapılmadı"), ("identifier", "TEST-KAYIT-0042")}
    comparison = evaluate_calibration(sample, raw, extracted, reference)["comparison"]
    assert comparison["all_declared_checks_passed"] is True
    assert comparison["full_reference_comparison_passed"] is True
    assert comparison["reference_passages"] == comparison["exact_passage_matches"] == 3
    assert comparison["critical_span_matches"] == 4
    assert comparison["warning_count"] == 0
    assert comparison["page_count"] is None  # Do not invent a real page count for TXT.


def test_artifacts_are_deterministic_except_actual_measured_elapsed_time(tmp_path):
    first, second = tmp_path.resolve() / "first", tmp_path.resolve() / "second"
    builder.build_fixture(first)
    builder.build_fixture(second)
    for name in ("raw.bin", "extraction.json", "reference.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    first_sample, second_sample = [json.loads((directory / "sample.json").read_bytes())
                                   for directory in (first, second)]
    assert first_sample.pop("extraction_elapsed_seconds") > 0
    assert second_sample.pop("extraction_elapsed_seconds") > 0
    assert first_sample == second_sample


@pytest.mark.parametrize("kind", ["directory", "file", "dangling_symlink", "directory_symlink"])
def test_existing_destination_is_preserved_before_parser_runs(tmp_path, monkeypatch, kind):
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

    def forbidden():
        pytest.fail("An existing destination must fail before parsing")

    monkeypatch.setattr(builder, "_prepare_package", forbidden)
    with pytest.raises(builder.FixtureError, match="destination_must_be_new"):
        builder.build_fixture(destination)
    if kind == "directory":
        assert (destination / "preserve.txt").read_text() == "existing data"
    elif kind == "file":
        assert destination.read_text() == "existing data"
    else:
        assert destination.is_symlink()


def test_symlink_ancestor_and_missing_parent_are_rejected(tmp_path):
    parent = tmp_path.resolve()
    (parent / "real").mkdir()
    (parent / "alias").symlink_to(parent / "real", target_is_directory=True)
    with pytest.raises(OSError):
        builder.build_fixture(parent / "alias" / "new")
    with pytest.raises(OSError):
        builder.build_fixture(parent / "missing" / "new")
    assert not list((parent / "real").iterdir())


def test_concurrent_destination_creation_does_not_overwrite_or_remove_it(tmp_path, monkeypatch):
    destination = tmp_path.resolve() / "race"
    original = builder._prepare_package

    def concurrent_creation():
        package = original()
        destination.mkdir()
        (destination / "preserve.txt").write_text("concurrent owner")
        return package

    monkeypatch.setattr(builder, "_prepare_package", concurrent_creation)
    with pytest.raises(FileExistsError):
        builder.build_fixture(destination)
    assert {entry.name for entry in destination.iterdir()} == {"preserve.txt"}
    assert (destination / "preserve.txt").read_text() == "concurrent owner"


@pytest.mark.parametrize("mutation", ["text", "locator", "warnings", "page_count"])
def test_gold_is_not_derived_from_wrong_parser_output(tmp_path, monkeypatch, mutation):
    def incorrect_parser():
        result = {"passages": [{"locator": locator, "text": text} for locator, text in builder.GOLD_PASSAGES],
                  "warnings": [], "page_count": None, "passage_count": 3}
        if mutation == "text":
            result["passages"][1]["text"] = result["passages"][1]["text"].replace("yapılmadı", "yapıldı")
        elif mutation == "locator":
            result["passages"][0]["locator"] = "incorrect location"
        elif mutation == "warnings":
            result["warnings"] = ["Unprocessed content"]
        else:
            result["page_count"] = 1
        return result

    monkeypatch.setattr(builder, "_parse_known_text", incorrect_parser)
    destination = tmp_path.resolve() / "must-not-exist"
    with pytest.raises(builder.FixtureError, match="independent_reference"):
        builder.build_fixture(destination)
    assert not destination.exists()


def test_extractor_change_during_measurement_aborts_before_publication(tmp_path, monkeypatch):
    versions = iter(["sha256-" + "a" * 64, "sha256-" + "b" * 64])
    monkeypatch.setattr(builder, "_extractor_version", lambda: next(versions))
    destination = tmp_path.resolve() / "changed"
    with pytest.raises(builder.FixtureError, match="extractor_changed"):
        builder.build_fixture(destination)
    assert not destination.exists()


def test_failed_write_removes_only_own_new_files(tmp_path, monkeypatch):
    original = builder._write_new_file

    def failure(directory_fd, name, content):
        if name == "extraction.json":
            raise OSError("synthetic write failure")
        return original(directory_fd, name, content)

    monkeypatch.setattr(builder, "_write_new_file", failure)
    destination = tmp_path.resolve() / "failed"
    with pytest.raises(OSError):
        builder.build_fixture(destination)
    assert not destination.exists()


def test_cli_success_and_failure_emit_no_content_or_private_paths(tmp_path, capsys):
    destination = tmp_path.resolve() / "private-name-must-not-print"
    assert builder.main([str(destination)]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "synthetic_fixture_created"
    assert captured.err == ""
    assert str(destination) not in captured.out
    assert "TEST-KAYIT-0042" not in captured.out
    assert "ödeme" not in captured.out
    assert builder.main([str(destination)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(destination) not in captured.err
    assert json.loads(captured.err)["status"] == "fixture_generation_failed"


@pytest.mark.parametrize("arguments", [
    [], ["--api-key=PRIVATE-CREDENTIAL-MARKER"],
    ["/private/confidential-path", "--unknown=PRIVATE-CREDENTIAL-MARKER"],
    ["/private/confidential-path", "PRIVATE-CREDENTIAL-MARKER"],
])
def test_invalid_arguments_never_echo_values_or_paths(arguments, capsys):
    with pytest.raises(SystemExit) as caught:
        builder.main(arguments)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Invalid synthetic-fixture arguments; use --help.\n"


def test_parser_diagnostics_are_suppressed(tmp_path, monkeypatch, capsys):
    from app import extraction_worker
    from app.extraction_client import ExtractionError

    def denied(*args, **kwargs):
        raise ExtractionError("PRIVATE-PARSER-ERROR-CONTENT")

    monkeypatch.setattr(extraction_worker, "parse_document", denied)
    assert builder.main([str(tmp_path.resolve() / "error")]) == 2
    result = capsys.readouterr()
    assert "PRIVATE-PARSER" not in result.err
    assert result.out == ""


def test_actual_child_receives_only_known_bytes_and_clean_environment(tmp_path, monkeypatch):
    from app import extraction_worker

    original = extraction_worker.subprocess.Popen
    calls = []

    def inspect(command, **kwargs):
        calls.append(command)
        assert command[1:3] == ["-m", "app.extract"]
        assert command[4] == ".txt"
        assert Path(command[3]).read_bytes() == builder.RAW_BYTES
        assert kwargs["env"] == {
            "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
            "PYTHONPATH": str(ROOT / "backend"), "OMP_THREAD_LIMIT": "1", "OPENBLAS_NUM_THREADS": "1",
        }
        assert kwargs["stdin"] == subprocess.DEVNULL
        return original(command, **kwargs)

    monkeypatch.setenv("LLM_PROVIDER_API_KEY", "synthetic-key-never-forwarded")
    monkeypatch.setenv("HTTP_PROXY", "synthetic-proxy-never-forwarded")
    monkeypatch.setattr(extraction_worker.subprocess, "Popen", inspect)
    builder.build_fixture(tmp_path.resolve() / "clean-env")
    assert len(calls) == 1


def test_isolated_import_does_not_load_app_settings_database_or_public_source_store(tmp_path):
    program = """
import importlib.util, socket, sys
from pathlib import Path
def forbidden(*args, **kwargs):
    raise AssertionError('network call prohibited')
socket.socket.connect = forbidden
spec = importlib.util.spec_from_file_location('fixture_builder', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.build_fixture(Path(sys.argv[2]))
assert result['real_corpus_measurements'] == 0
assert result['production_qualified'] is False
assert not {'app.config', 'app.db', 'app.provider', 'app.public_sources', 'app.auth'} & sys.modules.keys()
"""
    subprocess.run([sys.executable, "-c", program, str(ROOT / "scripts" / "build_calibration_fixture.py"),
                    str(tmp_path.resolve() / "isolated")],
                   cwd=tmp_path, env={"PATH": os.environ.get("PATH", ""), "LA_DATABASE_URL": "invalid",
                                     "LLM_PROVIDER_API_KEY": "synthetic-never-read"},
                   check=True, capture_output=True, timeout=15)
