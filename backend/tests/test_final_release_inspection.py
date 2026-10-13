"""Invented release observation; expected effects never authorize replay/repair."""
import hashlib
from pathlib import Path

import pytest
from test_declared_graph_assembly import assembly as assembly_fixture
from test_final_release_authorization import accepted, serving_inputs, stage_for
from test_source_reviews import assess

from app.config import Settings
from app.final_release_inspection import TransitionExpectation, inspect_transition, observation_locks
from app.release_preparation import canonical

assembly = assembly_fixture


def request(info, action="install", before=None):
    return TransitionExpectation.model_validate({"schema_version": "legal-final-transition-expectation-v1",
        "action": action, "release_id": info["release_id"], "serving_sha256": info["serving_sha256"], "before": before})


def files(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def observed(value, expectation):
    root = Path(value["settings"].graph_release_dir)
    before = files(root)
    result = inspect_transition(value["settings"], expectation)
    assert files(root) == before
    assert all(result[key] is False for key in ("command_commit_proven", "retry_authorized", "repair_performed",
                                               "activation_performed", "legal_qualification_granted"))
    return result


def test_observation_separates_effect_permission_and_later_state_without_writes(assembly, tmp_path):
    value = stage_for(assembly, tmp_path)
    serving, root, key, info, guard = serving_inputs(value)
    expected_install = request(info)
    absent = observed(value, expected_install)
    assert absent["observed_effect"] == "expected_effect_absent_at_observation"
    assert absent["public_inventory"] == "absent" and absent["current_permission"] == "not_checked"
    accepted(value)
    serving.install(root, value["candidate"] / "prepared", key, authorization_guard=guard)
    installed = observed(value, expected_install)
    assert installed["observed_effect"] == "expected_effect_present" and installed["current_permission"] == "verified"
    assert installed["active_pointer"] is None
    inactive = observed(value, request(info, "activate"))
    assert inactive["pointer_relation"] == "before" and inactive["observed_effect"] == "expected_effect_absent_at_observation"
    pointer = serving.activate(root, info["release_id"], key, expected_current=None, expected_sequence=0, authorization_guard=guard)
    active = observed(value, request(info, "activate"))
    assert active["pointer_relation"] == "after" and active["observed_effect"] == "expected_effect_present"
    item = value["assembly"]["current"]["evidence"][0][-1]
    assert assess(item[1], item[4] + "/review", 6, "rights", decision="rejected").status_code == 200
    withdrawn = observed(value, request(info, "activate"))
    assert withdrawn["public_inventory"] == "verified" and withdrawn["current_permission"] == "withheld_or_unavailable"
    assert withdrawn["observed_effect"] == "expected_effect_present"
    assert serving.read_pointer(root) == pointer
    # A later pointer state is not proof of the original transition's outcome.
    (root / "active.json").chmod(0o600)
    (root / "active.json").write_bytes(canonical({**pointer, "sequence": 2}))
    later = observed(value, request(info, "activate"))
    assert later["pointer_relation"] == "other" and later["observed_effect"] == "conflict_or_later_state"
    # Corrupt installed bytes never become an 'absent' or retryable verdict.
    corrupted = root / "releases" / info["release_id"] / "structure.nq"
    corrupted.chmod(0o600)
    corrupted.write_bytes(corrupted.read_bytes() + b"# changed\n")
    state = files(root)
    with pytest.raises(ValueError):
        inspect_transition(value["settings"], request(info, "activate"))
    assert files(root) == state


@pytest.mark.parametrize("change", ["missing-before", "unknown-field", "short-id", "invalid-rollback", "same-target", "unknown-action"])
def test_observation_requires_a_complete_explicit_expectation(change):
    info = {"release_id": "a" * 64, "serving_sha256": "b" * 64}
    data = request(info).model_dump()
    if change == "missing-before":
        del data["before"]
    elif change == "unknown-field":
        data["allow_retry"] = True
    elif change == "short-id":
        data["release_id"] = "a" * 8
    elif change == "invalid-rollback":
        data["action"] = "rollback"
    elif change == "unknown-action":
        data["action"] = "read-and-repair"
    else:
        data.update(action="activate", before={"format_version": 1, "release_id": info["release_id"],
            "serving_sha256": info["serving_sha256"], "previous_release_id": None, "sequence": 1})
    with pytest.raises(ValueError):
        TransitionExpectation.model_validate(data)


def test_read_only_observer_never_initializes_locks_or_creates_release_roots(tmp_path):
    root = tmp_path / "uninitialized"
    root.mkdir()
    before = files(root)
    with pytest.raises(ValueError), observation_locks(root):
        pytest.fail("Observation cannot initialize publication")
    assert files(root) == before and not list(root.iterdir())
    settings = Settings(_env_file=None, graph_release_dir=str(root))
    with pytest.raises(ValueError):
        inspect_transition(settings, request({"release_id": "a" * 64, "serving_sha256": "b" * 64}))
    assert not list(root.iterdir())
