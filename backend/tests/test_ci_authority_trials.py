"""Closed scheduling guards; no legal or provider qualification credit."""

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
        ids = placement.select(contract, lane, [other, *contract.ids])
        assert ids[0] == other
        selected.extend(ids[1:])
    assert sorted(selected) == list(contract.ids)


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
        value["lanes"]["graph"][0] = value["lanes"]["final"][0]
        value["lanes"]["graph"].sort()
    elif change == "unknown_lane":
        value["lanes"]["unknown"] = value["lanes"].pop("graph")
    else:
        value["waive"] = True
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        placement.load_contract(manifest, source)


@pytest.mark.parametrize("change", ["missing", "duplicate", "renamed"])
def test_incomplete_actual_collection_is_rejected(change):
    contract = placement.load_contract()
    ids = list(contract.ids)
    if change == "missing":
        ids.pop()
    elif change == "duplicate":
        ids.append(ids[0])
    else:
        ids[0] += "_renamed"
    with pytest.raises(ValueError):
        placement.select(contract, "graph", ids)


@pytest.mark.parametrize("change", ["missing", "duplicate", "skip", "xfail", "exact"])
def test_execution_receipt_requires_each_selected_pass_once(change):
    contract = placement.load_contract()
    plugin = placement.Partition(contract, "graph")
    ids = list(contract.lanes["graph"])
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


def test_workflow_routes_every_lane_once_and_keeps_fixed_resources():
    workflow = (placement.ROOT / ".github/workflows/ci.yml").read_text()
    blocks = dict(re.findall(r"^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)",
                             workflow.split("\njobs:\n", 1)[1], re.M | re.S))
    owners = {"final": "final-release-authorization", "candidate": "graph-candidate-contracts",
              "publication": "source-publication-contracts", "graph": "graph-runtime-contracts"}
    assert len(blocks) == 12
    assert sum(int(re.search(r"    timeout-minutes: (\d+)", b)[1]) for b in blocks.values()) == 70
    for lane, owner in owners.items():
        option = "-p scripts.ci_authority_trials --authority-trial-lane=" + lane
        assert workflow.count(option) == 1 and option in blocks[owner]
        line = next(x for x in blocks[owner].splitlines() if option in x)
        assert '"${authority_trial_tests[@]}"' in line and "-n 2" in line
    backend = blocks["backend-and-contracts"]
    assert '"${authority_trial_tests[@]}"' in backend.split("for path in ", 1)[1]
    group = re.search(r"  CI_AUTHORITY_TRIAL_TESTS: >-\n((?:    [^\n]+\n)+)", workflow)[1].split()
    assert group == ["backend/tests/test_authority_trials.py"]
    assert workflow.count("backend/tests/test_authority_trials.py") == 1
