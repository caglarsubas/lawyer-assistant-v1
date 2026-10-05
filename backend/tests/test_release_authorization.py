"""Synthetic isolated ledgers and TEST-ONLY signatures; no actual legal review."""

import base64
import hashlib
import shutil
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import func, select
from test_provision_mappings import mapping as mapping_fixture
from test_provision_mappings import propose, ready, review
from test_provision_mappings import source as source_fixture
from test_provision_mappings import workspace as workspace_fixture
from test_release_snapshot import operator_id
from test_source_reviews import assess, revoke

from app.db import Audit
from app.graph_release import _load_serving
from app.release_authorization import (
    AuthorizationError,
    ReleaseAuthorization,
    _packet_tools,
    build_authorization_body,
)
from app.release_preparation import compile_review
from app.release_promotion import promoted_graphs
from app.release_snapshot import REQUIRED_USES, locked_snapshot, readonly_store

mapping = mapping_fixture
source = source_fixture
workspace = workspace_fixture
ONTOLOGY = Path(__file__).resolve().parents[2] / "ontology"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def signed(path, body, key, tools):
    path.write_bytes(tools.canonical({"algorithm": "Ed25519", "body": body,
                                     "signature": base64.b64encode(key.sign(tools.canonical(body))).decode()}))


@pytest.fixture
def authorized(mapping, tmp_path):
    app, client, sources, source_id, base = mapping
    tools = _packet_tools()
    proof = b"PRIVATE TEST-ONLY RIGHTS, IDENTITY AND AUDIENCE PROOF"
    evidence_digest = sha(proof)
    ready(mapping, uses=sorted(REQUIRED_USES))
    response = assess(client, base + "/review", 5, "rights", evidence_refs=[
        {"reference": "PRIVATE TEST PROOF", "sha256": evidence_digest}], permitted_uses=sorted(REQUIRED_USES))
    assert response.status_code == 200
    proposed = propose(mapping, source_revision=6).json()["items"][0]
    resolution = {"start": proposed["span"]["start"], "end": proposed["span"]["end"],
                  "instrument_ref": "PRIVATE TEST instrument", "provision_ref": "PRIVATE TEST provision",
                  "provision_version_ref": "PRIVATE TEST version", "text_role": "operative_text",
                  "valid_from": "2011-01-01", "valid_until": "2012-01-01"}
    result = review(mapping, proposed["id"], source_revision=6, resolution=resolution)
    assert result.status_code == 200, result.text
    entities = [("urn:tr-law:instrument:test", "instrument", None),
                ("urn:tr-law:provision:test", "provision", "urn:tr-law:instrument:test"),
                ("urn:tr-law:provision-version:test", "provision_version", "urn:tr-law:provision:test")]
    registry = {"schema_version": "legal-identity-registry-v1", "entities": [
        {"id": identifier, "kind": kind, "parent_id": parent, "evidence_sha256": [evidence_digest]}
        for identifier, kind, parent in entities]}
    resolutions = {"schema_version": "provision-identity-resolutions-v1", "items": [{
        "mapping_id": proposed["id"], "instrument_id": entities[0][0], "provision_id": entities[1][0],
        "provision_version_id": entities[2][0]}]}
    key = Ed25519PrivateKey.generate()  # TEST ONLY, temporary directory.
    public_key = tmp_path / "TEST-ONLY-key.pem"
    public_key.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo))
    epoch = str(uuid4())
    epoch_path = tmp_path / "publication-epoch"
    epoch_path.write_text(epoch + "\n", encoding="ascii")
    root = tmp_path / "release-authorizations"
    with readonly_store(app.state.settings) as store:
        with locked_snapshot(store, sources, operator_id=operator_id(app), source_id=source_id,
                             expected_source_review_revision=6, expected_mapping_revision=2) as snapshot:
            files, summary = compile_review(snapshot, registry, resolutions, {evidence_digest: proof}, ONTOLOGY)
        assert summary["rdf_generated"]
        reviewed_at = datetime.now(timezone.utc).isoformat()
        public_reviewer = "TEST-ONLY PUBLIC REVIEW LABEL"
        promoted = promoted_graphs(files, public_reviewer, reviewed_at)
        graph_paths = {}
        for family, raw in promoted.items():
            path = tmp_path / f"{family}.ttl"
            path.write_bytes(raw)
            graph_paths[family] = path
        serving = _load_serving()
        release = serving._release
        evidence_dir = tmp_path / "public-evidence"
        evidence_dir.mkdir()
        for name in ("candidate/raw.bin", "candidate/text.txt", "candidate/locators.json"):
            raw = files[name]
            (evidence_dir / (sha(raw) + ".bin")).write_bytes(raw)
        review_body = {"reviewer": public_reviewer, "reviewed_at": reviewed_at, "decision": "approve",
                       "scope": "national_ontology_and_assertions", "ontology_sha256": release.ontology_digest(ONTOLOGY),
                       "input_graphs_sha256": {name: release.file_hash(path) for name, path in graph_paths.items()}}
        attestation = tmp_path / "TEST-ONLY-attestation.json"
        signed(attestation, review_body, key, tools)
        release.create_bundle(ONTOLOGY, graph_paths, evidence_dir, tmp_path / "bundle", attestation, public_key)
        serving.prepare(tmp_path / "bundle", public_key, tmp_path / "prepared")
        info = serving.validate_prepared(tmp_path / "prepared", public_key)
        directory = root / info["release_id"]
        directory.mkdir(parents=True)
        packet = tools.sealed_files(files, store)
        tools.atomic_packet(directory / "packet", packet)
        packet_digest = sha(packet["manifest.json"])
        approved_at = datetime.now(timezone.utc)
        body = build_authorization_body(info, files, packet_digest, epoch, "PRIVATE TEST REVIEW IDENTITY",
                                         approved_at.isoformat(), (approved_at + timedelta(days=1)).isoformat(), evidence_digest)
        auth_path = directory / "authorization.json"
        signed(auth_path, body, key, tools)
    return {"mapping": mapping, "tools": tools, "key": key, "public_key": public_key, "root": root,
            "epoch_path": epoch_path, "auth_path": auth_path, "body": body, "files": files,
            "info": info, "packet_digest": packet_digest, "evidence_digest": evidence_digest}


