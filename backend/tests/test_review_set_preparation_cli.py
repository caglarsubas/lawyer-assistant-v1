"""Private source-set CLI boundaries using isolated engineering fixtures only."""

import copy
import importlib.util
import json
import stat
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_provision_mappings
from test_public_sources import source as source_fixture
from test_release_snapshot import counts, operator_id
from test_release_snapshot_set import make_source_set
from test_review_preparation_cli import FakeStore
from test_source_reviews import assess
from test_workspace import workspace as workspace_fixture

from app import config, public_sources, release_set_preparation, release_snapshot, release_snapshot_set

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("review_set_preparation_cli_test", ROOT / "scripts/prepare_review_set.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)
workspace = workspace_fixture
source = source_fixture


def write_inputs(tmp_path, source_ids):
    request_dir = tmp_path / "selection"
    request_dir.mkdir()
    (request_dir / "sources.json").write_bytes(cli.io.canonical({
        "schema_version": "legal-review-source-selection-v1", "sources": [
            {"source_id": source_id, "expected_source_review_revision": 5,
             "expected_mapping_revision": 2} for source_id in source_ids]}))
    registry = tmp_path / "registry.json"
    registry.write_bytes(cli.io.canonical({"schema_version": "legal-identity-registry-v1", "entities": []}))
    resolutions = tmp_path / "resolutions.json"
    resolutions.write_bytes(cli.io.canonical({"schema_version": "provision-source-set-resolutions-v1",
                                            "sources": [{"source_id": source_id, "items": []}
                                                        for source_id in source_ids]}))
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    return dict(request_dir=request_dir, registry=registry, resolutions=resolutions, evidence_dir=evidence,
                output=tmp_path / "output")


def arguments(paths, owner="TEST-ONLY-owner"):
    return ["prepare", "--operator-id", owner, *[part for name, value in paths.items()
                                                for part in ("--" + name.replace("_", "-"), str(value))]]


def failed(capsys):
    result = capsys.readouterr()
    assert result.out == ""
    assert json.loads(result.err) == {"error": "review_source_set_preparation_failed", "publication_eligible": False}


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    paths = write_inputs(tmp_path, ["a" * 64, "b" * 64])
    store = FakeStore()
    settings = SimpleNamespace(public_source_dir=tmp_path / "unused-source-store")
    binding = {"schema_version": "legal-review-snapshot-set-v1", "operator_id": "TEST-ONLY-owner",
               "firm_id": "PRIVATE-FIRM", "publication_eligible": False,
               "sources": [{"source_id": value, "source_review_revision": 5, "mapping_revision": 2}
                           for value in ("a" * 64, "b" * 64)]}
    state = {"enters": 0, "exits": 0, "binding": binding, "store": store, "settings": settings, "paths": paths}

    @contextmanager
    def reader(_settings):
        assert _settings is settings
        yield store

    @contextmanager
    def snapshots(*args, **kwargs):
        state["enters"] += 1
        yield {"binding": copy.deepcopy(binding)}
        state["exits"] += 1

    def compiler(snapshot, registry, resolutions, evidence, ontology_root):
        return {"binding.json": cli.io.canonical(snapshot["binding"]),
                "registry.json": cli.io.canonical(registry), "resolutions.json": cli.io.canonical(resolutions),
                "review-report.json": b'{"PRIVATE-REVIEW-CANARY":true}',
                "candidate/exact.txt": "SYNTHETIC source only. Türkçe ⚖️.".encode()}, {
                    "source_count": 2, "signed": False, "publication_eligible": False,
                    "confidentiality": "firm_confidential", "rdf_generated": False}

    monkeypatch.setattr(config, "load_settings", lambda: settings)
    monkeypatch.setattr(release_snapshot, "readonly_store", reader)
    monkeypatch.setattr(release_snapshot_set, "locked_snapshot_set", snapshots)
    monkeypatch.setattr(public_sources, "PublicSourceStore", lambda _root: object())
    monkeypatch.setattr(release_set_preparation, "compile_review_set", compiler)
    monkeypatch.setattr(cli, "_ontology_digest", lambda _root: "c" * 64)
    return state


def test_schema_never_loads_configuration_or_storage(monkeypatch, capsys):
    def prohibited(*args, **kwargs):
        pytest.fail("Schema printing must not access deployment configuration or storage")
    monkeypatch.setattr(config, "load_settings", prohibited)
    monkeypatch.setattr(release_snapshot, "readonly_store", prohibited)
    assert cli.main(["schema"]) == 0
    captured = capsys.readouterr()
    assert not captured.err
    value = json.loads(captured.out)
    assert value["packet_schema"] == "legal-review-source-set-packet-v1"
    assert value["selection"]["properties"]["sources"]["maxItems"] == 8
    assert value["resolutions"]["additionalProperties"] is False
    assert value["registry"]["additionalProperties"] is False


@pytest.mark.parametrize("args", [[], ["PRIVATE-ARGUMENT"], ["prepare"], ["validate"],
                                  ["schema", "--PRIVATE-ARGUMENT"]])
def test_invalid_arguments_have_fixed_private_diagnostic(args, capsys):
    assert cli.main(args) == 2
    failed(capsys)


@pytest.mark.parametrize("component", ["selection", "registry", "resolutions", "evidence", "extra_request_file"])
def test_invalid_input_rejected_before_settings_load(tmp_path, monkeypatch, capsys, component):
    paths = write_inputs(tmp_path, ["a" * 64, "b" * 64])
    if component == "selection":
        (paths["request_dir"] / "sources.json").write_text('{"sources":[],"sources":[]}')
    elif component in {"registry", "resolutions"}:
        value = json.loads(paths[component].read_bytes())
        value["PRIVATE-INSTRUCTION"] = "must not reach deployment"
        paths[component].write_bytes(cli.io.canonical(value))
    elif component == "evidence":
        (paths["evidence_dir"] / ("a" * 64 + ".bin")).write_bytes(b"wrong-hash-private-evidence")
    else:
        (paths["request_dir"] / "private.txt").write_text("PRIVATE-CANARY")
    loaded = []
    monkeypatch.setattr(config, "load_settings", lambda: loaded.append(True))
    assert cli.main(arguments(paths)) == 2
    assert not loaded and not paths["output"].exists()
    failed(capsys)


def test_prepare_then_validate_uses_separate_schema_and_no_private_summary(scenario, capsys):
    paths, store = scenario["paths"], scenario["store"]
    assert cli.main(arguments(paths)) == 0
    first = capsys.readouterr()
    assert not first.err
    report = json.loads(first.out)
    assert report["current_at_validation"] and report["source_count"] == 2
    assert report["signed"] is report["publication_eligible"] is False
    assert scenario["enters"] == scenario["exits"] == 2
    files, fingerprint = cli._read_packet(paths["output"], store)
    assert report["packet_sha256"] == fingerprint
    assert all(value not in first.out for value in ["PRIVATE-FIRM", "TEST-ONLY-owner", "PRIVATE-REVIEW-CANARY",
                                                   str(paths["output"]), "SYNTHETIC source only"])
    assert all(stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
               for path in (paths["output"], *paths["output"].rglob("*")))
    with pytest.raises(ValueError, match="Unsupported review packet"):
        cli.io.read_packet(paths["output"], store)
    assert cli.main(["validate", str(paths["output"]), "--operator-id", "TEST-ONLY-owner"]) == 0
    assert capsys.readouterr().out == first.out
    assert cli._read_packet(paths["output"], store) == (files, fingerprint)


def test_v1_publication_coordinator_rejects_set_packet_before_snapshot(scenario, monkeypatch, capsys):
    assert cli.main(arguments(scenario["paths"])) == 0
    capsys.readouterr()
    spec = importlib.util.spec_from_file_location("set_packet_publication_boundary", ROOT / "scripts/review_publication.py")
    publication = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publication)
    calls = []
    monkeypatch.setattr(release_snapshot, "locked_snapshot", lambda *a, **k: calls.append(True))
    with pytest.raises(ValueError, match="Unsupported review packet"):
        with publication.current_packet(scenario["settings"], scenario["paths"]["output"], "TEST-ONLY-owner"):
            pytest.fail("Source-set packet must not enter single-source publication")
    assert not calls


