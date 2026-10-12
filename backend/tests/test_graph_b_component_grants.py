"""Invented isolated approvals; all signing keys below are TEST ONLY."""
import base64
import copy
import importlib.util
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_graph_b_publication import packet as packet_fixture
from test_graph_b_publication import prepare_public, request_args
from test_graph_b_snapshot import current as current_fixture
from test_release_authorization import signed
from test_source_reviews import assess

from app import graph_b_component_grants as grants
from app.config import ROOT
from app.graph_release import _load_serving
from app.release_authorization import AuthorizationError, ReleaseAuthorization
from app.release_preparation import canonical
from app.release_snapshot import readonly_store

current = current_fixture
packet = packet_fixture


def command_module():
    spec = importlib.util.spec_from_file_location("graph_b_component_command_test", ROOT / "scripts" / "review_graph_b_component.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def setup(current, packet, tmp_path):
    preparation, path, _ = packet
    prepared, _, epoch = prepare_public(current, packet, tmp_path)
    key = Ed25519PrivateKey.generate()  # TEST ONLY, no deployment key generation.
    public = tmp_path / "TEST-ONLY-component-key.pem"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    settings = current["app"].state.settings
    settings.graph_b_component_trusted_key = str(public)
    command = command_module()
    with preparation.current_packet(settings, path, current["operator_id"]) as (_, files, _, private, snapshot):
        _, args = request_args(current, snapshot, files, private)
    output = tmp_path / "signing-request"
    result = command.request(settings, prepared, packet=path, operator_id=current["operator_id"],
        reviewer=args["reviewer"], approved_at=args["approved_at"], expires_at=args["expires_at"],
        source_permissions=args["source_permissions"], output=output)
    assert result["signature_created"] is False
    with readonly_store(settings) as reader:
        request_files, _ = command.io.read_packet(output, reader, schema_version=grants.PACKET_SCHEMA)
        body = reader.decode(SimpleNamespace(payload=request_files["grant-body.fernet"].decode()))
    envelope = tmp_path / "TEST-ONLY-external-component-grant.json"
    signed(envelope, body, key, command.io)
    return {"command": command, "prepared": prepared, "packet": path, "key": key, "public": public, "epoch": epoch,
            "body": body, "envelope": envelope, "settings": settings, "current": current, "request": output}


def accept(value, tmp_path):
    output = tmp_path / "retained-grant"
    result = value["command"].accept(value["settings"], value["prepared"], packet=value["packet"],
        operator_id=value["current"]["operator_id"], authorization=value["envelope"], output=output)
    assert result == {"component_grant_accepted": True, "publication_performed": False, "national_release_serving_authorized": False}
    return output


@contextmanager
def guarded(value, grant, *, purpose="inspect"):
    info = _load_serving().validate_prepared(value["prepared"], value["command"].io.checked_path(value["settings"].graph_trusted_review_key))
    with readonly_store(value["settings"]) as reader, value["command"].gate(value["settings"], reader).guard(info, grant, purpose=purpose) as receipt:
        yield receipt


@pytest.fixture
def accepted_component(synthetic_component_grant_seed, tmp_path):
    from graph_b_test_seeds import cloned_component_grant
    with cloned_component_grant(synthetic_component_grant_seed, tmp_path / "independent-component-copy") as value:
        yield value


def test_encrypted_external_grant_is_current_but_cannot_serve(current, packet, tmp_path):
    value = setup(current, packet, tmp_path)
    output = accept(value, tmp_path)
    assert value["command"].validate(value["settings"], value["prepared"], grant=output)["current_component_grant"]
    with guarded(value, output, purpose="include") as receipt:
        assert receipt["current"] and receipt["national_release_serving_authorized"] is False
        assert "source_binding" not in receipt and current["operator_id"] not in str(receipt)
    flat = b"\n".join(p.read_bytes() for p in output.rglob("*") if p.is_file())
    for secret in (current["operator_id"].encode(), current["audience"], b"credential_data", b"source_binding", b"signature"):
        assert secret not in flat
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in output.rglob("*") if p.is_file())
    for action in ("install", "activate", "rollback", "read"):
        with pytest.raises(grants.ComponentGrantError), guarded(value, output, purpose=action):
            pytest.fail("Component inclusion never authorizes national serving")
    info = _load_serving().validate_prepared(value["prepared"], value["command"].io.checked_path(value["settings"].graph_trusted_review_key))
    with readonly_store(value["settings"]) as reader:
        national = ReleaseAuthorization(reader, current["sources"], output, value["public"], ROOT / "ontology", value["epoch"])
        with pytest.raises(AuthorizationError), national(info, "install"):
            pytest.fail("Separate grant namespaces cannot be used as national authorization")
    with pytest.raises(ValueError):
        accept(value, tmp_path)
    assert output.exists()  # Existing evidence is never deleted by a repeated acceptance.