@contextmanager
def guard(fixture, *, action="read", info=None, root=None, public_key=None, epoch_path=None):
    app, _, sources, _, _ = fixture["mapping"]
    with readonly_store(app.state.settings) as store:
        authorization = ReleaseAuthorization(store, sources, root or fixture["root"], public_key or fixture["public_key"],
                                             ONTOLOGY, epoch_path or fixture["epoch_path"])
        with authorization(info or fixture["info"], action) as receipt:
            yield receipt


def rewrite(fixture, **changes):
    body = {**fixture["body"], **changes}
    signed(fixture["auth_path"], body, fixture["key"], fixture["tools"])
    return body


@pytest.mark.parametrize("action", ["install", "activate", "rollback", "read"])
def test_current_exact_private_authorization_allows_only_safe_receipt(authorized, action):
    app = authorized["mapping"][0]
    with app.state.store.session() as session:
        before = session.scalar(select(func.count()).select_from(Audit))
    with guard(authorized, action=action) as receipt:
        assert receipt == {"release_id": authorized["info"]["release_id"], "current": True}
        assert "PRIVATE" not in str(receipt) and "publication_epoch" not in receipt
    with app.state.store.session() as session:
        assert session.scalar(select(func.count()).select_from(Audit)) == before


@pytest.mark.parametrize("change", [
    {"schema_version": "other"}, {"transformation": "automatic-unreviewed-promotion"}, {"decision": "reject"},
    {"audience": "private"}, {"permitted_uses": ["storage"]}, {"reviewer": " "}, {"reviewer": "a\nb"},
    {"release_id": "f" * 64}, {"serving_sha256": "f" * 64}, {"ontology_sha256": "f" * 64},
    {"review_key_sha256": "f" * 64}, {"preparation_manifest_sha256": "f" * 64},
    {"audience_evidence_sha256": "f" * 64}, {"source_binding": {}}, {"publication_epoch": str(uuid4())},
    {"publication_epoch": "not-a-uuid"}, {"approved_at": "2020-01-01"}, {"expires_at": "2020-01-01T00:00:00Z"},
    {"reviewed_claim": True},
])
def test_signed_but_invalid_authorization_is_rejected(authorized, change):
    rewrite(authorized, **change)
    with pytest.raises(AuthorizationError, match="Current private"), guard(authorized):
        pytest.fail("Invalid authorization must not yield")


