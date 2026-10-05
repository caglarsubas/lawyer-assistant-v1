"""Real isolated two-source review ledgers and TEST-ONLY external signatures."""

import copy
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from rdflib import RDF
from test_provision_mappings import review
from test_public_sources import source as source_fixture
from test_release_authorization import sha, signed
from test_release_snapshot import counts, operator_id
from test_release_snapshot_set import make_source_set
from test_source_reviews import assess, assign, revoke
from test_workspace import workspace as workspace_fixture

from app.graph_release import LA, _load_serving
from app.main import create_app
from app.release_authorization import AuthorizationError, _packet_tools
from app.release_set_authorization import ReleaseSetAuthorization, build_set_authorization_body
from app.release_set_preparation import compile_review_set
from app.release_set_promotion import signing_inputs
from app.release_snapshot import REQUIRED_USES, readonly_store
from app.release_snapshot_set import SnapshotSetRequest, locked_snapshot_set

workspace = workspace_fixture
source = source_fixture
ONTOLOGY = Path(__file__).resolve().parents[2] / "ontology"
PACKET_SCHEMA = "legal-review-source-set-packet-v1"


def public_version(fixture, directory, *, public_reviewer="TEST-ONLY PUBLIC SET REVIEW"):
    """A fresh external public review creates a new release, never mutates an old one."""
    directory.mkdir()
    files, tools = fixture["files"], fixture["tools"]
    serving = _load_serving()
    reviewed_at = datetime.now(timezone.utc).isoformat()
    inputs = signing_inputs(files, ontology_sha256=serving._release.ontology_digest(ONTOLOGY),
                            public_reviewer=public_reviewer, reviewed_at=reviewed_at)
    for name, raw in inputs.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    attestation = directory / "TEST-ONLY-external-review.json"
    signed(attestation, tools.parse_json(inputs["public-review-body.json"]), fixture["key"], tools)
    graph_paths = {family: directory / "inputs" / f"{family}.ttl" for family in ("structure", "jurisprudence")}
    serving._release.create_bundle(ONTOLOGY, graph_paths, directory / "evidence", directory / "bundle",
                                   attestation, fixture["public_key"])
    serving.prepare(directory / "bundle", fixture["public_key"], directory / "prepared")
    info = serving.validate_prepared(directory / "prepared", fixture["public_key"])
    destination = fixture["root"] / info["release_id"]
    destination.mkdir(parents=True)
    with readonly_store(fixture["app"].state.settings) as store:
        packet = tools.sealed_files(files, store, schema_version=PACKET_SCHEMA)
        tools.atomic_packet(destination / "packet", packet)
    packet_digest = sha(packet["manifest.json"])
    approved = datetime.now(timezone.utc)
    expires = (approved + timedelta(hours=12)).isoformat()
    permissions = [{**permission, "expires_at": expires} for permission in fixture["source_permissions"]]
    body = build_set_authorization_body(info, files, packet_digest, fixture["epoch"],
                                        "PRIVATE SET APPROVER", approved.isoformat(), expires, permissions)
    auth_path = destination / "authorization.json"
    signed(auth_path, body, fixture["key"], tools)
    return {**fixture, "info": info, "body": body, "auth_path": auth_path,
            "packet_digest": packet_digest, "source_permissions": permissions}


