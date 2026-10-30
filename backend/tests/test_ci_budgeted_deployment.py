"""The CI overlay cannot drop identities or borrow an unmeasured destination."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_ci_budgeted_deployment as overlay  # noqa: E402


@pytest.fixture(scope="module")
def inventory():
    return overlay.driver.collect(), json.loads(overlay.driver.MANIFEST.read_text())


def test_closed_overlay_preserves_every_original_identity_once(inventory):
    tests, manifest = inventory
    lanes = [[test.id() for test in overlay.plan(tests, manifest, n)] for n in range(1, 11)]
    assert list(map(len, lanes)) == [389, 425, 84, 23, 17, 26, 19, 12, 10, 13]
    assert sorted(ident for lane in lanes for ident in lane) == manifest["test_ids"]
    for lane in (2, 4, 5, 6, 7, 8, 9):
        assert lanes[lane - 1] == [test.id() for test in overlay.ORIGINAL_PLAN(tests, manifest, lane)]


@pytest.mark.parametrize("change", ["manifest", "driver", "counts", "budget", "unknown", "missing", "duplicate", "destination", "unmeasured", "zero", "source_lane"])
def test_changed_or_incomplete_overlay_fails_closed(inventory, change):
    tests, manifest = inventory
    value = copy.deepcopy(json.loads(overlay.PROFILE.read_text()))
    if change in ("manifest", "driver"):
        value[change + "_sha256"] = "0" * 64
    elif change == "counts":
        value["original_counts"]["3"] = 89
    elif change == "budget":
        value["worker_increment_budget_ms"]["1"] += 1
    elif change == "unknown":
        value["unreviewed"] = True
    elif change == "missing":
        value["assignments"].pop()
    elif change == "duplicate":
        value["assignments"][1] = copy.deepcopy(value["assignments"][0])
    elif change == "destination":
        value["assignments"][0]["shard"] = 5
    elif change == "unmeasured":
        value["assignments"][0]["observed_case_ms"] = 10001
    elif change == "zero":
        value["assignments"][0]["observed_case_ms"] = 0
    else:
        value["assignments"][0]["test_id"] = overlay.ORIGINAL_PLAN(tests, manifest, 1)[0].id()
    with pytest.raises(ValueError):
        overlay.assignments(tests, manifest, value)


def test_parallel_children_use_overlay_and_unchanged_receipt_verifier(monkeypatch):
    """Exercise the entry hook without launching an extra pair of workers."""
    def original_main():
        assert overlay.driver.plan is overlay.plan
        assert Path(overlay.driver.__file__).resolve() == Path(overlay.__file__).resolve()
        assert overlay.driver.merge_workers.__module__ == "run_ci_deployment_shard"
        return 37
    monkeypatch.setattr(overlay.driver, "main", original_main)
    monkeypatch.setattr(overlay.driver, "plan", overlay.ORIGINAL_PLAN)
    monkeypatch.setattr(overlay.driver, "__file__", str(overlay.ORIGINAL_DRIVER))
    assert overlay.main() == 37