@pytest.mark.parametrize("kind", ["future_approval", "before_review", "over_90_days", "reversed", "naive_expiry"])
def test_authorization_time_interval_is_bounded_and_after_review(authorized, kind):
    now = datetime.now(timezone.utc)
    changes = {
        "future_approval": {"approved_at": (now + timedelta(hours=1)).isoformat()},
        "before_review": {"approved_at": (now - timedelta(days=1)).isoformat()},
        "over_90_days": {"expires_at": (now + timedelta(days=91)).isoformat()},
        "reversed": {"expires_at": (now - timedelta(days=1)).isoformat()},
        "naive_expiry": {"expires_at": (now + timedelta(days=1)).replace(tzinfo=None).isoformat()},
    }[kind]
    rewrite(authorized, **changes)
    with pytest.raises(AuthorizationError), guard(authorized):
        pytest.fail("Time constraints must fail closed")


@pytest.mark.parametrize("kind", ["unsigned", "wrong_signature", "unknown_field", "wrong_algorithm", "duplicate_field"])
def test_strict_signature_envelope_rejects_forgery(authorized, kind):
    tools = authorized["tools"]
    envelope = tools.parse_json(authorized["auth_path"].read_bytes())
    if kind == "unsigned":
        envelope.pop("signature")
    elif kind == "wrong_signature":
        envelope["signature"] = base64.b64encode(b"0" * 64).decode()
    elif kind == "unknown_field":
        envelope["bypass"] = True
    elif kind == "wrong_algorithm":
        envelope["algorithm"] = "none"
    else:
        authorized["auth_path"].write_bytes(b'{"algorithm":"Ed25519","algorithm":"none"}')
    if kind != "duplicate_field":
        authorized["auth_path"].write_bytes(tools.canonical(envelope))
    with pytest.raises(AuthorizationError), guard(authorized):
        pytest.fail("Bad signature must not yield")


@pytest.mark.parametrize("kind", ["source_change", "mapping_rejection", "inactive", "role", "firm"])
def test_live_review_or_operator_change_blocks_signed_authorization(authorized, kind):
    mapping = authorized["mapping"]
    app, client, _, _, base = mapping
    if kind == "source_change":
        assert assess(client, base + "/review", 6, "legal").status_code == 200
    elif kind == "mapping_rejection":
        identifier = client.get(base + "/provision-mappings").json()["items"][0]["id"]
        assert review(mapping, identifier, 2, 6, "rejected").status_code == 200
    else:
        revoke(app, kind)
    with pytest.raises(AuthorizationError), guard(authorized):
        pytest.fail("Old authorization cannot outlive its bound review state")


@pytest.mark.parametrize("kind", ["authorization", "epoch", "packet", "public_graph", "public_evidence", "public_key"])
def test_exit_revalidates_exact_files_and_keys(authorized, kind):
    with pytest.raises(AuthorizationError), guard(authorized):
        if kind == "authorization":
            rewrite(authorized, reviewer="Changed private reviewer")
        elif kind == "epoch":
            authorized["epoch_path"].write_text(str(uuid4()) + "\n")
        elif kind == "packet":
            path = authorized["auth_path"].parent / "packet" / "registry.json"
            path.write_bytes(path.read_bytes() + b" ")
        elif kind == "public_key":
            authorized["public_key"].write_bytes(b"invalid public key")
        else:
            bundle = authorized["info"]["bundle_path"]
            path = bundle / "inputs/structure.ttl" if kind == "public_graph" else next((bundle / "evidence").iterdir())
            path.chmod(0o600)
            path.write_bytes(path.read_bytes() + b"tampered")


