"""Closed scheduling guards; no legal or provider qualification credit."""

import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import ci_authority_trials as placement  # noqa: E402


def test_complete_inventory_is_disjoint_and_preserves_other_tests():
    contract = placement.load_contract()
    other = "tests/test_unrelated.py::test_kept"
    selected = []
    for lane in placement.COUNTS:
        collected = contract.ids if lane == "capacity" else contract.lanes[lane]
        ids = placement.select(contract, lane, [other, *collected])
        assert other in ids
        selected.extend(x for x in ids if x != other)
    assert sorted(selected) == list(contract.ids)
    lane = next(k for k, v in contract.lanes.items() if placement.PRIORITY[0] in v)
    assert placement.select(contract, lane, [other, *contract.ids])[0] == placement.PRIORITY[0]


@pytest.mark.parametrize("change", ["source", "missing", "duplicate", "overlap", "unknown_lane", "extra_key"])
def test_changed_source_or_inventory_fails_closed(tmp_path, change):
    value = json.loads(placement.MANIFEST.read_text())
    source = tmp_path / "source.py"
    source.write_bytes(placement.SOURCE.read_bytes())
    if change == "source":
        source.write_bytes(source.read_bytes() + b"\n")
    elif change == "missing":
        value["test_ids"].pop()
    elif change == "duplicate":
        value["test_ids"][0] = value["test_ids"][1]
    elif change == "overlap":
        value["lanes"]["capacity"][0] = value["lanes"]["capacity"][1]
        value["lanes"]["capacity"].sort()
    elif change == "unknown_lane":
        value["lanes"]["unknown"] = value["lanes"].pop("capacity")
    else:
        value["waive"] = True
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        placement.load_contract(manifest, source)


@pytest.mark.parametrize("change", ["missing", "duplicate", "renamed"])
def test_incomplete_actual_collection_is_rejected(change):
    contract = placement.load_contract()
    for lane in placement.COUNTS:
        ids = list(contract.ids if lane == "capacity" else contract.lanes[lane])
        if change == "missing":
            ids.pop()
        elif change == "duplicate":
            ids.append(ids[0])
        else:
            ids[0] += "_renamed"
        with pytest.raises(ValueError):
            placement.select(contract, lane, ids)
    with pytest.raises(ValueError):
        placement.select(contract, "core", list(contract.ids))


@pytest.mark.parametrize("change", ["missing", "duplicate", "skip", "xfail", "exact"])
def test_execution_receipt_requires_each_selected_pass_once(change):
    contract = placement.load_contract()
    for lane in placement.COUNTS:
        plugin = placement.Partition(contract, lane)
        ids = list(contract.lanes[lane])
        if change == "missing":
            ids.pop()
        elif change == "duplicate":
            ids.append(ids[0])
        for index, nodeid in enumerate(ids):
            plugin.pytest_runtest_logreport(SimpleNamespace(
                when="call", passed=not (change == "skip" and index == 0), nodeid=nodeid,
                wasxfail=change == "xfail" and index == 0))
        session = SimpleNamespace(config=SimpleNamespace(getoption=lambda _: False), exitstatus=0)
        plugin.pytest_sessionfinish(session, 0)
        assert plugin.valid is (change == "exact")
        assert session.exitstatus == (0 if change == "exact" else pytest.ExitCode.TESTS_FAILED)
        receipts = []
        plugin.pytest_terminal_summary(SimpleNamespace(config=SimpleNamespace(), write_line=receipts.append), 0)
        if change == "exact":
            record = json.loads(receipts[0])
            assert record["complete_count"] == placement.COUNTS[lane]
            assert record["selected_ids_sha256"] == sorted(hashlib.sha256(n.encode()).hexdigest() for n in ids)
            assert "selected_ids" not in record
        else:
            assert not receipts


def test_workflow_routes_every_lane_once_and_keeps_fixed_resources():
    workflow = (placement.ROOT / ".github/workflows/ci.yml").read_text()
    blocks = dict(re.findall(r"^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)",
                             workflow.split("\njobs:\n", 1)[1], re.M | re.S))
    owners = {"capacity": "backend-capacity", "core": "backend-and-contracts"}
    assert len(blocks) == 13
    assert sum(int(re.search(r"    timeout-minutes: (\d+)", b)[1]) for b in blocks.values()) == 73
    for lane, owner in owners.items():
        option = "-p scripts.ci_authority_trials --authority-trial-lane=" + lane
        assert workflow.count(option) == 1 and option in blocks[owner]
        line = next(x for x in blocks[owner].splitlines() if option in x)
        assert "-n 2" in line
        if lane == "capacity":
            assert '"${authority_trial_tests[@]}"' in line
        else:
            assert 'pytest backend/tests "${ignore_args[@]}"' in line
    backend = blocks["backend-and-contracts"]
    assert '"${authority_trial_tests[@]}"' in backend.split("for path in ", 1)[1]
    assert 'if [[ "$path" != "${preview_tests[0]}" && "$path" != "${authority_trial_tests[2]}" ]]; then' in backend
    group = re.search(r"  CI_AUTHORITY_TRIAL_TESTS: >-\n((?:    [^\n]+\n)+)", workflow)[1].split()
    assert group == ["backend/tests/test_authority_trials.py", "backend/tests/test_graph.py",
                     "backend/tests/test_operator_recovery_inputs.py"]
    assert workflow.count("backend/tests/test_graph.py") == 1
    assert workflow.count("backend/tests/test_authority_trials.py") == 1


@pytest.mark.parametrize("fault", ["none", "new_job_29_seconds", "missing_job", "wrong_head"])
def test_explicit_thirteen_job_policy_keeps_the_original_core_and_floors(fault):
    from datetime import datetime, timedelta, timezone

    from scripts import run_ci_reserve_guard as old
    from scripts import run_ci_reserve_guard_v2 as current

    core = current.load_policy()
    assert len(old.CAPS) == 12 and sum(old.CAPS.values()) == 4200
    assert core.CAPS == {**old.CAPS, "backend-capacity": 180}
    assert core.STEP_CAPS == old.STEP_CAPS and core.FLOOR == old.FLOOR == 30
    assert core.policy_sha256() != old.policy_sha256()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    jobs = [{"name": k, "head_sha": "a" * 40, "run_id": 123, "status": "completed",
             "conclusion": "success", "started_at": start.isoformat(),
             "completed_at": (start + timedelta(seconds=cap - 30)).isoformat()}
            for k, cap in core.CAPS.items()]
    row = jobs[-1]
    if fault == "new_job_29_seconds":
        row["completed_at"] = (start + timedelta(seconds=151)).isoformat()
    elif fault == "missing_job":
        jobs.pop()
    elif fault == "wrong_head":
        row["head_sha"] = "b" * 40
    if fault == "none":
        assert core.inspect({"jobs": jobs}, 123, "a" * 40, final=True) == {
            "completed_siblings": 12, "minimum_reserve": 30}
    else:
        with pytest.raises(core.Rejected):
            core.inspect({"jobs": jobs}, 123, "a" * 40, final=True)
