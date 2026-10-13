"""Invented corpus, actual serving transitions, TEST-ONLY external signatures."""
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_declared_graph_assembly import assembly as assembly_fixture
from test_final_graph_candidate import input_for, proposed
from test_release_authorization import signed

from app import final_release_authorization as final
from app.graph_release import RuntimeGraphRelease, _load_serving
from app.release_authorization import AuthorizationError, ReleaseAuthorization
from app.release_preparation import canonical
from app.release_snapshot import readonly_store

assembly = assembly_fixture


def stage_for(assembly, tmp_path, *, real_staging=False):
    value = input_for(assembly, tmp_path)
    # input_for configured an independent public key; keep the matching private
    # TEST key only in this case. Production never creates keys or signatures.
    from test_declared_graph_assembly import key_pair
    value["key"], value["public"] = key_pair(tmp_path, "whole-release-permission")
    value["settings"].graph_final_grant_trusted_key = str(value["public"])
    value["settings"].graph_serving_review_role = "final"
    candidate = tmp_path / "candidate"
    if real_staging:
        proposed(value, candidate)
    else:
        form_candidate(value, candidate)
    value["candidate"] = candidate
    io = final._packet_tools()
    with readonly_store(value["settings"]) as reader:
        files, _ = io.read_packet(candidate / "permission", reader)
        request = reader.decode(SimpleNamespace(payload=files["request.fernet"].decode()))
    value["body"] = final.approval_body(request)
    value["authorization"] = tmp_path / "TEST-ONLY-external-whole-release.json"
    signed(value["authorization"], value["body"], value["key"], io)
    return value


def form_candidate(value, candidate):
    """Fresh actual assembly/public checks, no acceptance or rights verdict.

    The candidate CLI has its own positive/negative subject tests. Form its
    encrypted inputs here without running that older CLI's duplicate warmups;
    whole-release acceptance is the subject and revalidates every original.
    """
    from datetime import timedelta
    from tempfile import TemporaryDirectory

    from app.declared_graph_assembly import _load
    settings, command = value["settings"], value["command"]
    io, serving = command.io, _load_serving()
    with readonly_store(settings) as reader:
        files, packet_hash = io.read_packet(value["packet"], reader, schema_version="legal-declared-graph-assembly-v1")
        loaded = _load(settings, reader, value["assembly"]["declaration"], final.ROOT / "ontology")
        with TemporaryDirectory(prefix="TEST-ONLY-final-payload-") as scratch:
            root = Path(scratch)
            for name, raw in files.items():
                if name.startswith(("inputs/", "evidence/")) or name == "review-attestation.json":
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
            serving._release.create_bundle(final.ROOT / "ontology",
                {family: root / "inputs" / (family + ".ttl") for family in ("structure", "jurisprudence")},
                root / "evidence", root / "bundle", root / "review-attestation.json", value["assembly"]["public"])
            info = serving.prepare(root / "bundle", value["assembly"]["public"], root / "prepared")
            now = datetime.now(timezone.utc)
            request = command.request_body(settings, files, loaded, info, packet_hash,
                "TEST-ONLY INDEPENDENT FINAL PERMISSION REVIEWER", now.isoformat(),
                value.get("permission_expires_at", (now + timedelta(minutes=30)).isoformat()))
            private = {"binding.fernet": reader.seal_preparation({"reviewed_packet": str(value["packet"]),
                       "reviewed_packet_sha256": packet_hash}), "request.fernet": reader.seal_preparation(request),
                       "NOTICE.json": command.NOTICE}
            outputs = {"prepared/" + name: io.read_file(root / "prepared" / name, io.MAX_FILE)
                       for name in serving._files(root / "prepared")}
            outputs.update({"permission/" + name: raw for name, raw in io.sealed_files(private, reader).items()})
            outputs["NOTICE.json"] = command.NOTICE
            io.atomic_packet(candidate, outputs, max_depth=5)


@pytest.fixture
def staged(assembly, tmp_path):
    return stage_for(assembly, tmp_path)