def test_mutated_info_cannot_bypass_prepared_release_integrity(authorized):
    info = {**authorized["info"], "serving_sha256": "f" * 64}
    rewrite(authorized, serving_sha256="f" * 64)
    with pytest.raises(AuthorizationError), guard(authorized, info=info):
        pytest.fail("A matching body and supplied info are not independent verification")


def test_missing_authorization_and_unknown_action_fail_closed(authorized):
    with pytest.raises(AuthorizationError), guard(authorized, action="sign"):
        pytest.fail("There is no signing action")
    authorized["auth_path"].unlink()
    with pytest.raises(AuthorizationError), guard(authorized):
        pytest.fail("No default permit")


def test_unsigned_body_builder_requires_packet_evidence_and_preserves_privacy(authorized):
    body = authorized["body"]
    assert body["reviewer"] == "PRIVATE TEST REVIEW IDENTITY"
    assert body["source_binding"] == authorized["tools"].parse_json(authorized["files"]["binding.json"])
    assert set(body["permitted_uses"]) == REQUIRED_USES
    assert "signature" not in body
    with pytest.raises(AuthorizationError):
        build_authorization_body(authorized["info"], authorized["files"], authorized["packet_digest"],
                                 body["publication_epoch"], body["reviewer"], body["approved_at"], body["expires_at"], "f" * 64)


@pytest.mark.parametrize("kind", ["additional_signed_triple", "additional_manifest_file"])
def test_valid_signed_bundle_cannot_add_unbound_public_content(authorized, tmp_path, kind):
    tools, old = authorized["tools"], authorized["info"]
    serving = _load_serving()
    release = serving._release
    directory = tmp_path / "unbound"
    directory.mkdir()
    if kind == "additional_signed_triple":
        paths = {}
        for family in ("structure", "jurisprudence"):
            raw = (old["bundle_path"] / "inputs" / f"{family}.ttl").read_bytes()
            if family == "structure":
                raw += b'<urn:test-extra> <urn:test-predicate> "Unbound assertion" .\n'
            paths[family] = directory / f"{family}.ttl"
            paths[family].write_bytes(raw)
        attestation_body = {"reviewer": old["review"]["reviewer"], "reviewed_at": old["review"]["reviewed_at"],
                            "decision": "approve", "scope": "national_ontology_and_assertions",
                            "ontology_sha256": old["ontology_sha256"],
                            "input_graphs_sha256": {family: sha(path.read_bytes()) for family, path in paths.items()}}
        attestation = directory / "TEST-ONLY-attestation.json"
        signed(attestation, attestation_body, authorized["key"], tools)
        release.create_bundle(ONTOLOGY, paths, old["bundle_path"] / "evidence", directory / "bundle",
                              attestation, authorized["public_key"])
    else:
        shutil.copytree(old["bundle_path"], directory / "bundle")
        bundle = directory / "bundle"
        (bundle / "UNBOUND-PRIVATE-FILE.txt").write_bytes(b"Do not admit arbitrary signed directory files")
        manifest = tools.parse_json((bundle / "manifest.json").read_bytes())
        manifest["files"]["UNBOUND-PRIVATE-FILE.txt"] = sha((bundle / "UNBOUND-PRIVATE-FILE.txt").read_bytes())
        for name, raw in (("manifest.json", tools.canonical(manifest)),
                          ("manifest.sha256", (sha(tools.canonical(manifest)) + "\n").encode())):
            (bundle / name).chmod(0o600)
            (bundle / name).write_bytes(raw)
    serving.prepare(directory / "bundle", authorized["public_key"], directory / "prepared")
    info = serving.validate_prepared(directory / "prepared", authorized["public_key"])
    target = authorized["root"] / info["release_id"]
    target.mkdir()
    shutil.copytree(authorized["auth_path"].parent / "packet", target / "packet")
    body = {**authorized["body"], "release_id": info["release_id"], "serving_sha256": info["serving_sha256"]}
    signed(target / "authorization.json", body, authorized["key"], tools)
    with pytest.raises(AuthorizationError), guard(authorized, info=info):
        pytest.fail("Even valid signatures cannot broaden the bound preparation input")
