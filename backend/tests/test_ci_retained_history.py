"""A history allocation must preserve the frozen executor and every identity."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_ci_retained_deployment as overlay  # noqa: E402
import run_ci_retained_history_workers as history  # noqa: E402


@pytest.fixture(scope="module")
def inventory():
    return overlay.driver.collect(), json.loads(overlay.driver.MANIFEST.read_text())


def test_all_original_identities_execute_in_exactly_one_retained_lane(inventory):
    tests, manifest = inventory
    lanes = [[test.id() for test in overlay.plan(tests, manifest, n)] for n in range(1, 11)]
    assert list(map(len, lanes)) == [389, 419, 87, 23, 17, 26, 19, 12, 10, 16]
    assert sorted(ident for lane in lanes for ident in lane) == manifest["test_ids"]
    for n in (1, 4, 5, 6, 7, 8, 9):
        assert lanes[n - 1] == [test.id() for test in overlay.prior.plan(tests, manifest, n)]


@pytest.mark.parametrize("change", ["schema", "manifest", "source", "missing", "duplicate", "source_lane", "destination", "overbudget", "baseline", "history"])
def test_incomplete_or_unmeasured_overlay_cannot_execute(inventory, change):
    tests, manifest = inventory
    value = copy.deepcopy(json.loads(overlay.PROFILE.read_text()))
    if change == "schema":
        value["extra"] = True
    elif change == "manifest":
        value["manifest_sha256"] = "0" * 64
    elif change == "source":
        value["source_sha256"][overlay.SOURCES[0]] = "0" * 64
    elif change == "missing":
        value["assignments"].pop()
    elif change == "duplicate":
        value["assignments"][1] = copy.deepcopy(value["assignments"][0])
    elif change == "source_lane":
        value["assignments"][0]["test_id"] = overlay.prior.plan(tests, manifest, 3)[0].id()
    elif change == "destination":
        value["assignments"][0]["shard"] = 1
    elif change == "overbudget":
        value["assignments"][0]["observed_case_ms"] = 100000
    elif change == "baseline":
        value["baseline_case_ms"].pop(next(iter(value["baseline_case_ms"])))
    else:
        value["original_history_ids_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        overlay.assignments(tests, manifest, value)


def arguments():
    return [*history.EXECUTOR, "node", "node_modules/vitest/vitest.mjs", "run", "--pool=threads", "--maxWorkers=1",
            "--shard=2/2", "--reporter=default", "--reporter=json", "--outputFile=/tmp/invented.json", ":::",
            "bash", "scripts/run_ci_contracts.sh", "backend/.venv/bin/python", "scripts/run_ci_deployment_shard.py",
            "--shard=2", "--report=/tmp/invented.json"]


def test_retained_executor_changes_only_the_declared_deployment_entrypoint():
    args = arguments()
    untouched = list(args)
    node, contracts = history.commands(args)
    original_node, original_contracts = history.ORIGINAL_COMMANDS(args[3:])
    assert node == original_node and args == untouched
    assert contracts == [*original_contracts[:3], "scripts/run_ci_retained_deployment.py", *original_contracts[4:]]


@pytest.mark.parametrize("change", ["executor", "workers", "shard"])
def test_arbitrary_executor_or_extra_worker_is_refused(change):
    args = arguments()
    if change == "executor":
        args[2] = "untrusted.py"
    elif change == "workers":
        args[7] = "--maxWorkers=2"
    else:
        args[8], args[-2] = "--shard=1/2", "--shard=1"
    with pytest.raises(ValueError):
        history.commands(args)


def test_parallel_children_reenter_overlay_and_keep_original_receipt_checks(monkeypatch):
    original_file, original_plan = overlay.driver.__file__, overlay.driver.plan
    def run():
        assert overlay.driver.plan is overlay.plan
        assert Path(overlay.driver.__file__).resolve() == Path(overlay.__file__).resolve()
        assert overlay.driver.merge_workers.__module__ == "run_ci_deployment_shard"
        return 37
    monkeypatch.setattr(overlay.driver, "__file__", original_file)
    monkeypatch.setattr(overlay.driver, "plan", original_plan)
    monkeypatch.setattr(overlay.driver, "main", run)
    assert overlay.main() == 37
