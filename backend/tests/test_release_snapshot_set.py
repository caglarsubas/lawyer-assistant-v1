"""Isolated engineering reviews only; no acquired source or legal approval."""

import copy
import hashlib
import json
from contextlib import contextmanager

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from test_provision_mappings import TEXT, propose, ready, review
from test_public_sources import source as source_fixture
from test_release_snapshot import counts, operator_id
from test_source_reviews import another_client, assess, assign, revoke
from test_workspace import workspace as workspace_fixture

from app import release_snapshot_set as batch
from app.db import User
from app.provision_mapping_models import ProvisionMappingHead
from app.public_sources import PublicSourceStore
from app.release_preparation import PreparationError, _snapshot
from app.release_snapshot import REQUIRED_USES, SnapshotError, locked_snapshot, readonly_store
from app.source_review_models import SourceReviewHead

source = source_fixture
workspace = workspace_fixture


def make_source_set(workspace, source, count=2):
    """Populate exact independent ledger heads through real review APIs in tests."""
    app, client, _ = workspace
    store, inputs, metadata, locators = source
    inputs["text_path"].write_bytes(TEXT.encode())
    locators = {**locators, "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(), "passages": [
        {"id": "p1", "start": 0, "end": len(TEXT), "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
         "locator": "Synthetic snapshot-set test"}]}
    inputs["locators_path"].write_text(json.dumps(locators), encoding="utf-8")
    app.state.settings.public_source_dir = store.root
    results = []
    for index in range(count):
        inputs["metadata_path"].write_text(json.dumps({
            **metadata, "title": f"ISOLATED SNAPSHOT-SET FIXTURE {index}",
            "source_version_id": f"snapshot-set-fixture-{index}"}), encoding="utf-8")
        source_id = store.import_package(**inputs)["id"]
        mapping = app, client, store, source_id, f"/api/v1/public-sources/{source_id}"
        ready(mapping, uses=sorted(REQUIRED_USES))
        response = propose(mapping, source_revision=5)
        assert response.status_code == 200, response.text
        identifier = response.json()["items"][0]["id"]
        result = review(mapping, identifier)
        assert result.status_code == 200, result.text
        results.append(mapping)
    return results


@pytest.fixture
def source_set(workspace, source):
    return make_source_set(workspace, source)


def request_for(source_set):
    return batch.SnapshotSetRequest.model_validate({
        "schema_version": "legal-review-source-selection-v1", "sources": [
            {"source_id": item[3], "expected_source_review_revision": 5, "expected_mapping_revision": 2}
            for item in source_set]})


@contextmanager
def snapshot_set(source_set, *, reader=None, request=None, **changes):
    app, _, store, _, _ = source_set[0]
    with batch.locked_snapshot_set(reader or app.state.store, store,
                                   operator_id=changes["operator_id"] if "operator_id" in changes else operator_id(app),
                                   request=request if request is not None else request_for(source_set)) as value:
        yield value


