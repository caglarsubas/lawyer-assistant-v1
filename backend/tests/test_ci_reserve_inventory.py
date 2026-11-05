"""Gradual Actions inventory never replaces final, complete reserve qualification."""

import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import run_ci_reserve_guard_v2 as parent  # noqa: E402
from scripts import run_ci_reserve_guard_v3 as current  # noqa: E402

SHA, RUN = "a" * 40, 123


def jobs(core):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {"jobs": [{"name": name, "head_sha": SHA, "run_id": RUN, "status": "completed",
        "conclusion": "success", "started_at": start.isoformat(),
        "completed_at": (start + timedelta(seconds=cap - 30)).isoformat()}
        for name, cap in core.CAPS.items()]}


def test_gradual_inventory_keeps_all_policy_bounds_and_requires_complete_final():
    core, old = current.load_policy(), parent.load_policy()
    assert core.CAPS == old.CAPS and len(core.CAPS) == 13 and sum(core.CAPS.values()) == 4380
    assert core.STEP_CAPS == old.STEP_CAPS and core.FLOOR == old.FLOOR == 30
    assert core.POLL_SECONDS == old.POLL_SECONDS and core.policy_sha256() != old.policy_sha256()
    full = jobs(core)
    for count in (1, 11, 13):
        partial = {"jobs": full["jobs"][:count]}
        assert core.inspect(partial, RUN, SHA)["completed_siblings"] == count - 1
        if count < 13:
            with pytest.raises(core.Rejected, match="complete_job_inventory_required"):
                core.inspect(partial, RUN, SHA, final=True)
    assert core.inspect(full, RUN, SHA, final=True) == {"completed_siblings": 12, "minimum_reserve": 30}
    with pytest.raises(core.Rejected, match="inventory_regressed"):
        core.inspect({"jobs": full["jobs"][:11]}, RUN, SHA)
    with patch.object(current, "PARENT_SHA256", "0" * 64), pytest.raises(ValueError):
        current.load_policy()


def test_partial_snapshots_still_reject_identity_failure_and_exhausted_reserves():
    for mode in ("empty", "missing_self", "duplicate", "unknown", "wrong_head", "wrong_run", "failed",
                 "29_seconds", "bad_time", "phase_floor", "unfinished_final"):
        core = current.load_policy()
        value = {"jobs": jobs(core)["jobs"][:2]}
        row = value["jobs"][1]
        if mode == "empty":
            value["jobs"] = []
        elif mode == "missing_self":
            value["jobs"].pop(0)
        elif mode == "duplicate":
            value["jobs"].append(copy.deepcopy(row))
        elif mode == "unknown":
            row["name"] = "unapproved"
        elif mode == "wrong_head":
            row["head_sha"] = "b" * 40
        elif mode == "wrong_run":
            row["run_id"] = True
        elif mode == "failed":
            row["conclusion"] = "failure"
        elif mode == "29_seconds":
            row["completed_at"] = (datetime.fromisoformat(row["completed_at"]) + timedelta(seconds=1)).isoformat()
        elif mode == "bad_time":
            row["completed_at"] = "invalid"
        elif mode == "phase_floor":
            row["steps"] = [{**row, "name": "Test manifest-bound reader lifecycle slice 5",
                             "completed_at": "2026-01-01T00:00:46+00:00"}]
        else:
            value = jobs(core)
            value["jobs"][-1].update(status="in_progress", completed_at=None)
        with pytest.raises(core.Rejected):
            core.inspect(value, RUN, SHA, final=mode == "unfinished_final")
    for mode in ("valid", "timeout", "rejected", "oversized", "invalid"):
        core = current.load_policy()
        raw = json.dumps(jobs(core)).encode() if mode == "valid" else b" " * (2 * 1024**2 + 1) if mode == "oversized" else b"invalid"
        response = subprocess.CompletedProcess([], 1 if mode == "rejected" else 0, raw, b"INVENTED_ONLY")
        error = subprocess.TimeoutExpired([], 8) if mode == "timeout" else None
        with patch.object(current.subprocess, "run", return_value=response, side_effect=error) as request:
            if mode == "valid":
                assert core.snapshot("invented/repository", RUN, {}) == jobs(core)
            else:
                with pytest.raises(core.Rejected, match="metadata_"):
                    core.snapshot("invented/repository", RUN, {})
            assert request.call_count == 1 and request.call_args.kwargs["timeout"] == 8


def test_supervision_starts_once_on_partial_metadata_and_rejects_incomplete_final(capsys):
    original_popen = subprocess.Popen
    for complete in (True, False):
        core, children = current.load_policy(), []
        full = jobs(core)
        partial = {"jobs": full["jobs"][:11]}
        snapshots = iter([partial, full if complete else partial])

        def start(_command, **kwargs):
            assert not {"GH_TOKEN", "GITHUB_TOKEN"} & set(kwargs["env"])
            child = original_popen([sys.executable, "-c", "pass"], **kwargs,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(child)
            return child

        with patch.object(core, "context", return_value=("invented/repository", RUN, SHA)), \
                patch.object(core, "snapshot", side_effect=lambda *_: next(snapshots)), \
                patch.object(core.subprocess, "Popen", side_effect=start):
            if complete:
                assert core.supervise(["pytest", "backend/tests"], {"GH_TOKEN": "INVENTED_ONLY"}) == 0
            else:
                with pytest.raises(core.Rejected, match="complete_job_inventory_required"):
                    core.supervise(["pytest", "backend/tests"], {"GH_TOKEN": "INVENTED_ONLY"})
        assert len(children) == 1 and children[0].poll() is not None
        output = capsys.readouterr().out
        assert "INVENTED_ONLY" not in output
        assert ('"complete_backend_exit": 0' in output) == complete
