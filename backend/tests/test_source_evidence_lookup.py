"""Direct identities in invented RDF; actual signed ledger exercised separately."""

import json
from contextlib import contextmanager

import pytest
from sqlalchemy import select
from test_source_corpus import passage, release
from test_workspace import workspace as workspace_fixture

from app import source_corpus
from app.db import Membership, User
from app.firm_rbac import route_permissions
from app.source_corpus import EvidenceLookup, SourceCorpusService

workspace = workspace_fixture


def request(reader, ident, version, **changes):
    return EvidenceLookup.model_validate({"passage_id": ident, "source_version_id": version,
        "expected_release_id": reader.info["release_id"], "expected_serving_sha256": reader.info["serving_sha256"],
        "as_of": "1921-01-01", **changes})


def test_direct_lookup_ignores_lexical_scan_budgets_and_preserves_exact_quote(monkeypatch):
    reader = release()
    ident, version = passage(reader, "last", "TEST ONLY exact \r\n source 😀")
    monkeypatch.setattr(source_corpus, "MAX_PASSAGES", 0)
    monkeypatch.setattr(source_corpus, "SCAN_SECONDS", 0)
    # Even enumeration itself is prohibited: direct lookup uses indexed triples.
    monkeypatch.setattr(reader._resources, "subjects", lambda *_: pytest.fail("Unexpected source scan"))
    result = SourceCorpusService(reader).get_evidence(request(reader, ident, version))
    assert result["status"] == "found" and result["hit"]["text"] == "TEST ONLY exact \r\n source 😀"
    assert result["hit"]["authority_id"] is None and result["hit"]["temporal_applicability"] == "not_assessed"
    assert result["coverage"]["total_expected"] is None and reader.calls == ["entry", "exit"]


def test_private_absent_wrong_version_and_synthetic_are_indistinguishable():
    reader = release()
    ident, version = passage(reader, "public")
    private, private_version = passage(reader, "private", "PRIVATE-CANARY", scope="private")
    synthetic, synthetic_version = passage(reader, "synthetic", synthetic=True)
    service = SourceCorpusService(reader)
    outputs = [service.get_evidence(request(reader, a, b)) for a, b in (
        ("urn:test:absent", version), (private, private_version), (synthetic, synthetic_version), (ident, "urn:test:wrong"))]
    assert all(item == outputs[0] for item in outputs)
    assert outputs[0]["status"] == "unresolved" and outputs[0]["hit"] is None
    assert "PRIVATE" not in json.dumps(outputs)


@pytest.mark.parametrize("failure", ["entry", "exit", "release", "serving"])
def test_permission_and_snapshot_changes_withhold_all_evidence(failure):
    reader = release()
    ident, version = passage(reader, "source")
    spec = request(reader, ident, version)
    @contextmanager
    def guard():
        if failure == "entry":
            raise ValueError("PRIVATE-PERMISSION-ID")
        yield reader.info
        if failure == "exit":
            raise ValueError("PRIVATE-PERMISSION-ID")
    reader.current_guard = guard
    if failure in {"release", "serving"}:
        spec = request(reader, ident, version, **{
            "expected_release_id" if failure == "release" else "expected_serving_sha256": "f" * 64})
    result = SourceCorpusService(reader).get_evidence(spec)
    assert result["status"] == "unavailable" and result["hit"] is None
    assert result["snapshot"]["release_id"] is None and "PRIVATE" not in json.dumps(result)


def test_large_quote_is_withheld_whole_without_truncation(monkeypatch):
    reader = release()
    ident, version = passage(reader, "long", "TEST ONLY " * 2000)
    monkeypatch.setattr(source_corpus, "MAX_RESPONSE_BYTES", 3000)
    result = SourceCorpusService(reader).get_evidence(request(reader, ident, version))
    assert result["status"] == "over_budget" and result["hit"] is None


@pytest.mark.parametrize("changes", [{"expected_release_id": "short"}, {"passage_id": "invalid id"},
    {"as_of": "2026-02-30"}, {"as_of": "2026-2-1"}, {"limit": 100}, {"source_version_id": 1}])
def test_closed_lookup_payload_rejects_invalid_fields(changes):
    reader = release()
    ident, version = passage(reader, "source")
    with pytest.raises(ValueError):
        request(reader, ident, version, **changes)
    assert not reader.calls


def test_api_uses_read_permission_and_checks_membership_before_and_after(workspace, monkeypatch):
    app, client, matter = workspace
    path = f"/api/v1/matters/{matter}/corpus/evidence"
    reader = release()
    ident, version = passage(reader, "source")
    body = request(reader, ident, version).model_dump()
    monkeypatch.setattr(app.state.graph, "release", reader)
    found = client.post(path, json=body)
    assert found.status_code == 200 and found.json()["status"] == "found"
    assert found.headers["cache-control"] == "no-store"
    assert route_permissions(path, "POST") == {"matter.read"}
    calls = []
    def revoke(*args):
        calls.append(True)
        with app.state.store.session() as session:
            user = session.scalar(select(User).where(User.username == "demo"))
            row = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.matter_id == matter))
            session.delete(row)
            session.commit()
        return {"hit": {"text": "PRIVATE-CANARY"}}
    monkeypatch.setattr(SourceCorpusService, "get_evidence", revoke)
    denied = client.post(path, json=body)
    assert denied.status_code == 404 and "PRIVATE-CANARY" not in denied.text
    assert client.post(path, json=body).status_code == 404 and len(calls) == 1
