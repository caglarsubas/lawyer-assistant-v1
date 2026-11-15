"""Check the measured CI transfer against frozen deployment identities."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_ci_authenticated_headroom as headroom


@pytest.fixture(scope="module")
def inventory():
    tests = headroom.driver.collect()
    manifest = json.loads(headroom.driver.MANIFEST.read_text())
    return tests, manifest


def test_active_plan_transfers_cases_once_and_preserves_every_identity(inventory):
    tests, manifest = inventory
    before = {
        shard: {test.id() for test in headroom.retained.plan(tests, manifest, shard)}
        for shard in range(1, 11)
    }
    active = {
        shard: [test.id() for test in headroom.plan(tests, manifest, shard)]
        for shard in range(1, 11)
    }
    assert sorted(ident for identities in active.values() for ident in identities) == manifest["test_ids"]

    profile = json.loads(headroom.PROFILE.read_text())
    moved = set(profile["transferred_ids"])
    assert moved and moved <= before[3] and moved.isdisjoint(before[9])
    for shard, identities in active.items():
        expected = before[shard]
        if shard == 3:
            expected = expected - moved
        elif shard == 9:
            expected = expected | moved
        assert identities == sorted(expected)


@pytest.mark.parametrize("fault", [
    "manifest_digest", "source_digest", "duplicate_transfer", "missing_cost",
    "wrong_source", "invalid_cost", "over_budget_worker",
])
def test_unmeasured_or_inconsistent_transfer_fails_closed(inventory, fault):
    tests, manifest = inventory
    profile = json.loads(headroom.PROFILE.read_text())
    moved = profile["transferred_ids"][0]
    if fault == "manifest_digest":
        profile["manifest_sha256"] = "0" * 64
    elif fault == "source_digest":
        source = next(iter(profile["source_sha256"]))
        profile["source_sha256"][source] = "0" * 64
    elif fault == "duplicate_transfer":
        profile["transferred_ids"].append(moved)
    elif fault == "missing_cost":
        del profile["case_ms"][moved]
    elif fault == "wrong_source":
        profile["transferred_ids"][0] = headroom.retained.plan(tests, manifest, 9)[0].id()
    elif fault == "invalid_cost":
        profile["case_ms"][moved] = True
    else:
        profile["case_ms"][moved] = 120_000

    with pytest.raises(ValueError):
        headroom.allocations(tests, manifest, profile)