@pytest.mark.parametrize("component", ["binding.json", "registry.json", "resolutions.json", "review-report.json",
                                      "candidate/exact.txt", "manifest.hmac"])
def test_validate_rejects_packet_tampering_without_success(scenario, capsys, component):
    assert cli.main(arguments(scenario["paths"])) == 0
    capsys.readouterr()
    output = scenario["paths"]["output"]
    path = output / component
    path.write_bytes(path.read_bytes() + b"PRIVATE-TAMPERING")
    entered = scenario["enters"]
    assert cli.main(["validate", str(output), "--operator-id", "TEST-ONLY-owner"]) == 2
    assert scenario["enters"] == entered
    assert output.exists()
    failed(capsys)


@pytest.mark.parametrize("point", ["first_exit", "second_entry", "second_exit", "after_second_exit",
                                  "interrupted_second_exit"])
def test_prepare_discards_only_complete_output_when_live_boundary_fails(scenario, monkeypatch, capsys, point):
    original = release_snapshot_set.locked_snapshot_set
    visits = 0

    @contextmanager
    def changed(*args, **kwargs):
        nonlocal visits
        visits += 1
        visit = visits
        with original(*args, **kwargs) as snapshot:
            if point == "second_entry" and visit == 2:
                snapshot["binding"]["firm_id"] = "changed"
            yield snapshot
            if point == "first_exit" and visit == 1 or point == "second_exit" and visit == 2:
                raise ValueError("PRIVATE-LIVE-REVIEW-FAILURE")
            if point == "interrupted_second_exit" and visit == 2:
                raise KeyboardInterrupt()
        if point == "after_second_exit" and visit == 2:
            path = scenario["paths"]["registry"]
            path.write_bytes(path.read_bytes() + b"\n")

    monkeypatch.setattr(release_snapshot_set, "locked_snapshot_set", changed)
    assert cli.main(arguments(scenario["paths"])) == 2
    assert not scenario["paths"]["output"].exists()
    failed(capsys)