@pytest.fixture
def authorized_set(workspace, source, tmp_path):
    mappings = make_source_set(workspace, source)
    app, _, sources, _, _ = mappings[0]
    tools = _packet_tools()
    registry, resolutions, selection, evidence, permissions = [], [], [], {}, []
    for index, mapping in enumerate(mappings):
        _, client, _, source_id, base = mapping
        proof = f"PRIVATE TEST-ONLY source {index} rights identity and audience proof".encode()
        proof_hash = sha(proof)
        evidence[proof_hash] = proof
        changed = assess(client, base + "/review", 5, "rights", evidence_refs=[
            {"reference": "PRIVATE SOURCE-SPECIFIC PROOF", "sha256": proof_hash}],
                         permitted_uses=sorted(REQUIRED_USES))
        assert changed.status_code == 200, changed.text
        current = client.get(base + "/provision-mappings").json()
        item = current["items"][0]
        changed = review(mapping, item["id"], revision=2, source_revision=6,
                         resolution={**item["resolution"], "valid_from": "2011-01-01", "valid_until": "2012-01-01",
                                     "text_role": "operative_text"},
                         evidence_refs=[{"reference": "PRIVATE MAPPING PROOF", "sha256": proof_hash}])
        assert changed.status_code == 200, changed.text
        ids = [f"urn:tr-law:{kind}:set-fixture-{index}"
               for kind in ("instrument", "provision", "provision-version")]
        registry.extend({"id": value, "kind": kind, "parent_id": parent, "evidence_sha256": [proof_hash]}
                        for value, kind, parent in ((ids[0], "instrument", None), (ids[1], "provision", ids[0]),
                                                    (ids[2], "provision_version", ids[1])))
        resolutions.append({"source_id": source_id, "items": [{"mapping_id": item["id"],
                            "instrument_id": ids[0], "provision_id": ids[1], "provision_version_id": ids[2]}]})
        selection.append({"source_id": source_id, "expected_source_review_revision": 6, "expected_mapping_revision": 3})
        permissions.append({"source_id": source_id, "audience": "deployment_shared",
                            "permitted_uses": sorted(REQUIRED_USES), "evidence_sha256": proof_hash,
                            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    request = SnapshotSetRequest.model_validate({"schema_version": "legal-review-source-selection-v1",
                                                "sources": selection})
    with readonly_store(app.state.settings) as store:
        with locked_snapshot_set(store, sources, operator_id=operator_id(app), request=request) as snapshot:
            files, summary = compile_review_set(snapshot,
                {"schema_version": "legal-identity-registry-v1", "entities": registry},
                {"schema_version": "provision-source-set-resolutions-v1", "sources": resolutions}, evidence, ONTOLOGY)
    assert summary["rdf_generated"] and summary["assertion_count"] == 4
    key = Ed25519PrivateKey.generate()  # TEST ONLY; never touches deployment credentials.
    public_key = tmp_path / "TEST-ONLY-set-key.pem"
    public_key.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo))
    epoch = str(uuid4())
    epoch_path = app.state.settings.data_dir / "publication-epoch"
    epoch_path.write_text(epoch + "\n")
    fixture = {"app": app, "mappings": mappings, "sources": sources, "tools": tools, "files": files,
               "key": key, "public_key": public_key, "epoch": epoch, "epoch_path": epoch_path,
               "root": app.state.settings.data_dir / "release-authorizations", "request": request,
               "source_permissions": sorted(permissions, key=lambda value: value["source_id"])}
    return public_version(fixture, tmp_path / "initial-set-release")


@contextmanager
def guard_set(fixture, *, action="read", info=None):
    with readonly_store(fixture["app"].state.settings) as store:
        authorization = ReleaseSetAuthorization(store, fixture["sources"], fixture["root"],
                                                 fixture["public_key"], ONTOLOGY, fixture["epoch_path"])
        with authorization(info or fixture["info"], action) as receipt:
            yield receipt


def rewrite_set(fixture, **changes):
    body = {**fixture["body"], **changes}
    signed(fixture["auth_path"], body, fixture["key"], fixture["tools"])
    return body


def change_second(fixture, kind):
    mapping = sorted(fixture["mappings"], key=lambda value: value[3])[1]
    app, client, sources, source_id, base = mapping
    if kind == "rights":
        response = assess(client, base + "/review", 6, "rights", decision="needs_changes")
        assert response.status_code == 200, response.text
    elif kind == "mapping":
        item = client.get(base + "/provision-mappings").json()["items"][0]
        response = review(mapping, item["id"], revision=3, source_revision=6, decision="rejected")
        assert response.status_code == 200, response.text
    elif kind == "owner":
        response = assign(client, base + "/review", revision=6, action="release")
        assert response.status_code == 200, response.text
    else:
        raw = sources.root / source_id / "raw.bin"
        raw.chmod(0o600)
        raw.write_bytes(raw.read_bytes() + b"CHANGED SECOND SOURCE")


