"""Operator inspection emits no private contents or partial success."""

import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from test_public_sources import source as source_fixture
from test_release_snapshot import counts, operator_id
from test_release_snapshot_set import make_source_set
from test_workspace import workspace as workspace_fixture

from app import config, release_snapshot_set

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("review_set_cli_test", ROOT / "scripts/inspect_review_set.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
workspace = workspace_fixture
source = source_fixture


@pytest.fixture
def selection(workspace, source, tmp_path, monkeypatch):
    mappings = make_source_set(workspace, source, count=2)
    app = workspace[0]
    directory = tmp_path / "selection"
    directory.mkdir()
    (directory / "sources.json").write_text(json.dumps({
        "schema_version": "legal-review-source-selection-v1",
        "sources": [{"source_id": mapping[3], "expected_source_review_revision": 5,
                     "expected_mapping_revision": 2} for mapping in mappings],
    }))
    monkeypatch.setattr(config, "load_settings", lambda: app.state.settings)
    return app, mappings, directory, operator_id(app)


def arguments(selection):
    return ["inspect", "--request-dir", str(selection[2]), "--operator-id", selection[3]]


def assert_failure(capsys):
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "review_source_set_inspection_failed", "publication_eligible": False}


def test_inspection_emits_only_deterministic_summary_without_writes(selection, capsys):
    app, mappings, directory, owner = selection
    before = counts(app)
    request = (directory / "sources.json").read_bytes()
    assert cli.main(arguments(selection)) == 0
    first = capsys.readouterr()
    assert first.err == ""
    value = json.loads(first.out)
    assert set(value) == {"schema_version", "source_count", "mapping_count", "artifact_bytes",
                          "binding_sha256", "consistency_mode", "signed", "publication_eligible",
                          "confidentiality"}
    assert value["source_count"] == value["mapping_count"] == 2
    assert value["signed"] is value["publication_eligible"] is False
    assert value["confidentiality"] == "firm_confidential"
    for secret in [owner, "demo-firm", str(directory), *(mapping[3] for mapping in mappings),
                   "Synthetic test review only", "SENTETİK TEST METNİ"]:
        assert secret not in first.out
    assert cli.main(arguments(selection)) == 0
    assert capsys.readouterr().out == first.out
    assert counts(app) == before
    assert (directory / "sources.json").read_bytes() == request


@pytest.mark.parametrize("kind", ["extra_file", "oversized", "duplicate_key", "invalid_json", "boolean_revision",
                                  "extra_field", "duplicate_source", "hardlink", "symlink", "ancestor_link"])
def test_invalid_request_rejected_before_settings_load(selection, monkeypatch, capsys, kind):
    directory = selection[2]
    path = directory / "sources.json"
    command = arguments(selection)
    if kind == "extra_file":
        (directory / "private.txt").write_text("PRIVATE-REVIEW")
    elif kind == "oversized":
        path.write_bytes(b" " * (cli.MAX_REQUEST_BYTES + 1))
    elif kind == "duplicate_key":
        path.write_text('{"sources": [], "sources": []}')
    elif kind == "invalid_json":
        path.write_text("PRIVATE-REVIEW")
    elif kind in {"boolean_revision", "extra_field", "duplicate_source"}:
        value = json.loads(path.read_text())
        if kind == "boolean_revision":
            value["sources"][0]["expected_mapping_revision"] = True
        elif kind == "extra_field":
            value["private_notes"] = "PRIVATE-REVIEW"
        else:
            value["sources"][1] = value["sources"][0]
        path.write_text(json.dumps(value))
    elif kind in {"hardlink", "symlink"}:
        target = directory.parent / "original-selection.json"
        path.rename(target)
        if kind == "hardlink":
            path.hardlink_to(target)
        else:
            path.symlink_to(target)
    else:
        alias = directory.parent / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        command[2] = str(alias)
    loaded = []
    monkeypatch.setattr(config, "load_settings", lambda: loaded.append(True))
    assert cli.main(command) == 2
    assert not loaded
    assert_failure(capsys)


@pytest.mark.parametrize("kind", ["request_changed", "exit_failure", "interrupted"])
def test_no_partial_output_when_request_or_final_revalidation_fails(selection, monkeypatch, capsys, kind):
    original = release_snapshot_set.locked_snapshot_set

    @contextmanager
    def interrupted(*args, **kwargs):
        with original(*args, **kwargs) as snapshot:
            if kind == "request_changed":
                path = selection[2] / "sources.json"
                path.write_bytes(path.read_bytes() + b"\n")
            yield snapshot
            if kind == "exit_failure":
                raise ValueError("PRIVATE-REVIEW-AND-CREDENTIALS")
            if kind == "interrupted":
                raise KeyboardInterrupt()

    monkeypatch.setattr(release_snapshot_set, "locked_snapshot_set", interrupted)
    assert cli.main(arguments(selection)) == 2
    assert_failure(capsys)


def test_schema_does_not_load_configuration_or_storage(monkeypatch, capsys):
    loaded = []
    monkeypatch.setattr(config, "load_settings", lambda: loaded.append(True))
    assert cli.main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["properties"]["sources"]["maxItems"] == 8
    assert schema["additionalProperties"] is False
    assert not loaded


@pytest.mark.parametrize("args", [[], ["PRIVATE-ARGUMENT"], ["inspect"], ["schema", "--PRIVATE-ARGUMENT"]])
def test_bad_arguments_use_fixed_diagnostic(args, capsys):
    assert cli.main(args) == 2
    assert_failure(capsys)
