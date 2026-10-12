"""Encrypted component requests with TEST-ONLY source rights and public reviews."""
import copy
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_graph_b_snapshot import current as current_fixture
from test_graph_b_snapshot import incoming as incoming_fixture
from test_graph_b_snapshot import opened
from test_graph_b_snapshot import source as source_fixture
from test_graph_b_snapshot import workspace as workspace_fixture
from test_release_authorization import signed
from test_source_reviews import assess

from app import graph_b_publication as publication
from app.config import ROOT
from app.graph_release import _load_serving
from app.release_authorization import AuthorizationError, ReleaseAuthorization
from app.release_preparation import canonical, digest
from app.release_snapshot import REQUIRED_USES, SnapshotError, readonly_store

current = current_fixture
incoming = incoming_fixture
source = source_fixture
workspace = workspace_fixture


def command_module():
    spec = importlib.util.spec_from_file_location("graph_b_publication_command_test", ROOT / "scripts" / "prepare_graph_b_publication.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def prepare(current, tmp_path):
    selection = tmp_path / "selection.json"
    selection.write_bytes(canonical(current["request"].model_dump()))
    evidence = tmp_path / "audience-evidence"
    evidence.mkdir()
    (evidence / (digest(current["audience"]) + ".bin")).write_bytes(current["audience"])
    output = tmp_path / "private-packet"
    command = command_module()
    report = command.prepare(current["app"].state.settings, operator_id=current["operator_id"],
        selection=selection, evidence_dir=evidence, output=output)
    return command, output, report


@pytest.fixture
def packet(current, tmp_path):
    return prepare(current, tmp_path)


def test_private_packet_sealed_encrypted_and_public_files_exact(current, packet):
    command, path, report = packet
    assert report == {"packet_created": True, "signed": False, "publication_eligible": False,
        "encrypted_private_evidence": True, "public_assertions": 6, "national_release_serving_authorized": False}
    assert command.validate(current["app"].state.settings, path, operator_id=current["operator_id"])["current_at_validation"]
    with readonly_store(current["app"].state.settings) as reader, opened(current, reader) as snapshot:
        files, _ = command.io.read_packet(path, reader, schema_version=publication.PACKET_SCHEMA)
        private = publication.verify_files(reader, files, snapshot, ROOT / "ontology")
        assert private["binding"] == snapshot["binding"]
        assert private["signed_review_event"]["credential_data"]
        assert private["signed_review_event"]["accepted_key"]
        assert not set(private["public_input_paths"]) & {publication.PRIVATE_FILE, "NOTICE.json", "manifest.hmac"}
        flat = b"\n".join(file.read_bytes() for file in path.rglob("*") if file.is_file())
        for confidential in (current["operator_id"].encode(), current["request"].reviewer_id.encode(),
                current["audience"], b"credential_data", b"appointment", b"accepted_key", b"firm_id", b"context_id"):
            assert confidential not in flat
        assert b"TEST-ONLY PUBLIC REVIEWER" in flat  # Intentional public assertion label.
        assert private["schema_version"] == publication.PRIVATE_SCHEMA
    assert all((file.stat().st_mode & 0o777) == 0o600 for file in path.rglob("*") if file.is_file())
    assert (path.stat().st_mode & 0o777) == 0o700


@pytest.mark.parametrize("change", ["ciphertext", "wrong-deployment", "binding", "credential", "audience", "public-rdf", "extra-file"])
def test_integrity_seal_is_not_current_review_or_publication_permission(current, packet, change):
    command, path, _ = packet
    with readonly_store(current["app"].state.settings) as reader:
        files, _ = command.io.read_packet(path, reader, schema_version=publication.PACKET_SCHEMA)
        value = publication.private_evidence(reader, files)
        if change == "ciphertext":
            files[publication.PRIVATE_FILE] = files[publication.PRIVATE_FILE][:-8] + b"AAAAAAAA"
        elif change == "wrong-deployment":
            from cryptography.fernet import Fernet
            files[publication.PRIVATE_FILE] = Fernet(Fernet.generate_key()).encrypt(canonical(value))
        elif change == "public-rdf":
            files["inputs/jurisprudence.ttl"] += b"# substituted bytes\n"
        elif change == "extra-file":
            files["private-account.json"] = b"{}"
        else:
            if change == "binding":
                value["binding"]["signed_review_sha256"] = "f" * 64
            if change == "credential":
                value["signed_review_event"]["credential_data"] = "changed"
            if change == "audience":
                value["audience_evidence"][digest(current["audience"])] = "Y2hhbmdlZA=="
            files[publication.PRIVATE_FILE] = reader.seal_preparation(value)
        # Even a correctly deployment-sealed changed packet must reconstruct the
        # exact review and source bytes, not accept the integrity seal as approval.
        changed = path.parent / "changed-packet"
        command.io.atomic_packet(changed, command.io.sealed_files(files, reader, schema_version=publication.PACKET_SCHEMA))
    with pytest.raises((ValueError, SnapshotError)):
        command.validate(current["app"].state.settings, changed, operator_id=current["operator_id"])


def test_source_change_keeps_old_packet_but_withholds_current_validation(current, packet):
    command, path, _ = packet
    item = current["evidence"][0][2]
    assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    with pytest.raises(SnapshotError):
        command.validate(current["app"].state.settings, path, operator_id=current["operator_id"])
    assert path.exists()  # Preserved evidence is not silently rewritten/deleted.


def test_late_trust_change_removes_only_newly_owned_output(current, tmp_path, monkeypatch):
    command = command_module()
    selection = tmp_path / "selection.json"
    selection.write_bytes(canonical(current["request"].model_dump()))
    evidence = tmp_path / "audience"
    evidence.mkdir()
    (evidence / (digest(current["audience"]) + ".bin")).write_bytes(current["audience"])
    output = tmp_path / "withheld"
    original = command.io.atomic_packet
    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        current["key"].write_bytes(b"rotated invalid key")
        return value
    monkeypatch.setattr(command.io, "atomic_packet", changed)
    with pytest.raises(SnapshotError):
        command.prepare(current["app"].state.settings, operator_id=current["operator_id"], selection=selection,
                        evidence_dir=evidence, output=output)
    assert not output.exists()


def request_args(current, snapshot, files, private):
    timestamp = datetime.now(timezone.utc)
    expires = (timestamp + timedelta(hours=1)).isoformat()
    info = {"release_id": "a" * 64, "serving_sha256": "b" * 64, "ontology_sha256": snapshot["binding"]["ontology_sha256"],
        "review": {"verified": True, "key_sha256": "c" * 64, "reviewed_at": snapshot["signed_review_history"][-1]["envelope"]["body"]["reviewed_at"]}}
    permissions = [{"source_id": key, "audience": "deployment_shared", "permitted_uses": sorted(REQUIRED_USES),
        "evidence_sha256": digest(current["audience"]), "expires_at": expires} for key in sorted(snapshot["packages"])]
    return info, {"packet_sha256": "d" * 64, "epoch": str(uuid4()), "reviewer": "TEST-ONLY PRIVATE SOURCE APPROVER",
        "approved_at": timestamp.isoformat(), "expires_at": expires, "source_permissions": permissions}


@pytest.mark.parametrize("change", ["missing-source", "duplicate-source", "wrong-source", "audience", "uses", "proof", "permission-expiry",
    "expired", "future", "overlong", "appointment", "epoch", "extra-field", "private-binding", "unverified-public-review"])
def test_component_request_requires_each_current_source_and_bounded_permission(current, change):
    with readonly_store(current["app"].state.settings) as reader, opened(current, reader) as snapshot:
        files = publication.prepare_files(reader, snapshot, {digest(current["audience"]): current["audience"]}, ROOT / "ontology")
        private = publication.private_evidence(reader, files)
        info, args = request_args(current, snapshot, files, private)
        permissions = args["source_permissions"]
        if change == "missing-source":
            permissions.pop()
        if change == "duplicate-source":
            permissions[1] = copy.deepcopy(permissions[0])
        if change == "wrong-source":
            permissions[0]["source_id"] = "f" * 64
        if change == "audience":
            permissions[0]["audience"] = "firm_only"
        if change == "uses":
            permissions[0]["permitted_uses"].remove("indexing")
        if change == "proof":
            permissions[0]["evidence_sha256"] = "f" * 64
        if change == "permission-expiry":
            permissions[0]["expires_at"] = args["approved_at"]
        if change == "expired":
            args["expires_at"] = args["approved_at"]
        if change == "future":
            args["approved_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        if change in {"overlong", "appointment"}:
            args["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=91 if change == "overlong" else 31)).isoformat()
        if change == "epoch":
            args["epoch"] = "not an epoch"
        if change == "extra-field":
            permissions[0]["extra"] = True
        if change == "private-binding":
            private["binding"]["snapshot_sha256"] = "f" * 64
        if change == "unverified-public-review":
            info["review"]["verified"] = False
        with pytest.raises(publication.PublicationPreparationError):
            publication.permission_request(files, private, snapshot, info, **args)


def prepare_public(current, packet, tmp_path):
    command, path, _ = packet
    key = Ed25519PrivateKey.generate()  # TEST ONLY; no production signing authority.
    public_key = tmp_path / "TEST-ONLY-national-review.pem"
    public_key.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    current["app"].state.settings.graph_trusted_review_key = str(public_key)
    with readonly_store(current["app"].state.settings) as reader:
        files, _ = command.io.read_packet(path, reader, schema_version=publication.PACKET_SCHEMA)
    public_review = json.loads(files["public-review-body.json"])
    public_review.update(reviewer="TEST-ONLY NATIONAL PUBLIC REVIEWER", reviewed_at=datetime.now(timezone.utc).isoformat())
    attestation = tmp_path / "TEST-ONLY-public-attestation.json"
    signed(attestation, public_review, key, command.io)
    serving = _load_serving()
    bundle, prepared = tmp_path / "public-bundle", tmp_path / "prepared-component"
    serving._release.create_bundle(ROOT / "ontology", {family: path / "inputs" / (family + ".ttl") for family in ("structure", "jurisprudence")},
        path / "evidence", bundle, attestation, public_key)
    serving.prepare(bundle, public_key, prepared)
    epoch_path = current["app"].state.settings.data_dir / "publication-epoch"
    epoch_path.write_text(str(uuid4()) + "\n")
    return prepared, public_key, epoch_path


def test_real_public_attestation_and_encrypted_unsigned_request_cannot_install(current, packet, tmp_path):
    command, path, _ = packet
    prepared, public_key, _ = prepare_public(current, packet, tmp_path)
    with command.current_packet(current["app"].state.settings, path, current["operator_id"]) as (_, files, _, private, snapshot):
        info, args = request_args(current, snapshot, files, private)
    output = tmp_path / "unsigned-request"
    result = command.request(current["app"].state.settings, prepared, packet=path, operator_id=current["operator_id"],
        reviewer=args["reviewer"], approved_at=args["approved_at"], expires_at=args["expires_at"], source_permissions=args["source_permissions"], output=output)
    assert result == {"component_permission_requested": True, "signed": False, "publication_eligible": False,
                      "national_release_serving_authorized": False}
    with readonly_store(current["app"].state.settings) as reader:
        encrypted, _ = command.io.read_packet(output, reader, schema_version=publication.PACKET_SCHEMA)
        body = reader.decode(SimpleNamespace(payload=encrypted["permission-request.fernet"].decode()))
        assert body["schema_version"] == publication.REQUEST_SCHEMA and body["scope"] == "component_inclusion_only"
        assert body["national_release_serving_authorized"] is False and body["signed"] is False
        assert len(body["source_permissions"]) == 3
        assert current["operator_id"].encode() not in b"\n".join(encrypted.values())
        info = _load_serving().validate_prepared(prepared, public_key)
        gate = ReleaseAuthorization(reader, current["sources"], tmp_path / "absent-authorization", public_key, ROOT / "ontology",
                                    current["app"].state.settings.data_dir / "publication-epoch")
        with pytest.raises(AuthorizationError), gate(info, "install"):
            pytest.fail("Unsigned inclusion requests are never runtime publication grants")
        with pytest.raises(ValueError, match="authorization guard"):
            _load_serving().install(tmp_path / "serving", prepared, public_key)


def test_epoch_change_after_request_write_withholds_new_artifact(current, packet, tmp_path, monkeypatch):
    command, path, _ = packet
    prepared, _, epoch_path = prepare_public(current, packet, tmp_path)
    with command.current_packet(current["app"].state.settings, path, current["operator_id"]) as (_, files, _, private, snapshot):
        _, args = request_args(current, snapshot, files, private)
    original = command.io.atomic_packet
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        epoch_path.write_text(str(uuid4()) + "\n")
        return result
    monkeypatch.setattr(command.io, "atomic_packet", changed)
    output = tmp_path / "withheld-request"
    with pytest.raises(ValueError):
        command.request(current["app"].state.settings, prepared, packet=path, operator_id=current["operator_id"],
            reviewer=args["reviewer"], approved_at=args["approved_at"], expires_at=args["expires_at"], source_permissions=args["source_permissions"], output=output)
    assert not output.exists()


def test_parser_and_failures_never_print_private_source_selection(current, capsys, monkeypatch):
    command = command_module()
    with pytest.raises(SystemExit):
        command.parser().parse_args(["accept", "--operator-id", current["operator_id"]])
    from app import config
    monkeypatch.setattr(config, "load_settings", lambda: current["app"].state.settings)
    assert command.main(["validate", "/nonexistent-private-packet", "--operator-id", current["operator_id"]]) == 2
    output = capsys.readouterr()
    assert current["operator_id"] not in output.err and "publication_performed" in output.err


def test_atomic_rename_interruption_discards_only_new_packet(current, tmp_path, monkeypatch):
    command = command_module()
    selection = tmp_path / "selection.json"
    selection.write_bytes(canonical(current["request"].model_dump()))
    evidence = tmp_path / "audience"
    evidence.mkdir()
    (evidence / (digest(current["audience"]) + ".bin")).write_bytes(current["audience"])
    output = tmp_path / "interrupted-packet"
    original = command.io._rename_exclusive
    def interrupt(*args):
        original(*args)
        raise KeyboardInterrupt()
    monkeypatch.setattr(command.io, "_rename_exclusive", interrupt)
    with pytest.raises(KeyboardInterrupt):
        command.prepare(current["app"].state.settings, operator_id=current["operator_id"], selection=selection,
                        evidence_dir=evidence, output=output)
    assert not output.exists() and not list(tmp_path.glob(".legal-review-*"))
    assert not list(tmp_path.glob(".*.preparation-lock"))


def test_another_source_accepted_proof_cannot_fill_this_source_permission(workspace, incoming, tmp_path):
    from test_decision_equivalence import pins
    from test_decision_equivalence import prepare as equivalence_prepare
    from test_graph_b_review import accept
    from test_graph_b_review import prepare as review_prepare

    from app.graph_b_snapshot import SnapshotRequest
    app, client = workspace[:2]
    proofs = [f"TEST-ONLY source {index} audience permission evidence".encode() for index in range(3)]
    evidence_set = equivalence_prepare(app, client, *incoming, permitted_uses=sorted(REQUIRED_USES),
        rights_evidence=lambda index, item: [{"reference": "TEST-ONLY exact source", "sha256": digest(proofs[index])}])
    signed_review = review_prepare(evidence_set, tmp_path)
    result = accept(evidence_set, signed_review)
    assert result.status_code == 200, result.text
    body = result.json()["current"]["envelope"]["body"]
    fixture = {"app": app, "sources": incoming[0], "operator_id": body["operator_id"], "key": signed_review[4],
        "request": SnapshotRequest(schema_version="signed-graph-b-selection-v1",
            decision_source_ids=sorted(item[3] for item in evidence_set[0][:2]), register_source_id=evidence_set[0][2][3],
            reviewer_id=body["reviewer_id"], expected_review_revision=1, expected_equivalence_revision=2, pins=pins(evidence_set)),
        "audience": proofs[0]}
    with readonly_store(app.state.settings) as reader, opened(fixture, reader) as snapshot:
        files = publication.prepare_files(reader, snapshot, {digest(raw): raw for raw in proofs}, ROOT / "ontology")
        private = publication.private_evidence(reader, files)
        info, args = request_args(fixture, snapshot, files, private)
        by_source = {item[3]: digest(raw) for item, raw in zip(evidence_set[0], proofs, strict=True)}
        for permission in args["source_permissions"]:
            permission["evidence_sha256"] = by_source[permission["source_id"]]
        assert publication.permission_request(files, private, snapshot, info, **args)["signed"] is False
        # The substituted proof is real, retained and accepted for another source;
        # a union-of-rights implementation would incorrectly accept it here.
        args["source_permissions"][0]["evidence_sha256"] = args["source_permissions"][1]["evidence_sha256"]
        with pytest.raises(publication.PublicationPreparationError):
            publication.permission_request(files, private, snapshot, info, **args)


def test_request_expiring_during_atomic_output_is_withheld(current, packet, tmp_path, monkeypatch):
    command, path, _ = packet
    prepared, _, _ = prepare_public(current, packet, tmp_path)
    with command.current_packet(current["app"].state.settings, path, current["operator_id"]) as (_, files, _, private, snapshot):
        _, args = request_args(current, snapshot, files, private)
    real_datetime = publication.datetime
    class Expired(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + timedelta(hours=2)
    original = command.io.atomic_packet
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(publication, "datetime", Expired)
        return result
    monkeypatch.setattr(command.io, "atomic_packet", changed)
    output = tmp_path / "expired-request"
    with pytest.raises(ValueError):
        command.request(current["app"].state.settings, prepared, packet=path, operator_id=current["operator_id"],
            reviewer=args["reviewer"], approved_at=args["approved_at"], expires_at=args["expires_at"], source_permissions=args["source_permissions"], output=output)
    assert not output.exists()