@pytest.mark.parametrize("action", ["install", "activate", "rollback", "read"])
def test_exact_set_authorization_allows_only_a_safe_receipt_without_ledger_writes(authorized_set, action):
    before = counts(authorized_set["app"])
    with guard_set(authorized_set, action=action) as receipt:
        assert receipt == {"release_id": authorized_set["info"]["release_id"], "current": True}
        assert "PRIVATE" not in json.dumps(receipt)
    assert counts(authorized_set["app"]) == before


@pytest.mark.parametrize("kind", ["rights", "mapping", "package", "owner"])
@pytest.mark.parametrize("during", [False, True], ids=["entry", "exit"])
def test_only_second_source_change_invalidates_the_whole_set(authorized_set, kind, during):
    if not during:
        change_second(authorized_set, kind)
    with pytest.raises(AuthorizationError), guard_set(authorized_set):
        if during:
            change_second(authorized_set, kind)
        else:
            pytest.fail("A stale second source must not authorize the set")


@pytest.mark.parametrize("kind", ["inactive", "role", "firm"])
def test_operator_must_remain_active_authorized_and_in_the_bound_firm(authorized_set, kind):
    revoke(authorized_set["app"], kind)
    with pytest.raises(AuthorizationError), guard_set(authorized_set):
        pytest.fail("A signed set cannot override operator and firm authorization")


def test_signed_source_binding_cannot_omit_duplicate_or_substitute_members(authorized_set):
    original = authorized_set["body"]["source_binding"]
    for kind in ("omit", "duplicate", "substitute", "operator", "firm"):
        binding = copy.deepcopy(original)
        if kind == "omit":
            binding["sources"].pop()
        elif kind == "duplicate":
            binding["sources"][1] = copy.deepcopy(binding["sources"][0])
        elif kind == "substitute":
            binding["sources"][1]["source_id"] = "f" * 64
        elif kind == "operator":
            binding["operator_id"] = "different-private-operator"
        else:
            binding["firm_id"] = "different-private-firm"
        rewrite_set(authorized_set, source_binding=binding)
        with pytest.raises(AuthorizationError), guard_set(authorized_set):
            pytest.fail(f"Signed {kind} binding must be denied")


def test_every_source_needs_its_own_bound_audience_permission(authorized_set):
    original = authorized_set["body"]["source_permissions"]
    supplied = copy.deepcopy(list(reversed(original)))
    before = copy.deepcopy(supplied)
    existing = authorized_set["body"]
    rebuilt = build_set_authorization_body(
        authorized_set["info"], authorized_set["files"], authorized_set["packet_digest"],
        existing["publication_epoch"], existing["reviewer"], existing["approved_at"], existing["expires_at"], supplied)
    assert rebuilt["source_permissions"] == original and supplied == before
    for kind in ("omit", "duplicate", "wrong_source", "wrong_audience", "missing_use", "cross_source_proof", "order"):
        permissions = copy.deepcopy(original)
        if kind == "omit":
            permissions.pop()
        elif kind == "duplicate":
            permissions[1] = copy.deepcopy(permissions[0])
        elif kind == "wrong_source":
            permissions[1]["source_id"] = "f" * 64
        elif kind == "wrong_audience":
            permissions[1]["audience"] = "one_firm"
        elif kind == "missing_use":
            permissions[1]["permitted_uses"].remove("export")
        elif kind == "order":
            permissions.reverse()
        else:
            # Both proofs exist physically; source A's proof must not license B.
            permissions[1]["evidence_sha256"] = permissions[0]["evidence_sha256"]
        rewrite_set(authorized_set, source_permissions=permissions)
        with pytest.raises(AuthorizationError), guard_set(authorized_set):
            pytest.fail(f"Signed {kind} source permission must be denied")