def test_set_is_sorted_consistent_deterministic_and_confidential(source_set):
    app, _, store, _, _ = source_set[0]
    original = {item[3]: {path.name: path.read_bytes() for path in (store.root / item[3]).iterdir()}
                for item in source_set}
    before = counts(app)
    statements = []
    event.listen(app.state.store.engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    with snapshot_set(source_set) as first:
        assert [item["binding"]["source_id"] for item in first["snapshots"]] == sorted(item[3] for item in source_set)
        assert first["binding"] == {
            "schema_version": "legal-review-snapshot-set-v1", "firm_id": "demo-firm",
            "operator_id": operator_id(app), "sources": [item["binding"] for item in first["snapshots"]],
            "publication_eligible": False}
        for item in first["snapshots"]:
            mapping = next(value for value in source_set if value[3] == item["binding"]["source_id"])
            assert item["state"] == mapping[1].get(mapping[4] + "/provision-mappings").json()
            assert not item["state"]["publication_eligible"]
        expected_bytes = sum(len(raw) for item in first["snapshots"] for raw in item["package"].artifacts.values())
        summary = first["summary"]
        assert summary["source_count"] == summary["mapping_count"] == 2
        assert summary["artifact_bytes"] == expected_bytes
        assert summary["binding_sha256"] == hashlib.sha256(batch._canonical(first["binding"])).hexdigest()
        assert summary["consistency_mode"] == "sqlite_demo_optimistic_revalidation"
        assert summary["confidentiality"] == "firm_confidential"
        assert summary["signed"] is summary["publication_eligible"] is False
        public_text = json.dumps(summary)
        assert all(item[3] not in public_text for item in source_set)
        assert operator_id(app) not in public_text and "Demo Avukat" not in public_text
    with snapshot_set(list(reversed(source_set))) as second:
        assert second["binding"] == first["binding"]
        assert second["summary"] == first["summary"]
    assert counts(app) == before
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert original == {item[3]: {path.name: path.read_bytes() for path in (store.root / item[3]).iterdir()}
                        for item in source_set}


def test_all_sources_use_one_session_and_deterministic_lock_order(source_set, monkeypatch):
    original = batch._load
    loaded = []

    def load(store, session, package, *args):
        loaded.append((id(session), package.detail["id"]))
        return original(store, session, package, *args)

    monkeypatch.setattr(batch, "_load", load)
    with snapshot_set(list(reversed(source_set))):
        assert len(loaded) == 4  # Initial capture and pre-yield revalidation.
    expected = sorted(item[3] for item in source_set)
    assert [item[1] for item in loaded] == expected * 3
    assert len({item[0] for item in loaded}) == 1


def test_readonly_store_preserves_database_keys_and_v1_output(source_set):
    app, _, store, _, _ = source_set[0]
    before = counts(app)
    key_path = app.state.settings.data_dir / "demo-encryption.key"
    key = key_path.read_bytes()
    with readonly_store(app.state.settings) as reader:
        with snapshot_set(source_set, reader=reader) as value:
            expected = value["snapshots"][0]
        with locked_snapshot(reader, store, operator_id=operator_id(app),
                             source_id=expected["binding"]["source_id"],
                             expected_source_review_revision=5, expected_mapping_revision=2) as single:
            assert single["binding"] == expected["binding"]
            assert single["state"] == expected["state"]
    assert counts(app) == before and key_path.read_bytes() == key


@pytest.mark.parametrize("change", [
    "empty", "one", "nine", "duplicate", "extra", "wrong_schema", "tuple", "string",
    "bad_id", "uppercase_id", "newline_id", "bool_source_revision", "bool_mapping_revision",
    "zero_revision", "oversized_revision", "unknown_source_field",
])
def test_strict_source_request_contract(change):
    data = {"schema_version": "legal-review-source-selection-v1", "sources": [
        {"source_id": "a" * 64, "expected_source_review_revision": 5, "expected_mapping_revision": 2},
        {"source_id": "b" * 64, "expected_source_review_revision": 5, "expected_mapping_revision": 2}]}
    if change == "empty":
        data["sources"] = []
    elif change == "one":
        data["sources"].pop()
    elif change == "nine":
        data["sources"] = [{**data["sources"][0], "source_id": f"{index:064x}"} for index in range(9)]
    elif change == "duplicate":
        data["sources"][1] = data["sources"][0]
    elif change == "extra":
        data["approve"] = True
    elif change == "wrong_schema":
        data["schema_version"] = "legal-review-snapshot-v1"
    elif change == "tuple":
        data["sources"] = tuple(data["sources"])
    elif change == "string":
        data["sources"] = "a" * 64
    elif change in {"bad_id", "uppercase_id", "newline_id"}:
        data["sources"][0]["source_id"] = {"bad_id": "unknown", "uppercase_id": "A" * 64,
                                             "newline_id": "a" * 63 + "\n"}[change]
    elif change == "bool_source_revision":
        data["sources"][0]["expected_source_review_revision"] = True
    elif change == "bool_mapping_revision":
        data["sources"][0]["expected_mapping_revision"] = True
    elif change == "zero_revision":
        data["sources"][0]["expected_mapping_revision"] = 0
    elif change == "oversized_revision":
        data["sources"][0]["expected_source_review_revision"] = 1001
    elif change == "unknown_source_field":
        data["sources"][0]["rights_override"] = True
    with pytest.raises(ValidationError):
        batch.SnapshotSetRequest.model_validate(data)


@pytest.mark.parametrize("change", ["dict", "modified", "constructed", "invalid_operator", "bool_operator"])
def test_invalid_or_mutated_requests_fail_before_session_and_source_reads(source_set, monkeypatch, change):
    request = request_for(source_set)
    operator = operator_id(source_set[0][0])
    if change == "dict":
        request = request.model_dump()
    elif change == "modified":
        request.sources[0].expected_mapping_revision = True
    elif change == "constructed":
        request = batch.SnapshotSetRequest.model_construct(schema_version="wrong", sources=request.sources)
    elif change == "invalid_operator":
        operator = ""
    elif change == "bool_operator":
        operator = True
    monkeypatch.setattr(source_set[0][0].state.store, "session", lambda: pytest.fail("Must not open storage"))
    monkeypatch.setattr(PublicSourceStore, "verified_package", lambda *_: pytest.fail("Must not read sources"))
    with pytest.raises(SnapshotError), snapshot_set(source_set, request=request, operator_id=operator):
        pytest.fail("Invalid request must not yield")


def test_request_mutation_after_entry_does_not_change_selection(source_set):
    request = request_for(source_set)
    with snapshot_set(source_set, request=request) as value:
        expected = copy.deepcopy(value["binding"])
        request.sources[0].source_id = "f" * 64
        request.sources[0].expected_mapping_revision = 999
        request.sources.clear()
    assert value["binding"] == expected


@pytest.mark.parametrize("change", ["source_revision", "mapping_revision", "unknown_source", "missing_right",
                                     "source_rejected", "mapping_rejected", "released_owner", "corrupt_source",
                                     "corrupt_mapping", "package"])
def test_one_bad_source_blocks_entire_set_before_yield(source_set, change):
    mapping = source_set[1]
    app, client, store, source_id, base = mapping
    request = request_for(source_set)
    selected = next(item for item in request.sources if item.source_id == source_id)
    if change == "source_revision":
        selected.expected_source_review_revision = 4
    elif change == "mapping_revision":
        selected.expected_mapping_revision = 1
    elif change == "unknown_source":
        selected.source_id = "f" * 64
    elif change in {"missing_right", "source_rejected"}:
        args = {"permitted_uses": ["local_processing", "internal_display"]} if change == "missing_right" else {}
        category = "rights" if change == "missing_right" else "legal"
        decision = "accepted" if change == "missing_right" else "rejected"
        assert assess(client, base + "/review", 5, category, decision, **args).status_code == 200
        selected.expected_source_review_revision = 6
    elif change == "mapping_rejected":
        identifier = client.get(base + "/provision-mappings").json()["items"][0]["id"]
        assert review(mapping, identifier, 2, 5, "rejected").status_code == 200
        selected.expected_mapping_revision = 3
    elif change == "released_owner":
        assert assign(client, base + "/review", 5, "release").status_code == 200
        selected.expected_source_review_revision = 6
    elif change.startswith("corrupt"):
        model = SourceReviewHead if change == "corrupt_source" else ProvisionMappingHead
        with app.state.store.session() as session:
            session.scalar(select(model).where(model.source_id == source_id)).payload = "broken ciphertext"
            session.commit()
    elif change == "package":
        path = store.root / source_id / "text.txt"
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(SnapshotError), snapshot_set(source_set, request=request):
        pytest.fail("One invalid source must block the complete set")


@pytest.mark.parametrize("change", ["inactive", "role", "firm", "other_owner"])
def test_operator_scope_is_required_for_all_sources(source_set, change):
    app = source_set[0][0]
    operator = operator_id(app)
    if change == "other_owner":
        another_client(app, username="unassigned-admin", role="admin")
        with app.state.store.session() as session:
            operator = session.scalar(select(User.id).where(User.username == "unassigned-admin"))
    else:
        revoke(app, change)
    with pytest.raises(SnapshotError), snapshot_set(source_set, operator_id=operator):
        pytest.fail("Operator must own every source in this firm")


@pytest.mark.parametrize("source_index", [0, 1])
@pytest.mark.parametrize("change", ["source", "mapping", "owner", "package"])
def test_every_source_is_revalidated_after_caller_operation(source_set, source_index, change):
    mapping = source_set[source_index]
    _, client, store, source_id, base = mapping
    with pytest.raises(SnapshotError), snapshot_set(source_set):
        if change == "source":
            assert assess(client, base + "/review", 5, "legal").status_code == 200
        elif change == "mapping":
            identifier = client.get(base + "/provision-mappings").json()["items"][0]["id"]
            assert review(mapping, identifier, 2, 5, "rejected").status_code == 200
        elif change == "owner":
            assert assign(client, base + "/review", 5, "release").status_code == 200
        elif change == "package":
            path = store.root / source_id / "text.txt"
            path.chmod(0o600)
            path.write_bytes(path.read_bytes() + b"changed")


@pytest.mark.parametrize("change", ["inactive", "role", "firm"])
def test_operator_revalidated_after_caller_operation(source_set, change):
    with pytest.raises(SnapshotError), snapshot_set(source_set):
        revoke(source_set[0][0], change)


@pytest.mark.parametrize("change", ["source", "package", "operator"])
def test_initial_capture_races_are_rejected_before_any_snapshot_is_yielded(source_set, monkeypatch, change):
    original = batch._load
    ordered = sorted(source_set, key=lambda item: item[3])
    changed = False

    def load(*args):
        nonlocal changed
        result = original(*args)
        if not changed and args[2].detail["id"] == ordered[-1][3]:
            changed = True
            mapping = ordered[0]
            if change == "source":
                assert assess(mapping[1], mapping[4] + "/review", 5, "legal").status_code == 200
            elif change == "package":
                path = mapping[2].root / mapping[3] / "text.txt"
                path.chmod(0o600)
                path.write_bytes(path.read_bytes() + b"changed")
            else:
                revoke(mapping[0], "inactive")
        return result

    monkeypatch.setattr(batch, "_load", load)
    with pytest.raises(SnapshotError), snapshot_set(source_set):
        pytest.fail("Inconsistent initial capture must never be returned")


@pytest.mark.parametrize("when", ["before_yield", "after_yield"])
def test_account_change_during_last_revalidation_read_is_detected(source_set, monkeypatch, when):
    original = batch._load
    calls = 0
    target = 4 if when == "before_yield" else 6

    def load(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls == target:
            revoke(source_set[0][0], "inactive")
        return result

    monkeypatch.setattr(batch, "_load", load)
    with pytest.raises(SnapshotError), snapshot_set(source_set):
        assert when == "after_yield"


@pytest.mark.parametrize("change", ["binding", "source_binding", "review", "state", "package_bytes", "metadata",
                                     "summary", "remove_snapshot", "replace_snapshot", "extra_field"])
def test_returned_content_mutation_cannot_alter_retained_comparison_baselines(source_set, change):
    with pytest.raises(SnapshotError, match="content changed"), snapshot_set(source_set) as value:
        if change == "binding":
            value["binding"]["sources"][0]["mapping_revision"] = 999
        elif change == "source_binding":
            value["snapshots"][0]["binding"]["mapping_revision"] = 999
        elif change == "review":
            value["snapshots"][0]["source_review"]["assessments"]["legal"]["decision"] = "rejected"
        elif change == "state":
            value["snapshots"][0]["state"]["items"].clear()
        elif change == "package_bytes":
            value["snapshots"][0]["package"].artifacts["raw.bin"] = b"changed"
        elif change == "metadata":
            value["snapshots"][0]["package"].metadata.title = "Changed title"
        elif change == "summary":
            value["summary"]["publication_eligible"] = True
        elif change == "remove_snapshot":
            value["snapshots"].pop()
        elif change == "replace_snapshot":
            value["snapshots"][0] = None
        else:
            value["extra"] = True


def test_source_bytes_and_mapping_caps_apply_to_total_not_each_source(source_set, monkeypatch):
    packages = [item[2].verified_package(item[3]) for item in source_set]
    total = sum(len(raw) for package in packages for raw in package.artifacts.values())
    monkeypatch.setattr(batch, "MAX_ARTIFACT_BYTES", total)
    monkeypatch.setattr(batch, "MAX_MAPPINGS", 2)
    with snapshot_set(source_set):
        pass
    monkeypatch.setattr(batch, "MAX_ARTIFACT_BYTES", total - 1)
    with pytest.raises(SnapshotError, match="byte limit"), snapshot_set(source_set):
        pytest.fail("Total artifact bytes must be bounded")
    monkeypatch.setattr(batch, "MAX_ARTIFACT_BYTES", total)
    monkeypatch.setattr(batch, "MAX_MAPPINGS", 1)
    with pytest.raises(SnapshotError, match="mapping limit"), snapshot_set(source_set):
        pytest.fail("Total mappings must be bounded")


def test_caller_failure_closes_session_without_writes(source_set, monkeypatch):
    app = source_set[0][0]
    before = counts(app)
    original = app.state.store.session
    closed = []

    @contextmanager
    def tracked_session():
        with original() as session:
            try:
                yield session
            finally:
                closed.append(True)

    monkeypatch.setattr(app.state.store, "session", tracked_session)
    with pytest.raises(RuntimeError, match="caller failed"), snapshot_set(source_set):
        raise RuntimeError("caller failed")
    assert closed
    assert counts(app) == before


def test_snapshot_set_cannot_be_used_as_a_single_source_preparation(source_set):
    with snapshot_set(source_set) as value:
        with pytest.raises(PreparationError):
            _snapshot(value)