def accepted(value):
    return final.accept(value["settings"], candidate=value["candidate"], authorization=value["authorization"])


def serving_inputs(value):
    serving = _load_serving()
    root = value["assembly"]["root"] / "published"
    key = value["assembly"]["public"]
    info = serving.validate_prepared(value["candidate"] / "prepared", key)
    return serving, root, key, info, final.FinalReleaseAuthorization(value["settings"]).guard


def activate(value):
    serving, root, key, info, guard = serving_inputs(value)
    serving.install(root, value["candidate"] / "prepared", key, authorization_guard=guard)
    pointer = serving.activate(root, info["release_id"], key, expected_current=None, expected_sequence=0, authorization_guard=guard)
    return serving, root, key, info, guard, pointer


def test_whole_external_approval_install_activation_and_current_runtime_read(assembly, tmp_path):
    value = stage_for(assembly, tmp_path, real_staging=True)
    receipt = accepted(value)
    assert receipt["whole_release_authorization_accepted"] and not receipt["publication_performed"]
    serving, root, key, info, guard, pointer = activate(value)
    assert pointer["release_id"] == info["release_id"] and pointer["sequence"] == 1
    runtime = RuntimeGraphRelease(root, key, guard)
    assert runtime.status()["status"] == "verified"
    with runtime.current_guard() as actual:
        assert actual["release_id"] == receipt["release_id"]
    # Read does not accept the staging candidate as an installed active root.
    with pytest.raises(AuthorizationError), guard(info, "read"):
        pytest.fail("Candidate is not a runtime release")
    # The central namespace dispatcher must use the final guard exactly once,
    # without trying the structurally signed component policy after denial.
    with readonly_store(value["settings"]) as reader:
        from app.public_sources import PublicSourceStore
        dispatcher = ReleaseAuthorization(reader, PublicSourceStore(value["settings"].public_source_dir),
            value["settings"].data_dir / "release-authorizations", Path(value["settings"].graph_trusted_review_key),
            final.ROOT / "ontology", value["settings"].data_dir / "publication-epoch", settings=value["settings"])
        with dispatcher.guard(serving.load_active(root, key), "read") as result:
            assert result["scope"] == "complete_declared_release"
    directory = value["settings"].data_dir / "release-authorizations" / receipt["release_id"]
    assert all(path.stat().st_mode & 0o077 == 0 for path in (directory, *directory.rglob("*")))
    flat = b"\n".join(path.read_bytes() for path in directory.rglob("*") if path.is_file())
    assert value["body"]["reviewer"].encode() not in flat
    with pytest.raises(ValueError):
        accepted(value)
    assert serving.read_pointer(root) == pointer


def test_external_grant_requires_exact_whole_reviewed_request(staged):
    from cryptography.exceptions import InvalidSignature
    value, io = staged, final._packet_tools()
    original = value["body"]
    # Each bad envelope is independently signed and exercised. Sharing the
    # unchanged valid candidate avoids rebuilding older staging subjects five
    # times; final success proves denials were not caused by broken setup.
    for change in ("wrong-key", "partial-members", "extra-field", "unsigned-request", "coerced-flag"):
        body = {**original, "component_release_ids": list(original["component_release_ids"])}
        signing_key = value["assembly"]["key"] if change == "wrong-key" else value["key"]
        if change == "partial-members":
            body["component_release_ids"].pop()
        elif change == "extra-field":
            body["extra"] = "invalid"
        elif change == "coerced-flag":
            body["signed"] = 1
        elif change == "unsigned-request":
            body.update(schema_version=value["command"].SCHEMA, decision="request", signed=False,
                        national_release_serving_authorized=False)
        signed(value["authorization"], body, signing_key, io)
        with pytest.raises((ValueError, InvalidSignature)):
            accepted(value)
        assert not (value["settings"].data_dir / "release-authorizations" / original["release_id"]).exists(), change
    signed(value["authorization"], original, value["key"], io)
    assert accepted(value)["whole_release_authorization_accepted"]


