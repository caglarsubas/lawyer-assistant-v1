"""Invented private recorded dependency receipts, actual current source guards."""
import importlib.util

import pytest
from test_declared_graph_assembly import assembly as assembly_fixture
from test_final_release_authorization import accepted, activate, stage_for
from test_final_release_inspection import files
from test_retained_mixed_assembly import successor
from test_source_reviews import assess

from app import config, retained_release_inspection
from app.config import ROOT
from app.release_preparation import canonical
from app.retained_release_inspection import DependencyExpectation, inspect_dependencies

assembly = assembly_fixture


def request(info):
    return DependencyExpectation(schema_version="legal-retained-dependency-expectation-v1",
        release_id=info["release_id"], serving_sha256=info["serving_sha256"])


def test_retained_observation_separates_recorded_inventory_from_current_permission(assembly, tmp_path, monkeypatch, capsys):
    first = stage_for(assembly, tmp_path)
    accepted(first)
    serving, root, key, _, guard, pointer = activate(first)
    second = successor(first, pointer, tmp_path / "observed-successor")
    accepted(second)
    info = serving.validate_prepared(second["candidate"] / "prepared", key)
    serving.install(root, second["candidate"] / "prepared", key, authorization_guard=guard)
    state = files(root)
    first_receipt = inspect_dependencies(assembly["settings"], request(info))
    assert first_receipt["recorded_retained_base"] == pointer
    assert first_receipt["recorded_components"] == second["body"]["component_release_ids"]
    assert first_receipt["recorded_dependencies_sha256"] == second["body"]["dependencies_sha256"]
    assert first_receipt["current_permission"] == "verified" and first_receipt["active_pointer"] == pointer
    assert files(root) == state
    # Sources remain current conjunctive dependencies even when the observed
    # target is installed but inactive and the signed old inventory still exists.
    item = assembly["current"]["evidence"][0][2]
    assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    denied = inspect_dependencies(assembly["settings"], request(info))
    assert denied["current_permission"] == "withheld_or_unavailable"
    assert denied["recorded_whole_signature"] == "verified"
    assert denied["recorded_inventory_sha256"] == first_receipt["recorded_inventory_sha256"]
    assert all(denied[name] is False for name in ("activation_authorized", "runtime_read_authorized", "retry_authorized",
        "repair_performed", "publication_performed", "legal_qualification_granted"))
    assert files(root) == state
    encoded = canonical(denied)
    for secret in (assembly["current"]["operator_id"].encode(), assembly["current"]["audience"], str(assembly["root"]).encode()):
        assert secret not in encoded
    spec = importlib.util.spec_from_file_location("TEST_retained_inspector", ROOT / "scripts/inspect_retained_dependencies.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    expectation = tmp_path / "expectation.json"
    expectation.write_bytes(canonical(request(info).model_dump()))
    monkeypatch.setattr(config, "load_settings", lambda: assembly["settings"])
    assert cli.main(["--expectation", str(expectation)]) == 0
    assert "withheld_or_unavailable" in capsys.readouterr().out
    # A late original-packet change is unknown, even when a valid old signature
    # was read earlier. No entry observation survives inconsistent exit bytes.
    original = second["packet"] / "dependencies.fernet"
    raw = original.read_bytes()
    capture = retained_release_inspection.capture_roots
    def changed(roots):
        result = capture(roots)
        original.write_bytes(raw + b"changed during observation")
        return result
    with monkeypatch.context() as patch:
        patch.setattr(retained_release_inspection, "capture_roots", changed)
        try:
            with pytest.raises(ValueError):
                inspect_dependencies(assembly["settings"], request(info))
        finally:
            original.write_bytes(raw)
    # Broken provenance never turns into a recorded complete inventory or
    # permission grant. The CLI returns only a bounded, private-safe error.
    original.write_bytes(original.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        inspect_dependencies(assembly["settings"], request(info))
    assert cli.main(["--expectation", str(expectation)]) == 2
    error = capsys.readouterr()
    assert not error.out and "retained_dependency_observation_unavailable" in error.err
    assert str(assembly["root"]) not in error.err and assembly["current"]["operator_id"] not in error.err
    assert files(root) == state


@pytest.mark.parametrize("change", ["missing-id", "short-hash", "unknown-schema", "extra", "unknown-id"])
def test_dependency_expectation_is_closed_and_explicit(change):
    data = request({"release_id": "a" * 64, "serving_sha256": "b" * 64}).model_dump()
    if change == "missing-id":
        del data["release_id"]
    elif change == "short-hash":
        data["serving_sha256"] = "b" * 8
    elif change == "unknown-schema":
        data["schema_version"] = "legal-retained-dependency-expectation-v2"
    elif change == "unknown-id":
        data["release_id"] = "latest"
    else:
        data["allow_repair"] = True
    with pytest.raises(ValueError):
        DependencyExpectation.model_validate(data)


def test_dependency_observer_never_initializes_state(tmp_path):
    from app.config import Settings
    root = tmp_path / "uninitialized"
    root.mkdir()
    settings = Settings(_env_file=None, graph_release_dir=str(root), graph_serving_review_role="final")
    with pytest.raises(ValueError):
        inspect_dependencies(settings, request({"release_id": "a" * 64, "serving_sha256": "b" * 64}))
    assert not list(root.iterdir())
