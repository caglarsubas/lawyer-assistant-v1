"""Protect actual cohort execution while redistributing bounded CI work."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import ci_authority_cohorts as partition  # noqa: E402


def test_real_contract_retains_all_original_identities_once():
    contract = partition.load_contract()
    assert len(contract.ids) == 19
    assert {k: len(v) for k, v in contract.lanes.items()} == {"review": 16, "database": 1, "history": 2}
    rows = [x for values in contract.lanes.values() for x in values]
    assert len(rows) == len(set(rows)) == 19 and sorted(rows) == list(contract.ids)


@pytest.mark.parametrize("change", ["source", "missing", "duplicate", "overlap", "schema"])
def test_changed_contract_is_rejected_before_execution(tmp_path, change):
    value = json.loads(partition.MANIFEST.read_text())
    if change == "source":
        value["source_sha256"] = "0" * 64
    elif change == "missing":
        value["test_ids"].pop()
    elif change == "duplicate":
        value["lanes"]["review"][1] = value["lanes"]["review"][0]
    elif change == "overlap":
        value["lanes"]["database"] = value["lanes"]["history"][:1]
    else:
        value["schema"] = "unreviewed-inventory"
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        partition.load_contract(path)


def test_collection_cannot_omit_duplicate_or_invent_an_identity():
    contract = partition.load_contract()
    for ids in (list(contract.ids[:-1]), [*contract.ids, contract.ids[0]],
                [*contract.ids[:-1], partition.PREFIX + "test_undeclared"]):
        with pytest.raises(ValueError):
            partition.select(contract, "review", ids)
    with pytest.raises(ValueError):
        partition.select(contract, "undeclared", list(contract.ids))
    other = "test_unrelated.py::test_retained"
    assert partition.select(contract, "database", [*contract.ids, other]) == [*contract.lanes["database"], other]


def test_expensive_cases_start_in_separate_worker_halves_without_losing_other_cases():
    contract = partition.load_contract()
    others = [f"test_other.py::test_{i:02d}" for i in range(49)]
    for lane in ("database", "history"):
        ids = partition.select(contract, lane, [*others, *contract.ids])
        assert [ids.index(x) for x in contract.lanes[lane]] == ([0] if lane == "database" else [0, len(ids) // 2])
        assert [x for x in ids if x not in contract.ids] == others
        plugin = partition.Partition(contract, lane)
        plugin.pytest_xdist_node_collection_finished(ids)
        ids[0], ids[1] = ids[1], ids[0]
        with pytest.raises(pytest.UsageError):
            plugin.pytest_xdist_node_collection_finished(ids)


def run_fixture(tmp_path, lane, skip=False):
    """A serial child replaces its waiting parent; no extra worker pair."""
    marker = tmp_path / "actual-calls.txt"
    code = "import pytest\n"
    for i in range(19):
        body = "pytest.skip('insufficient execution')" if skip and i == 0 else (
            f"with open({str(marker)!r}, 'a') as stream: stream.write('test_{i:02d}\\n')")
        code += f"\ndef test_{i:02d}():\n    {body}\n"
    source = tmp_path / "test_fixture.py"
    source.write_text(code)
    ids = tuple(f"test_fixture.py::test_{i:02d}" for i in range(19))
    lanes = {"review": ids[:16], "database": ids[16:17], "history": ids[17:]}
    scaffold = ("from ci_authority_cohorts import Contract, Partition\n"
        "def pytest_configure(config):\n"
        f"    contract = Contract({hashlib.sha256(source.read_bytes()).hexdigest()!r}, {ids!r}, {lanes!r})\n"
        f"    config.pluginmanager.register(Partition(contract, {lane!r}), 'fixture-partition')\n")
    (tmp_path / "conftest.py").write_text(scaffold)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    result = subprocess.run([sys.executable, "-m", "pytest", str(source), "--rootdir", str(tmp_path),
        "--confcutdir", str(tmp_path), "-q"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=12)
    actual = marker.read_text().splitlines() if marker.exists() else []
    receipts = [json.loads(row) for row in result.stdout.splitlines() if row.startswith('{"authority_cohort_partition":')]
    return result.returncode, actual, receipts


@pytest.mark.parametrize("lane,start,stop", [("review", 0, 16), ("database", 16, 17), ("history", 17, 19)])
def test_real_execution_and_receipt_match_independent_expected_calls(tmp_path, lane, start, stop):
    status, actual, receipts = run_fixture(tmp_path, lane)
    assert status == 0
    assert actual == [f"test_{i:02d}" for i in range(start, stop)]
    assert len(receipts) == 1
    assert receipts[0]["selected_ids"] == [f"test_fixture.py::test_{i:02d}" for i in range(start, stop)]
    assert receipts[0]["complete_count"] == 19 and receipts[0]["authority_cohort_partition"] == lane


def test_a_skipped_selected_case_cannot_publish_a_success_receipt(tmp_path):
    status, actual, receipts = run_fixture(tmp_path, "review", skip=True)
    assert status != 0 and len(actual) == 15 and receipts == []