def test_global_and_per_source_expiry_never_extend_one_another(authorized_set):
    now = datetime.now(timezone.utc)
    original = authorized_set["body"]
    mutations = [
        {"expires_at": (now - timedelta(seconds=1)).isoformat()},
        {"approved_at": (now + timedelta(hours=1)).isoformat()},
        {"approved_at": "2010-01-01T00:00:00Z"},
        {"expires_at": (now + timedelta(days=91)).isoformat()},
    ]
    for expires in ((now - timedelta(seconds=1)).isoformat(), now.replace(tzinfo=None).isoformat(),
                    (now + timedelta(days=91)).isoformat()):
        permissions = copy.deepcopy(original["source_permissions"])
        permissions[1]["expires_at"] = expires
        mutations.append({"source_permissions": permissions})
    for changes in mutations:
        rewrite_set(authorized_set, **changes)
        with pytest.raises(AuthorizationError), guard_set(authorized_set):
            pytest.fail("Signed expiry or approval dates must fail closed")


def test_authorization_expiring_inside_guard_is_rejected(authorized_set, monkeypatch):
    import app.release_authorization as legacy
    import app.release_set_authorization as batch

    class Future(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime.now(timezone.utc) + timedelta(days=2)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    with pytest.raises(AuthorizationError), guard_set(authorized_set):
        monkeypatch.setattr(legacy, "datetime", Future)
        monkeypatch.setattr(batch, "datetime", Future)


def test_expiry_crossed_during_final_public_validation_still_denies(authorized_set, monkeypatch):
    import app.release_set_authorization as batch

    class Future(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime.now(timezone.utc) + timedelta(days=2)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    original = batch.ReleaseSetAuthorization._public_match
    visits = []

    def finish_after_expiry(*args, **kwargs):
        result = original(*args, **kwargs)
        visits.append(True)
        if len(visits) == 2:
            monkeypatch.setattr(batch, "datetime", Future)
        return result

    monkeypatch.setattr(batch.ReleaseSetAuthorization, "_public_match", finish_after_expiry)
    with pytest.raises(AuthorizationError), guard_set(authorized_set):
        pass
    assert len(visits) == 2


@pytest.mark.parametrize("kind", ["epoch", "packet", "key", "public_graph", "public_evidence"])
def test_exit_revalidates_private_and_public_bytes(authorized_set, kind):
    fixture = authorized_set
    with pytest.raises(AuthorizationError), guard_set(fixture):
        if kind == "epoch":
            fixture["epoch_path"].write_text(str(uuid4()) + "\n")
        elif kind == "packet":
            path = fixture["auth_path"].parent / "packet" / "registry.json"
            path.write_bytes(path.read_bytes() + b"\n")
        elif kind == "key":
            fixture["public_key"].write_bytes(b"PRIVATE REPLACEMENT KEY")
        else:
            bundle = fixture["info"]["bundle_path"]
            path = bundle / "inputs/structure.ttl" if kind == "public_graph" else next((bundle / "evidence").iterdir())
            path.chmod(0o600)
            path.write_bytes(path.read_bytes() + b"UNBOUND PUBLIC CHANGE")


def test_wrong_schema_cannot_dispatch_set_packet_to_legacy_authorization(authorized_set):
    from app.release_authorization import ReleaseAuthorization

    rewrite_set(authorized_set, schema_version="legal-release-authorization-v1",
                transformation="reviewed-provision-promotion-v1")
    with readonly_store(authorized_set["app"].state.settings) as store:
        gate = ReleaseAuthorization(store, authorized_set["sources"], authorized_set["root"],
                                    authorized_set["public_key"], ONTOLOGY, authorized_set["epoch_path"])
        with pytest.raises(AuthorizationError), gate(authorized_set["info"], "read"):
            pytest.fail("A v1 envelope cannot authorize a source-set packet")


def test_real_app_dispatch_search_and_second_source_revocation(authorized_set, tmp_path, monkeypatch):
    fixture, serving = authorized_set, _load_serving()
    root = tmp_path / "runtime-volume"

    def authorize(info, action):
        return guard_set(fixture, info=info, action=action)

    info = serving.install(root, fixture["info"]["bundle_path"].parent, fixture["public_key"],
                           authorization_guard=authorize)
    serving.activate(root, info["release_id"], fixture["public_key"], expected_current=None,
                     authorization_guard=authorize)
    settings = fixture["app"].state.settings.model_copy(update={
        "graph_release_dir": str(root), "graph_trusted_review_key": str(fixture["public_key"]),
        "opensearch_url": "http://opensearch:9200", "search_release_id": info["release_id"]})
    app = create_app(settings)
    with TestClient(app):
        assert app.state.graph.release_status()["status"] == "verified"
        graph = app.state.graph.release._graphs["structure"]
        hits = []
        authorities = set()
        for assertion in graph.subjects(RDF.type, LA.Assertion):
            authority = str(graph.value(assertion, LA.subject))
            if ":instrument:" not in authority:
                continue
            authorities.add(authority)
            evidence = graph.value(assertion, LA.evidence)
            artifact = graph.value(evidence, LA.artifact)
            hits.append({"_id": "PRIVATE-INDEX-ID", "_index": "law-public-passages", "_source": {
                "passage_id": "PRIVATE-INDEX-ID", "document_id": "PRIVATE-INDEX-DOC",
                "source_version_id": "PRIVATE-INDEX-VERSION", "source_sha256": str(graph.value(artifact, LA.contentHash)),
                "text": str(graph.value(evidence, LA.quotedText)), "title": "PRIVATE-INDEX-TITLE",
                "source_url": "https://example.gov.tr/PRIVATE-INDEX-URL", "locator": str(graph.value(evidence, LA.locator)), "authority_id": authority,
                "release_id": info["release_id"], "visibility": "public", "rights_status": "permitted",
                "review_status": "legally_reviewed", "valid_from": "2011-01-01", "valid_to": "2012-01-01"}})
        assert len(authorities) == 2
        monkeypatch.setattr(app.state.search, "_request", lambda *args: hits)
        found = app.state.search.search("SYNTHETIC TEST ONLY", as_of="2011-06-01")
        assert {hit["authority_id"] for hit in found["hits"]} == authorities
        assert "PRIVATE-INDEX" not in json.dumps(found)
        change_second(fixture, "rights")
        assert app.state.graph.release_status()["status"] == "unavailable"
        monkeypatch.setattr(app.state.search, "_request", lambda *args: pytest.fail("Revoked set must not query search"))
        blocked = app.state.search.search("SYNTHETIC TEST ONLY", as_of="2011-06-01")
        assert blocked["hits"] == [] and blocked["coverage"]["status"] == "unavailable"
        assert "PRIVATE" not in json.dumps(blocked)


def test_actual_guard_rollback_revalidates_both_sources_and_preserves_pointer_on_denial(authorized_set, tmp_path):
    fixture, serving = authorized_set, _load_serving()
    second = public_version(fixture, tmp_path / "fresh-public-review", public_reviewer="TEST-ONLY SECOND PUBLIC REVIEW")
    root = tmp_path / "rollback-volume"

    def authorize(info, action):
        return guard_set(fixture, info=info, action=action)

    for current in (fixture, second):
        serving.install(root, current["info"]["bundle_path"].parent, fixture["public_key"], authorization_guard=authorize)
    first_id, second_id = fixture["info"]["release_id"], second["info"]["release_id"]
    assert first_id != second_id
    serving.activate(root, first_id, fixture["public_key"], expected_current=None, authorization_guard=authorize)
    serving.activate(root, second_id, fixture["public_key"], expected_current=first_id, expected_sequence=1,
                     authorization_guard=authorize)
    rolled = serving.rollback(root, fixture["public_key"], expected_current=second_id, expected_sequence=2,
                              authorization_guard=authorize)
    assert rolled["release_id"] == first_id and rolled["sequence"] == 3
    serving.activate(root, second_id, fixture["public_key"], expected_current=first_id, expected_sequence=3,
                     authorization_guard=authorize)
    before = serving.read_pointer(root)
    change_second(fixture, "rights")
    with pytest.raises(ValueError):
        serving.rollback(root, fixture["public_key"], expected_current=second_id, expected_sequence=4,
                         authorization_guard=authorize)
    assert serving.read_pointer(root) == before