@pytest.mark.parametrize("change", ["schema", "unsigned", "extra-body", "extra-envelope", "signature", "algorithm", "key-id", "national", "duplicate"])
def test_strict_signed_envelope_rejects_cross_namespace_and_forgery(tmp_path, change):
    key = Ed25519PrivateKey.generate()  # TEST ONLY; parser/signature tests need no source setup.
    public = tmp_path / "TEST-ONLY.pem"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    # Signature-shape test deliberately uses no live publication context. It can
    # never be accepted; live complete field equality is tested separately below.
    request = {name: None for name in grants.REQUEST_FIELDS}
    request.update(schema_version=grants.REQUEST_SCHEMA, scope="component_inclusion_only", signed=False, national_release_serving_authorized=False)
    from app.graph_b_review import configured_key_path
    body = grants.grant_body(request, configured_key_path(public)[2])
    envelope = {"algorithm": "Ed25519", "body": body, "signature": base64.b64encode(key.sign(canonical(body))).decode()}
    if change == "schema":
        body["schema_version"] = "legal-release-authorization-v1"
    elif change == "unsigned":
        body["signed"] = False
    elif change == "extra-body":
        body["override"] = True
    elif change == "extra-envelope":
        envelope["override"] = True
    elif change == "signature":
        envelope["signature"] = base64.b64encode(b"0" * 64).decode()
    elif change == "algorithm":
        envelope["algorithm"] = "none"
    elif change == "key-id":
        body["component_grant_key_sha256"] = "f" * 64
    elif change == "national":
        body["national_release_serving_authorized"] = True
    raw = canonical(envelope) if change != "duplicate" else b'{"algorithm":"Ed25519","algorithm":"none"}'
    with pytest.raises((ValueError, InvalidSignature)):
        grants.verify_envelope(raw, public)


@pytest.mark.parametrize("change", ["source-permission", "epoch", "key", "public-bytes", "negative-review", "account"])
def test_current_grant_withheld_after_dependency_change(accepted_component, change):
    value, output = accepted_component
    current = value["current"]
    if change == "source-permission":
        item = current["evidence"][0][2]
        assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    elif change == "epoch":
        value["epoch"].write_text(str(uuid4()) + "\n")
    elif change == "key":
        value["public"].write_bytes(b"invalid rotated TEST-ONLY key")
    elif change == "public-bytes":
        info = _load_serving().validate_prepared(value["prepared"], value["command"].io.checked_path(value["settings"].graph_trusted_review_key))
        target = info["bundle_path"] / "inputs/jurisprudence.ttl"
        target.chmod(0o600)
        target.write_bytes(target.read_bytes() + b"# different public bytes\n")
    elif change == "account":
        from app.db import User
        with current["app"].state.store.session() as session:
            session.get(User, current["request"].reviewer_id).active = False
            session.commit()
    else:
        from test_graph_b_review import accept as review_accept
        current["signed"][5].update(expected_review_revision=1, reviewed_at=datetime.now(timezone.utc).isoformat())
        assert review_accept(current["evidence"], current["signed"], decision="reject").status_code == 200
    with pytest.raises(ValueError):
        value["command"].validate(value["settings"], value["prepared"], grant=output)
    assert output.exists()


