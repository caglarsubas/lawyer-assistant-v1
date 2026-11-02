"""Closed placement rejects omissions and requires actual non-skipped execution."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import ci_source_reviews as p  # noqa: E402


def test_frozen_source_and_three_lanes_preserve_every_original_identity():
    c = p.load_contract()
    assert len(c.ids) == 69 and {k: len(v) for k, v in c.lanes.items()} == dict.fromkeys(p.LANES, 23)
    ids = [x for lane in c.lanes.values() for x in lane]
    assert sorted(ids) == list(c.ids) and len(ids) == len(set(ids))


@pytest.mark.parametrize("kind", ["source", "missing", "overlap", "schema", "extra", "duplicate"])
def test_changed_source_or_manifest_fails_closed(tmp_path, kind):
    v = json.loads(p.MANIFEST.read_text())
    if kind == "source":
        v["source_sha256"] = "0" * 64
    elif kind == "missing":
        v["test_ids"].pop()
    elif kind == "overlap":
        v["lanes"]["candidate"] = v["lanes"]["withdrawal"]
    elif kind == "schema":
        v["schema"] = "unreviewed"
    elif kind == "extra":
        v["automatic_lane"] = True
    else:
        v["lanes"]["publication"][1] = v["lanes"]["publication"][0]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(v))
    with pytest.raises(ValueError):
        p.load_contract(path)


def test_full_collection_is_mandatory_and_unrelated_cases_are_untouched():
    c = p.load_contract()
    for ids in (c.ids[:-1], (*c.ids, c.ids[0]), (*c.ids[:-1], p.PREFIX + "test_invented")):
        with pytest.raises(ValueError):
            p.select(c, "candidate", ids)
    with pytest.raises(ValueError):
        p.select(c, "invented", c.ids)
    other = "tests/test_other.py::test_keep"
    assert p.select(c, "withdrawal", [other, *c.ids]) == [other, *c.lanes["withdrawal"]]
    with pytest.raises(pytest.UsageError):
        p.Partition(c, "candidate").pytest_xdist_node_collection_finished(list(c.ids))


def actual(tmp_path, lane, skip=False):
    marker = tmp_path / "executed.txt"
    code = "import pytest\n"
    for i in range(69):
        body = "pytest.skip('incomplete execution')" if skip and i == 0 else (
            f"with open({str(marker)!r}, 'a') as stream: stream.write('test_{i:02d}\\n')")
        code += f"\ndef test_{i:02d}():\n    {body}\n"
    source = tmp_path / "test_fixture.py"
    source.write_text(code)
    ids = tuple(f"test_fixture.py::test_{i:02d}" for i in range(69))
    lanes = {name: ids[i::3] for i, name in enumerate(p.LANES)}
    scaffold = ("from ci_source_reviews import Contract, Partition\n"
        "def pytest_configure(config):\n"
        f"    c = Contract({hashlib.sha256(source.read_bytes()).hexdigest()!r}, {ids!r}, {lanes!r})\n"
        f"    config.pluginmanager.register(Partition(c, {lane!r}), 'fixture-partition')\n")
    (tmp_path / "conftest.py").write_text(scaffold)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    # The serial child replaces its waiting parent; no additional active worker pair.
    v = subprocess.run([sys.executable, "-m", "pytest", str(source), "--rootdir", str(tmp_path),
        "--confcutdir", str(tmp_path), "-q"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=12)
    rows = [json.loads(s) for s in v.stdout.splitlines() if s.startswith('{"source_review_partition":')]
    return v.returncode, marker.read_text().splitlines() if marker.exists() else [], rows


@pytest.mark.parametrize("lane", p.LANES)
def test_actual_calls_and_receipt_match_independently_expected_lane(tmp_path, lane):
    status, calls, rows = actual(tmp_path, lane)
    slot = p.LANES.index(lane)
    assert status == 0 and calls == [f"test_{i:02d}" for i in range(slot, 69, 3)]
    assert len(rows) == 1 and rows[0]["complete_count"] == 69 and rows[0]["source_review_partition"] == lane
    assert rows[0]["selected_ids"] == [f"test_fixture.py::test_{i:02d}" for i in range(slot, 69, 3)]


def test_skipped_selected_case_cannot_publish_a_success_receipt(tmp_path):
    status, calls, rows = actual(tmp_path, "candidate", skip=True)
    assert status != 0 and len(calls) == 22 and not rows
