"""TEST-ONLY signed local snapshots; no licences or public permissions issued."""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update
from test_decision_equivalence import pins
from test_decision_equivalence import prepare as equivalence_prepare
from test_graph_b_review import accept
from test_graph_b_review import prepare as review_prepare
from test_jurisprudence_candidates import incoming as incoming_fixture
from test_public_sources import source as source_fixture
from test_source_reviews import assess
from test_workspace import workspace as workspace_fixture

from app.db import User
from app.graph_b_signing import compile_inputs
from app.graph_b_snapshot import SnapshotRequest, locked_graph_b_snapshot
from app.release_preparation import canonical, digest
from app.release_snapshot import REQUIRED_USES, SnapshotError, readonly_store

workspace = workspace_fixture
source = source_fixture
incoming = incoming_fixture


def prepare(workspace, incoming, tmp_path, *, full_rights=True):
    app, client = workspace[:2]
    audience = b"TEST-ONLY source-specific deployment audience evidence; human legal approval not represented"
    evidence = equivalence_prepare(app, client, *incoming,
        permitted_uses=sorted(REQUIRED_USES) if full_rights else None,
        rights_evidence=[{"reference": "TEST-ONLY deployment audience", "sha256": digest(audience)}])
    signed = review_prepare(evidence, tmp_path)
    result = accept(evidence, signed)
    assert result.status_code == 200, result.text
    body = result.json()["current"]["envelope"]["body"]
    request = SnapshotRequest(schema_version="signed-graph-b-selection-v1",
        decision_source_ids=sorted(item[3] for item in evidence[0][:2]), register_source_id=evidence[0][2][3],
        reviewer_id=body["reviewer_id"], expected_review_revision=1, expected_equivalence_revision=2, pins=pins(evidence))
    return {"app": app, "evidence": evidence, "signed": signed, "request": request, "operator_id": body["operator_id"],
            "key": signed[4], "audience": audience, "sources": incoming[0]}


@pytest.fixture
def current(tmp_path, synthetic_signed_graph_b_seed):
    from graph_b_test_seeds import cloned_signed_snapshot
    with cloned_signed_snapshot(synthetic_signed_graph_b_seed, tmp_path) as value:
        yield value


def opened(fixture, reader, **changes):
    return locked_graph_b_snapshot(reader, fixture["sources"], operator_id=fixture["operator_id"],
        request=fixture["request"], trusted_key=fixture["key"], ontology_root=__import__("app.config", fromlist=["ROOT"]).ROOT / "ontology",
        **changes)


def test_local_snapshot_reproduces_http_signing_bytes_without_http_identity(current):
    from test_graph_b_signing import download

    from app.config import ROOT
    with readonly_store(current["app"].state.settings) as reader:
        with opened(current, reader, shared=True) as snapshot:
            binding = snapshot["binding"]
            assert binding["publication_eligible"] is False and binding["selection"] == current["request"].model_dump()
            assert len(snapshot["signed_review_history"]) == 1 and len(snapshot["equivalence_history"]) == 2
            assert all(source["export_allowed"] for source in snapshot["bound"]["sources"].values())
            generated = compile_inputs(snapshot["packages"], snapshot["decisions"], snapshot["captured"], snapshot["bound"],
                snapshot["equivalence_history"][-1], snapshot["signed_review_history"][-1], ROOT / "ontology")
        assert generated == download(current["evidence"], current["signed"]).json()
        with reader.session() as session:
            actor = session.scalar(select(User).where(User.id == current["operator_id"]))
            actor.active = False
            with pytest.raises(SnapshotError, match="cannot write"):
                session.flush()


@pytest.mark.parametrize("change", ["operator", "reviewer", "review-revision", "equivalence-revision", "pin", "key", "negative"])
def test_stale_or_unqualified_selection_cannot_reconstruct_current_approval(current, change):
    if change in {"operator", "reviewer"}:
        ident = current["operator_id"] if change == "operator" else current["request"].reviewer_id
        with current["app"].state.store.session() as session:
            session.execute(update(User).where(User.id == ident).values(active=False))
            session.commit()
    if change == "review-revision":
        current["request"].expected_review_revision = 2
    if change == "equivalence-revision":
        current["request"].expected_equivalence_revision = 1
    if change == "pin":
        current["request"].pins.source_revisions[current["request"].register_source_id] -= 1
    if change == "key":
        current["key"].write_bytes(b"not a key")
    if change == "negative":
        current["signed"][5].update(expected_review_revision=1, reviewed_at=datetime.now(timezone.utc).isoformat())
        assert accept(current["evidence"], current["signed"], decision="reject").status_code == 200
        current["request"].expected_review_revision = 2
    with readonly_store(current["app"].state.settings) as reader, pytest.raises(SnapshotError), opened(current, reader):
        pytest.fail("Only the exact current independently signed approval is eligible")


def test_export_only_rights_do_not_authorize_publication_uses(workspace, incoming, tmp_path):
    fixture = prepare(workspace, incoming, tmp_path, full_rights=False)
    with readonly_store(fixture["app"].state.settings) as reader, pytest.raises(SnapshotError), opened(fixture, reader):
        pytest.fail("All six source uses must be accepted")


@pytest.mark.parametrize("change", ["returned-ledger", "returned-source", "source-bytes", "trust", "role", "ontology"])
def test_exit_revalidation_withholds_caller_mutations_and_concurrent_changes(current, monkeypatch, change):
    from app.graph_release import _load_serving
    with readonly_store(current["app"].state.settings) as reader, pytest.raises(SnapshotError):
        with opened(current, reader) as snapshot:
            if change == "returned-ledger":
                snapshot["signed_review_history"][-1]["actor"]["name"] = "changed"
            if change == "returned-source":
                next(iter(snapshot["packages"].values())).artifacts["text.txt"] = b"changed"
            if change == "source-bytes":
                (current["sources"].root / current["request"].register_source_id / "text.txt").write_bytes(b"changed")
            if change == "trust":
                current["key"].write_bytes(b"changed")
            if change == "role":
                with current["app"].state.store.session() as session:
                    session.execute(update(User).where(User.id == current["request"].reviewer_id).values(role="lawyer"))
                    session.commit()
            if change == "ontology":
                monkeypatch.setattr(_load_serving()._release, "ontology_digest", lambda *args: "f" * 64)


def test_source_rights_revocation_changes_snapshot_and_never_invents_a_new_pin(current):
    item = current["evidence"][0][2]
    assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    with readonly_store(current["app"].state.settings) as reader, pytest.raises(SnapshotError), opened(current, reader):
        pytest.fail("A stale signed review cannot silently follow new rights")


def test_selection_is_closed_and_revalidated_after_caller_edits(current):
    data = current["request"].model_dump()
    for changes in ({"extra": True}, {"expected_review_revision": True}, {"decision_source_ids": list(reversed(data["decision_source_ids"]))},
                    {"register_source_id": data["decision_source_ids"][0]}, {"register_source_id": "f" * 64 + "\n"}):
        with pytest.raises(ValueError):
            SnapshotRequest.model_validate({**data, **changes})
    current["request"].pins.source_revisions.pop(current["request"].register_source_id)
    with readonly_store(current["app"].state.settings) as reader, pytest.raises(SnapshotError), opened(current, reader):
        pytest.fail("Mutated models must be revalidated")
    assert "publication_eligible" not in json.dumps(data)
    assert digest(canonical(data))
