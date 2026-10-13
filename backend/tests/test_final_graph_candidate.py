"""TEST-ONLY final candidate; no deployment key, signed serving grant or activation."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_declared_graph_assembly import accepted, key_pair, prepared
from test_declared_graph_assembly import assembly as assembly_fixture
from test_release_authorization import signed
from test_source_reviews import assess

from app.config import ROOT
from app.graph_release import _load_serving
from app.release_snapshot import readonly_store

assembly = assembly_fixture


def command_module():
    spec = importlib.util.spec_from_file_location("final_candidate_command_test", ROOT / "scripts/prepare_final_graph_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def input_for(assembly, tmp_path, *, actual_acceptance=False):
    packet = prepared(assembly, tmp_path / "assembly")
    reviewed = tmp_path / "reviewed"
    if actual_acceptance:
        accepted(assembly, packet, reviewed)
    else:
        # Fresh actual preparation and external TEST-ONLY signature, no retained
        # verdict. Candidate staging is the subject and fully verifies these
        # inputs/live sources. Avoid testing the old acceptance command again
        # as setup for every new negative candidate case.
        io = assembly["command"].io
        with readonly_store(assembly["settings"]) as store:
            files, _ = io.read_packet(packet, store, schema_version=assembly["command"].PACKET_SCHEMA)
            attestation = tmp_path / "TEST-ONLY-final-review.json"
            signed(attestation, io.parse_json(files["public-review-body.json"]), assembly["key"], io)
            files["review-attestation.json"] = attestation.read_bytes()
            io.atomic_packet(reviewed, io.sealed_files(files, store, schema_version=assembly["command"].PACKET_SCHEMA))
    _, key = key_pair(tmp_path, "independent-final-permission")
    settings = assembly["settings"]
    settings.graph_final_grant_trusted_key = str(key)
    return {"assembly": assembly, "packet": reviewed, "settings": settings, "public": key,
            "command": command_module(), "root": tmp_path}


@pytest.fixture
def candidate_input(assembly, tmp_path):
    return input_for(assembly, tmp_path)


@pytest.fixture
def fresh_candidate_input(assembly, tmp_path):
    return input_for(assembly, tmp_path, actual_acceptance=True)


def proposed(value, output, **changes):
    now = datetime.now(timezone.utc)
    args = {"packet": value["packet"], "reviewer": "TEST-ONLY INDEPENDENT FINAL PERMISSION REVIEWER",
            "approved_at": now.isoformat(), "expires_at": (now + timedelta(minutes=30)).isoformat(), "output": output}
    return value["command"].prepare(value["settings"], **{**args, **changes})


def test_candidate_is_exact_reviewed_public_payload_with_encrypted_unsigned_permission(fresh_candidate_input, tmp_path):
    value = fresh_candidate_input
    output = tmp_path / "final-candidate"
    result = proposed(value, output)
    assert result["final_permission_signing_inputs_created"] and result["signature_created"] is False
    assert result["publication_performed"] is False and result["national_release_serving_authorized"] is False
    assert value["command"].validate(value["settings"], output)["current_final_serving_candidate"]
    with readonly_store(value["settings"]) as reader:
        files, _ = value["command"].io.read_packet(output / "permission", reader)
        body = reader.decode(SimpleNamespace(payload=files["request.fernet"].decode()))
    assert body["schema_version"] == value["command"].SCHEMA and body["signed"] is False
    assert len(body["component_release_ids"]) == 2 and body["audience"] == "deployment_shared"
    assert body["release_id"] == result["release_id"] and body["national_release_serving_authorized"] is False
    flat = b"\n".join(path.read_bytes() for path in output.rglob("*") if path.is_file())
    for private in (value["assembly"]["current"]["operator_id"].encode(), value["assembly"]["current"]["audience"],
                    b"source_permissions", b"dependencies_sha256", b"TEST-ONLY INDEPENDENT FINAL PERMISSION REVIEWER"):
        assert private not in flat
    with pytest.raises(ValueError):
        _load_serving().install(Path(value["settings"].graph_release_dir), output / "prepared",
                               Path(value["settings"].graph_final_review_trusted_key))
    assert not (Path(value["settings"].graph_release_dir) / "active.json").exists()
    with pytest.raises(ValueError):
        proposed(value, output)
    assert output.exists()


@pytest.mark.parametrize("change", ["overlong", "expired", "future", "same-reviewer", "shared-key"])
def test_candidate_permission_cannot_extend_a_component_or_claim_shared_trust(candidate_input, tmp_path, change):
    value, changes = candidate_input, {}
    now = datetime.now(timezone.utc)
    if change == "overlong":
        changes["expires_at"] = (now + timedelta(days=1)).isoformat()
    elif change == "expired":
        changes["expires_at"] = (now - timedelta(seconds=1)).isoformat()
    elif change == "future":
        changes["approved_at"] = (now + timedelta(minutes=1)).isoformat()
    elif change == "same-reviewer":
        changes["reviewer"] = "TEST-ONLY INDEPENDENT FINAL REVIEWER"
    else:
        value["settings"].graph_final_grant_trusted_key = value["settings"].graph_final_review_trusted_key
    with pytest.raises(ValueError):
        proposed(value, tmp_path / "withheld", **changes)
    assert not (tmp_path / "withheld").exists()


@pytest.mark.parametrize("change", ["public-bytes", "extra-file", "private-body", "epoch", "b-rights"])
def test_current_whole_candidate_withheld_after_any_dependency_change(candidate_input, tmp_path, change):
    value, output = candidate_input, tmp_path / "candidate"
    proposed(value, output)
    if change == "public-bytes":
        path = output / "prepared/jurisprudence.nq"
        path.write_bytes(path.read_bytes() + b"# changed\n")
    elif change == "extra-file":
        (output / "unknown-file").write_bytes(b"unknown")
    elif change == "epoch":
        (value["settings"].data_dir / "publication-epoch").write_text(str(uuid4()) + "\n")
    elif change == "b-rights":
        item = value["assembly"]["current"]["evidence"][0][-1]
        assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    else:
        with readonly_store(value["settings"]) as reader:
            files, _ = value["command"].io.read_packet(output / "permission", reader)
            body = reader.decode(SimpleNamespace(payload=files["request.fernet"].decode()))
            body["national_release_serving_authorized"] = True
            files["request.fernet"] = reader.seal_preparation(body)
            sealed = value["command"].io.sealed_files(files, reader)
        for name, raw in sealed.items():
            (output / "permission" / name).write_bytes(raw)
    with pytest.raises(ValueError):
        value["command"].validate(value["settings"], output)
    assert output.exists()


def test_late_epoch_change_discards_new_candidate_and_safe_cli(candidate_input, tmp_path, monkeypatch, capsys):
    value = candidate_input
    original = value["command"].io.atomic_packet
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        (value["settings"].data_dir / "publication-epoch").write_text(str(uuid4()) + "\n")
        return result
    monkeypatch.setattr(value["command"].io, "atomic_packet", changed)
    with pytest.raises(ValueError):
        proposed(value, tmp_path / "withheld")
    assert not (tmp_path / "withheld").exists()
    from app import config
    monkeypatch.setattr(config, "load_settings", lambda: value["settings"])
    assert value["command"].main(["validate", "/absent-private-candidate"]) == 2
    output = capsys.readouterr()
    assert value["assembly"]["current"]["operator_id"] not in output.err


@pytest.mark.parametrize("change", ["attestation-bytes", "review-clock"])
def test_reviewed_packet_exit_still_withholds_changed_signature_bytes_or_time(candidate_input, monkeypatch, change):
    value = candidate_input
    command = value["assembly"]["command"]
    with pytest.raises(ValueError):
        with command.current_packet(value["settings"], value["packet"], reviewed=True):
            if change == "attestation-bytes":
                (value["packet"] / "review-attestation.json").write_bytes(b"substituted after full verification")
            else:
                class Earlier(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return datetime.now(tz) - timedelta(minutes=1)
                monkeypatch.setattr(command, "datetime", Earlier)
