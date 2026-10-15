"""Unchanged whole-release transition case, isolated for bounded CI scheduling."""
from datetime import datetime, timezone

import pytest
from test_final_graph_candidate import input_for, proposed
from test_final_release_authorization import accepted, activate, assembly, staged
from test_release_authorization import signed

from app import final_release_authorization as final
from app.graph_release import RuntimeGraphRelease
from app.release_authorization import AuthorizationError
from app.release_snapshot import readonly_store

__all__ = ["assembly", "staged"]


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