def test_activation_and_rollback_use_monotonic_pointer_and_current_target_grant(staged, tmp_path):
    value = staged
    accepted(value)
    # A second independently attested final bundle is staged while the original
    # preparation base is still current. The same sources remain unmodified.
    other_root = tmp_path / "second"
    other_root.mkdir()
    second = input_for(value["assembly"], other_root)
    second["settings"].graph_final_grant_trusted_key = str(value["public"])
    second["key"], second["public"] = value["key"], value["public"]
    second["candidate"] = other_root / "candidate"
    proposed(second, second["candidate"], approved_at=datetime.now(timezone.utc).isoformat())
    io = final._packet_tools()
    with readonly_store(value["settings"]) as reader:
        _, _, _, _, _, request = final.candidate_inputs(value["settings"], reader, second["candidate"])
    second["authorization"] = other_root / "TEST-ONLY-external-grant.json"
    signed(second["authorization"], final.approval_body(request), value["key"], io)
    accepted(second)
    serving, root, key, first_info, guard, first = activate(value)
    second_info = serving.validate_prepared(second["candidate"] / "prepared", key)
    assert first_info["release_id"] != second_info["release_id"]
    serving.install(root, second["candidate"] / "prepared", key, authorization_guard=guard)
    with pytest.raises(ValueError):
        serving.activate(root, second_info["release_id"], key, expected_current=None, expected_sequence=0, authorization_guard=guard)
    current = serving.activate(root, second_info["release_id"], key, expected_current=first["release_id"], expected_sequence=1, authorization_guard=guard)
    assert current["previous_release_id"] == first["release_id"] and current["sequence"] == 2
    assert RuntimeGraphRelease(root, key, guard).status()["status"] == "verified"
    previous = serving.rollback(root, key, expected_current=current["release_id"], expected_sequence=2, authorization_guard=guard)
    assert previous["release_id"] == first["release_id"] and previous["sequence"] == 3
    assert RuntimeGraphRelease(root, key, guard).status()["status"] == "verified"
    # Withdrawal of the rollback target must not restore revoked content.
    target = value["settings"].data_dir / "release-authorizations" / second_info["release_id"] / "grant.fernet"
    target.write_bytes(b"changed")
    with pytest.raises(AuthorizationError):
        serving.rollback(root, key, expected_current=previous["release_id"], expected_sequence=3, authorization_guard=guard)
    assert serving.read_pointer(root) == previous


@pytest.mark.parametrize("action", ["install", "activate"])
def test_late_grant_change_has_unknown_transition_outcome_and_no_blind_replay(staged, monkeypatch, action):
    value = staged
    accepted(value)
    serving, root, key, info, guard = serving_inputs(value)
    original = serving._sync_directory
    changed = False
    def change(path):
        nonlocal changed
        original(path)
        if path == (root / "releases" if action == "install" else root) and not changed:
            changed = True
            (value["settings"].data_dir / "publication-epoch").write_text(str(uuid4()) + "\n")
    if action == "activate":
        serving.install(root, value["candidate"] / "prepared", key, authorization_guard=guard)
    monkeypatch.setattr(serving, "_sync_directory", change)
    with pytest.raises(serving.TransitionOutcomeUnknown):
        if action == "install":
            serving.install(root, value["candidate"] / "prepared", key, authorization_guard=guard)
        else:
            serving.activate(root, info["release_id"], key, expected_current=None, expected_sequence=0, authorization_guard=guard)
    assert changed and (root / "releases" / info["release_id"]).exists()
    assert (serving.read_pointer(root) is not None) == (action == "activate")
    with pytest.raises(AuthorizationError):
        serving.install(root, value["candidate"] / "prepared", key, authorization_guard=guard)


def test_guard_rejects_unheld_or_fabricated_transition(staged):
    value = staged
    accepted(value)
    _, root, _, info, guard = serving_inputs(value)
    before, after = None, {"format_version": 1, "release_id": info["release_id"], "serving_sha256": info["serving_sha256"],
                            "previous_release_id": None, "sequence": 1}
    descriptor = os.open(root / "publication.lock", os.O_RDONLY)
    try:
        with pytest.raises(AuthorizationError), guard({**info, "_transition": {"before": before, "after": after,
                "action": "activate", "descriptor": descriptor}}, "activate"):
            pytest.fail("A mere open descriptor is not a held exclusive lock")
    finally:
        os.close(descriptor)