@pytest.mark.parametrize("change", ["epoch", "grant-key", "public-key", "expiry", "encrypted-grant"])
def test_exit_checks_withhold_after_mid_use_changes(accepted_component, monkeypatch, change):
    value, output = accepted_component
    with pytest.raises(grants.ComponentGrantError), guarded(value, output):
        if change == "epoch":
            value["epoch"].write_text(str(uuid4()) + "\n")
        elif change == "grant-key":
            value["public"].write_bytes(b"rotated invalid TEST-ONLY key")
        elif change == "public-key":
            from pathlib import Path
            Path(value["settings"].graph_trusted_review_key).write_bytes(b"invalid TEST-ONLY public review key")
        elif change == "encrypted-grant":
            target = output / "grant.fernet"
            target.write_bytes(b"changed encrypted bytes")
        else:
            from app import graph_b_publication
            class Later(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime.now(tz) + timedelta(days=2)
            monkeypatch.setattr(graph_b_publication, "datetime", Later)


def test_valid_signature_cannot_replace_source_specific_permission(current, packet, tmp_path):
    value = setup(current, packet, tmp_path)
    body = copy.deepcopy(value["body"])
    body["source_permissions"][0]["evidence_sha256"] = "f" * 64
    signed(value["envelope"], body, value["key"], value["command"].io)
    with pytest.raises(ValueError):
        accept(value, tmp_path)
    assert not (tmp_path / "retained-grant").exists()


def test_late_epoch_change_after_atomic_acceptance_removes_new_output(current, packet, tmp_path, monkeypatch):
    value = setup(current, packet, tmp_path)
    original = value["command"].io.atomic_packet
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        value["epoch"].write_text(str(uuid4()) + "\n")
        return result
    monkeypatch.setattr(value["command"].io, "atomic_packet", changed)
    with pytest.raises(ValueError):
        accept(value, tmp_path)
    assert not (tmp_path / "retained-grant").exists()


def test_independent_trust_roles_and_safe_cli_errors(current, packet, tmp_path, capsys, monkeypatch):
    value = setup(current, packet, tmp_path)
    value["settings"].graph_b_component_trusted_key = value["settings"].graph_trusted_review_key
    with pytest.raises(ValueError):
        accept(value, tmp_path)
    from app import config
    monkeypatch.setattr(config, "load_settings", lambda: value["settings"])
    assert value["command"].main(["validate", "--prepared", str(value["prepared"]), "--grant", "/absent-private-grant"]) == 2
    output = capsys.readouterr()
    assert current["operator_id"] not in output.err and "publication_performed" in output.err


@pytest.mark.parametrize('change', ['epoch', 'public-bytes'])
def test_changes_during_source_exit_reconstruction_are_checked_again(accepted_component, monkeypatch, change):
    value, output = accepted_component
    original = grants.locked_graph_b_snapshot
    @contextmanager
    def changed(*args, **kwargs):
        with original(*args, **kwargs) as snapshot:
            yield snapshot
        if change == 'epoch':
            value['epoch'].write_text(str(uuid4()) + '\n')
        else:
            info = _load_serving().validate_prepared(value['prepared'], value['command'].io.checked_path(value['settings'].graph_trusted_review_key))
            target = info['bundle_path'] / 'inputs/jurisprudence.ttl'
            target.chmod(0o600)
            target.write_bytes(target.read_bytes() + b'# changed during original-source reconstruction\n')
    monkeypatch.setattr(grants, 'locked_graph_b_snapshot', changed)
    with pytest.raises(grants.ComponentGrantError), guarded(value, output):
        pass