@pytest.mark.parametrize("kind", ["input", "ontology", "compiler_failure"])
def test_prepare_rejects_changes_during_compilation(scenario, monkeypatch, capsys, kind):
    original = release_set_preparation.compile_review_set

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if kind == "input":
            path = scenario["paths"]["resolutions"]
            path.write_bytes(path.read_bytes() + b"\n")
        elif kind == "ontology":
            monkeypatch.setattr(cli, "_ontology_digest", lambda _root: "d" * 64)
        else:
            raise ValueError("PRIVATE-COMPILER-DIAGNOSTIC")
        return result

    monkeypatch.setattr(release_set_preparation, "compile_review_set", changed)
    assert cli.main(arguments(scenario["paths"])) == 2
    assert not scenario["paths"]["output"].exists()
    failed(capsys)


def test_prepare_preserves_existing_output(scenario, capsys):
    output = scenario["paths"]["output"]
    output.mkdir()
    sentinel = output / "existing-private-note"
    sentinel.write_bytes(b"must survive")
    assert cli.main(arguments(scenario["paths"])) == 2
    assert sentinel.read_bytes() == b"must survive"
    failed(capsys)


def test_prepare_does_not_remove_a_replacement_output(scenario, monkeypatch, capsys):
    original = cli.io.atomic_packet
    output = scenario["paths"]["output"]

    def replaced(*args, **kwargs):
        identity = original(*args, **kwargs)
        output.rename(output.with_name("moved-owned-output"))
        output.mkdir()
        (output / "foreign-sentinel").write_bytes(b"must survive")
        return identity

    monkeypatch.setattr(cli.io, "atomic_packet", replaced)
    assert cli.main(arguments(scenario["paths"])) == 2
    assert (output / "foreign-sentinel").read_bytes() == b"must survive"
    failed(capsys)


@pytest.mark.parametrize("kind", ["rebuilt_changed", "packet_after_exit", "ontology_after_exit", "exit_failure"])
def test_validate_rechecks_final_integrity_without_modifying_packet(scenario, monkeypatch, capsys, kind):
    paths = scenario["paths"]
    assert cli.main(arguments(paths)) == 0
    capsys.readouterr()
    original = release_snapshot_set.locked_snapshot_set

    @contextmanager
    def changed(*args, **kwargs):
        with original(*args, **kwargs) as snapshot:
            if kind == "rebuilt_changed":
                snapshot["binding"]["firm_id"] = "changed"
            yield snapshot
            if kind == "exit_failure":
                raise ValueError("PRIVATE-LIVE-EXIT-FAILURE")
        if kind == "packet_after_exit":
            (paths["output"] / "candidate/exact.txt").write_bytes(b"PRIVATE-SUBSTITUTION")
        elif kind == "ontology_after_exit":
            monkeypatch.setattr(cli, "_ontology_digest", lambda _root: "d" * 64)

    monkeypatch.setattr(release_snapshot_set, "locked_snapshot_set", changed)
    assert cli.main(["validate", str(paths["output"]), "--operator-id", "TEST-ONLY-owner"]) == 2
    assert paths["output"].exists()
    failed(capsys)


def test_prepare_cleans_output_when_store_context_exit_fails(scenario, monkeypatch, capsys):
    original = release_snapshot.readonly_store
    output = scenario["paths"]["output"]

    @contextmanager
    def failed_exit(*args, **kwargs):
        with original(*args, **kwargs) as store:
            yield store
        assert output.is_dir()
        raise ValueError("PRIVATE-STORE-EXIT-FAILURE")

    monkeypatch.setattr(release_snapshot, "readonly_store", failed_exit)
    assert cli.main(arguments(scenario["paths"])) == 2
    assert not output.exists()
    failed(capsys)