def test_original_retained_structural_base_remains_required_after_activation(assembly, tmp_path):
    from app.public_sources import PublicSourceStore
    serving, settings = _load_serving(), assembly["settings"]
    root, component_key = Path(settings.graph_release_dir), Path(settings.graph_trusted_review_key)
    declaration = assembly["declaration"]
    with readonly_store(settings) as reader:
        gate = ReleaseAuthorization(reader, PublicSourceStore(settings.public_source_dir),
            settings.data_dir / "release-authorizations", component_key, final.ROOT / "ontology",
            settings.data_dir / "publication-epoch")
        serving.install(root, Path(declaration.structure.prepared), component_key, authorization_guard=gate.guard)
        pointer = serving.activate(root, declaration.structure.release_id, component_key, expected_current=None,
                                   expected_sequence=0, authorization_guard=gate.guard)
    data = declaration.model_dump()
    data["expected_base"] = pointer
    from app.declared_graph_assembly import Declaration
    assembly["declaration"] = Declaration.model_validate(data)
    assembly["selection"].write_bytes(canonical(data))
    value = stage_for(assembly, tmp_path)
    accepted(value)
    serving, root, key, info, guard = serving_inputs(value)
    serving.install(root, value["candidate"] / "prepared", key, authorization_guard=guard)
    selected = serving.activate(root, info["release_id"], key, expected_current=pointer["release_id"],
                                expected_sequence=pointer["sequence"], authorization_guard=guard)
    runtime = RuntimeGraphRelease(root, key, guard)
    assert runtime.status()["status"] == "verified" and selected["sequence"] == 2
    base_file = root / "releases" / pointer["release_id"] / "structure.nq"
    base_file.chmod(0o600)
    base_file.write_bytes(base_file.read_bytes() + b"# changed retained base\n")
    assert runtime.status()["status"] == "unavailable"
    assert serving.read_pointer(root) == selected


def test_acceptance_interruption_discards_only_owned_new_permission(staged, monkeypatch):
    value, tools = staged, final._packet_tools()
    original = tools.atomic_packet
    # Patch the exact helper returned to acceptance, while preserving all other
    # original-source readers. No subject or signature verdict is mocked.
    def interrupted(*args, **kwargs):
        result = original(*args, **kwargs)
        (value["settings"].data_dir / "publication-epoch").write_text(str(uuid4()) + "\n")
        return result
    monkeypatch.setattr(tools, "atomic_packet", interrupted)
    monkeypatch.setattr(final, "_packet_tools", lambda: tools)
    with pytest.raises(ValueError):
        accepted(value)
    assert not (value["settings"].data_dir / "release-authorizations" / value["body"]["release_id"]).exists()
    assert value["candidate"].exists() and value["packet"].exists()


@pytest.mark.parametrize("change", ["candidate-bytes", "expiry", "serving-role"])
def test_mid_read_changes_cannot_reuse_an_entry_permission_verdict(staged, monkeypatch, change):
    value = staged
    accepted(value)
    serving, root, key, _, _, _ = activate(value)
    info = serving.load_active(root, key)
    command = final.commands()
    monkeypatch.setattr(final, "commands", lambda: command)
    with pytest.raises(AuthorizationError), final.FinalReleaseAuthorization(value["settings"]).guard(info, "read"):
        if change == "candidate-bytes":
            path = value["candidate"] / "prepared/jurisprudence.nq"
            path.chmod(0o600)
            path.write_bytes(path.read_bytes() + b"# changed during bounded use\n")
        elif change == "serving-role":
            value["settings"].graph_serving_review_role = "component"
        else:
            from datetime import timedelta
            class FutureClock:
                @staticmethod
                def now(zone):
                    return datetime.now(zone) + timedelta(days=2)
            monkeypatch.setattr(command, "datetime", FutureClock)
