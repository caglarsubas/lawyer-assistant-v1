"""Closed source-bound coverage, including unrelated tests in the same job."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import ci_materialization_capacity as placement  # noqa: E402


def test_complete_materialization_inventory_executes_once_across_existing_pairs():
    contract = placement.load_contract()
    observed = []
    for lane in placement.COUNTS:
        selected = placement.select(contract, lane, ["tests/test_unrelated.py::test_preserved", *contract.ids])
        assert selected[0] == "tests/test_unrelated.py::test_preserved"
        observed += selected[1:]
    assert sorted(observed) == list(contract.ids) and len(observed) == len(set(observed)) == 58


@pytest.mark.parametrize("fault", ["missing", "overlap", "source", "unknown_lane"])
def test_materialization_partition_corruption_fails_closed(tmp_path, fault):
    value = json.loads(placement.MANIFEST.read_text())
    if fault == "missing":
        value["test_ids"].pop()
    elif fault == "overlap":
        value["lanes"]["review"][0] = value["lanes"]["final"][0]
        value["lanes"]["review"].sort()
    elif fault == "source":
        value["source_sha256"] = "0" * 64
    else:
        value["lanes"]["unapproved"] = value["lanes"].pop("final")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        placement.load_contract(path)
