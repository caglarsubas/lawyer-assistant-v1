"""Source-bound redistribution of 99 unchanged backend cases within fixed jobs."""

import hashlib
import json
import math
import re
from pathlib import Path

import pytest

from scripts.ci_source_reviews import Contract as BaseContract
from scripts.ci_source_reviews import Partition as BasePartition
from scripts.ci_source_reviews import select as select  # noqa: F401
from scripts.controller_stage_manifest import strict

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/fixtures/backend_spill_capacity.json"
SOURCES = ("backend/tests/test_graph_b_publication.py", "backend/tests/test_disposition_reconciliation_receipt.py", "backend/tests/test_authority_adjudications.py")
COUNTS = {'review': 14, 'database': 10, 'publication': 15, 'candidate': 9, 'graph': 9, 'capacity': 8, 'analysis': 6, 'frontend': 7, 'final': 5, 'withdrawal': 3, 'history': 6, 'planning': 7, 'backend': 0}
BUDGETS = {'review': 21000, 'database': 15000, 'publication': 22000, 'candidate': 13000, 'graph': 13000, 'capacity': 12000, 'analysis': 9000, 'frontend': 10000, 'final': 8000, 'withdrawal': 4000, 'history': 8000, 'planning': 10000, 'backend': 500}


class Contract(BaseContract):
    @property
    def prefix(self):
        return tuple(n.removeprefix("backend/") + "::" for n in SOURCES)


def estimated_increment(ids, costs):
    return math.ceil((sum(costs[n] for n in ids) + max((costs[n] for n in ids), default=0)) / 2) + 500


def load_contract(path=MANIFEST, root=ROOT):
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise ValueError("Metadata capacity manifest exceeds its bound")
    value = strict(raw)
    fields = {"schema", "source_sha256", "test_ids", "lanes", "case_cost_ms", "lane_increment_budget_ms",
              "observed_head", "observed_run", "local_xml_sha256", "retained_log_sha256", "normalization"}
    if (type(value) is not dict or set(value) != fields or value["schema"] != "backend-spill-capacity-v1"
            or value["source_sha256"] != {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in SOURCES}
            or value["observed_head"] != "99768ba50f3ab8befcc0f531f6bc1b460820a010"
            or value["observed_run"] != 42042276367 or type(value["observed_run"]) is not int
            or value["lane_increment_budget_ms"] != BUDGETS
            or type(value["normalization"]) is not str or not 1 <= len(value["normalization"]) <= 256):
        raise ValueError("Source-bound measured capacity evidence required")
    logs = value["retained_log_sha256"]
    if (type(logs) is not str or not re.fullmatch(r"[0-9a-f]{64}", logs)
            or type(value["local_xml_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["local_xml_sha256"])):
        raise ValueError("Exact retained timing commitments required")
    ids, lanes, costs = value["test_ids"], value["lanes"], value["case_cost_ms"]
    prefixes = tuple(n.removeprefix("backend/") + "::" for n in SOURCES)
    if (type(ids) is not list or len(ids) != 99 or ids != sorted(set(ids))
            or any(type(n) is not str or not n.startswith(prefixes) or len(n) > 1024 for n in ids)
            or [sum(n.startswith(p) for n in ids) for p in prefixes] != [31, 27, 41]
            or type(lanes) is not dict or set(lanes) != set(COUNTS)
            or type(costs) is not dict or set(costs) != set(ids)
            or any(type(x) is not int or not 0 < x <= 60000 for x in costs.values())):
        raise ValueError("Complete original metadata case identities required")
    all_ids = []
    for lane, count in COUNTS.items():
        selected = lanes[lane]
        if (type(selected) is not list or len(selected) != count or selected != sorted(set(selected))
                or not set(selected) <= set(ids) or estimated_increment(selected, costs) > BUDGETS[lane]):
            raise ValueError("Declared lane must fit its fixed measured increment")
        all_ids.extend(selected)
    if sorted(all_ids) != ids or len(set(all_ids)) != 99:
        raise ValueError("Every original metadata case must execute once")
    digest = hashlib.sha256(json.dumps(value["source_sha256"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return Contract(digest, tuple(ids), {k: tuple(v) for k, v in lanes.items()})


class Partition(BasePartition):
    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        if self.valid and exitstatus == 0 and not hasattr(terminalreporter.config, "workerinput"):
            terminalreporter.write_line(json.dumps({"backend_spill_capacity_partition": self.lane,
                "source_sha256": self.contract.source_sha256, "inventory_sha256": self.contract.inventory_sha256,
                "complete_count": 99, "selected_ids": sorted(self.passed)}))


def pytest_addoption(parser):
    parser.addoption("--backend-spill-capacity-lane", choices=tuple(COUNTS))


def pytest_configure(config):
    try:
        if (not hasattr(config, "workerinput") and not config.getoption("collectonly")
                and config.getoption("numprocesses", default=None) != 2):
            raise ValueError("Exactly two existing workers required")
        config.pluginmanager.register(Partition(load_contract(), config.getoption("backend_spill_capacity_lane")),
                                      "closed-backend-spill-capacity-partition")
    except (ValueError, OSError, KeyError, TypeError):
        raise pytest.UsageError("Exact metadata sources, complete inventory and measured lane required") from None