@pytest.mark.parametrize("resolved", [False, True], ids=["blocked-private-report", "combined-rdf"])
def test_real_two_source_review_packet_stays_private_and_rejects_revoked_review(
        workspace, source, tmp_path, monkeypatch, capsys, resolved):
    proof = b"ISOLATED TEST rights proof; never a real legal or source permission."
    fingerprint = cli.io.digest(proof)
    original_assess = test_provision_mappings.assess

    def assess_with_physical_proof(*args, **kwargs):
        return original_assess(*args, **{**kwargs, "evidence_refs": [
            {"reference": "Isolated physical test proof", "sha256": fingerprint}]})

    monkeypatch.setattr(test_provision_mappings, "assess", assess_with_physical_proof)
    mappings = make_source_set(workspace, source)
    app = workspace[0]
    owner = operator_id(app)
    paths = write_inputs(tmp_path, [mapping[3] for mapping in mappings])
    (paths["evidence_dir"] / (fingerprint + ".bin")).write_bytes(proof)
    if resolved:
        registry, groups = [], []
        selection_path = paths["request_dir"] / "sources.json"
        selection = json.loads(selection_path.read_bytes())
        for index, mapping in enumerate(mappings):
            current = mapping[1].get(mapping[4] + "/provision-mappings").json()
            item = current["items"][0]
            response = test_provision_mappings.review(
                mapping, item["id"], revision=current["revision"],
                resolution={**item["resolution"], "valid_from": "2011-01-01", "valid_until": "2012-01-01",
                            "text_role": "operative_text"},
                evidence_refs=[{"reference": "Isolated mapping proof", "sha256": fingerprint}])
            assert response.status_code == 200, response.text
            selected = next(row for row in selection["sources"] if row["source_id"] == mapping[3])
            selected["expected_mapping_revision"] = response.json()["revision"]
            instrument = f"urn:tr-law:instrument:isolated-set-{index}"
            provision = f"urn:tr-law:provision:isolated-set-{index}"
            version = f"urn:tr-law:provision-version:isolated-set-{index}"
            registry.extend({"id": identity, "kind": kind, "parent_id": parent,
                             "evidence_sha256": [fingerprint]}
                            for identity, kind, parent in [(instrument, "instrument", None),
                                                          (provision, "provision", instrument),
                                                          (version, "provision_version", provision)])
            groups.append({"source_id": mapping[3], "items": [{"mapping_id": item["id"],
                           "instrument_id": instrument, "provision_id": provision, "provision_version_id": version}]})
        selection_path.write_bytes(cli.io.canonical(selection))
        paths["registry"].write_bytes(cli.io.canonical({"schema_version": "legal-identity-registry-v1",
                                                      "entities": registry}))
        paths["resolutions"].write_bytes(cli.io.canonical({"schema_version": "provision-source-set-resolutions-v1",
                                                         "sources": groups}))
    monkeypatch.setattr(config, "load_settings", lambda: app.state.settings)
    before = counts(app)
    assert cli.main(arguments(paths, owner)) == 0
    captured = capsys.readouterr()
    assert not captured.err
    report = json.loads(captured.out)
    assert report["source_count"] == report["mapping_count"] == 2
    assert report["publication_eligible"] is report["signed"] is False
    assert report["rdf_generated"] is resolved
    if resolved:
        assert report["assertion_count"] == 4 and report["blocker_codes"] == []
        candidate = (paths["output"] / "candidate/structure.ttl").read_text()
        assert "urn:tr-law:provision:isolated-set-0" in candidate
        assert "urn:tr-law:provision:isolated-set-1" in candidate
        assert "reviewPreparationOnly" in candidate
        assert proof.decode() not in candidate and owner not in candidate
    else:
        assert "unresolved_identity" in report["blocker_codes"]
        assert not (paths["output"] / "candidate/structure.ttl").exists()
    assert owner not in captured.out and "ISOLATED TEST rights proof" not in captured.out
    assert cli.main(["validate", str(paths["output"]), "--operator-id", owner]) == 0
    assert capsys.readouterr().out == captured.out
    assert counts(app) == before
    response = assess(mappings[0][1], mappings[0][4] + "/review", revision=5,
                      category="rights", decision="rejected")
    assert response.status_code == 200, response.text
    assert cli.main(["validate", str(paths["output"]), "--operator-id", owner]) == 2
    failed(capsys)
