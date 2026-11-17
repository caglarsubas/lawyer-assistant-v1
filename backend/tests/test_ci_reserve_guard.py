"""Cost supervision against invented Actions metadata; no live token or API."""

import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_ci_reserve_guard as guard  # noqa: E402

SHA, RUN = "a" * 40, 123


def jobs():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {"jobs": [{"name": name, "head_sha": SHA, "run_id": RUN, "status": "completed",
        "conclusion": "success", "started_at": start.isoformat(),
        "completed_at": (start + timedelta(seconds=cap - 30)).isoformat()} for name, cap in guard.CAPS.items()]}


def test_all_closed_jobs_must_retain_the_original_floor():
    value = guard.inspect(jobs(), RUN, SHA, final=True)
    assert value == {"completed_siblings": 11, "minimum_reserve": 30}
    assert sum(guard.CAPS.values()) == 4200 and len(guard.CAPS) == 12


@pytest.mark.parametrize("fault", ["missing", "duplicate", "extra", "wrong_sha", "wrong_run", "cancelled",
                                   "failed", "29_seconds", "negative_time", "naive_time", "invalid_time"])
def test_incomplete_identity_failure_or_exhausted_reserve_is_not_qualified(fault):
    value = jobs()
    row = next(j for j in value["jobs"] if j["name"] == "frontend")
    if fault == "missing":
        value["jobs"].pop()
    elif fault == "duplicate":
        value["jobs"][-1] = copy.deepcopy(value["jobs"][0])
    elif fault == "extra":
        row["name"] = "unapproved"
    elif fault == "wrong_sha":
        row["head_sha"] = "b" * 40
    elif fault == "wrong_run":
        row["run_id"] += 1
    elif fault in {"cancelled", "failed"}:
        row["conclusion"] = fault
    elif fault == "29_seconds":
        row["completed_at"] = (datetime.fromisoformat(row["completed_at"]) + timedelta(seconds=1)).isoformat()
    elif fault == "negative_time":
        row["completed_at"] = "2025-12-31T00:00:00+00:00"
    elif fault == "naive_time":
        row["started_at"] = "2026-01-01T00:00:00"
    else:
        row["completed_at"] = "unparseable"
    with pytest.raises(guard.Rejected):
        guard.inspect(value, RUN, SHA, final=True)


def test_in_progress_observations_never_establish_a_final_timing_rejection():
    value = jobs()
    row = next(j for j in value["jobs"] if j["name"] == "frontend")
    row.update(status="in_progress", completed_at=None)
    assert guard.inspect(value, RUN, SHA)["completed_siblings"] == 10
    with pytest.raises(guard.Rejected, match="siblings_incomplete"):
        guard.inspect(value, RUN, SHA, final=True)


@pytest.mark.parametrize("completed", [False, True])
def test_existing_internal_phase_floor_is_checked_only_after_completion(completed):
    value = jobs()
    owner = next(j for j in value["jobs"] if j["name"] == guard.SELF)
    phase = {**owner, "name": "Test manifest-bound reader lifecycle slice 5",
             "status": "completed" if completed else "in_progress",
             "completed_at": "2026-01-01T00:00:46+00:00" if completed else None}
    owner["steps"] = [phase]
    if completed:
        with pytest.raises(guard.Rejected, match="phase_reserve"):
            guard.inspect(value, RUN, SHA)
    else:
        assert guard.inspect(value, RUN, SHA)["completed_siblings"] == 11


def test_pr_and_main_contexts_bind_the_api_run_without_forwarding_credentials(tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"head": {"sha": SHA}}}))
    env = {"GITHUB_ACTIONS": "true", "GITHUB_JOB": guard.SELF, "GH_TOKEN": "INVENTED_CI_TOKEN",
           "GITHUB_TOKEN": "OTHER_INVENTED_TOKEN", "GITHUB_REPOSITORY": "invented/repository",
           "GITHUB_RUN_ID": str(RUN), "GITHUB_EVENT_PATH": str(event), "GITHUB_SHA": "b" * 40}
    assert guard.context(env) == ("invented/repository", RUN, SHA)
    assert not {"GH_TOKEN", "GITHUB_TOKEN"} & guard.child_environment(env).keys()
    event.write_text("{}")
    assert guard.context(env)[2] == "b" * 40
    for key in ("GITHUB_ACTIONS", "GITHUB_JOB", "GH_TOKEN", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        with pytest.raises(guard.Rejected):
            guard.context({**env, key: ""})


def test_metadata_errors_never_echo_transport_output_or_token(capsys):
    result = subprocess.CompletedProcess([], 1, b"INVENTED_PRIVATE_OUTPUT", b"INVENTED_CI_TOKEN")
    with patch.object(guard.subprocess, "run", return_value=result):
        with pytest.raises(guard.Rejected, match="metadata_unavailable"):
            guard.snapshot("invented/repository", RUN, {"GH_TOKEN": "INVENTED_CI_TOKEN"})
    assert capsys.readouterr() == ("", "")


def test_own_disposable_process_group_stops_cleanly():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                               start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        guard.stop(process)
        assert process.poll() is not None and process.returncode != 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_non_backend_or_collection_commands_cannot_start_a_process():
    with patch.object(guard.subprocess, "Popen", side_effect=AssertionError("must not start")):
        for command in (["other"], ["pytest", "backend/tests", "--collect-only"]):
            with pytest.raises(guard.Rejected):
                guard.supervise(command, {})


@pytest.mark.parametrize("outcome", ["sibling_reserve", "siblings_incomplete", "child_failed"])
def test_supervision_stops_its_child_and_never_qualifies_incomplete_runs(outcome, capsys):
    original_popen = subprocess.Popen
    children = []
    def start(_command, **kwargs):
        assert "GH_TOKEN" not in kwargs["env"] and "GITHUB_TOKEN" not in kwargs["env"]
        code = "import time;time.sleep(60)" if outcome == "sibling_reserve" else "raise SystemExit(7)" if outcome == "child_failed" else "pass"
        child = original_popen([sys.executable, "-c", code], **kwargs,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(child)
        return child
    initial, final = jobs(), jobs()
    row = next(j for j in final["jobs"] if j["name"] == "frontend")
    if outcome == "sibling_reserve":
        row["completed_at"] = (datetime.fromisoformat(row["completed_at"]) + timedelta(seconds=1)).isoformat()
    else:
        row.update(status="in_progress", completed_at=None)
    env = {"GH_TOKEN": "INVENTED_CI_TOKEN", "GITHUB_TOKEN": "OTHER_INVENTED_TOKEN"}
    snapshots = iter([initial])
    def observed(*_):
        return next(snapshots, final)
    with patch.object(guard, "context", return_value=("invented/repository", RUN, SHA)), \
            patch.object(guard, "snapshot", side_effect=observed), \
            patch.object(guard, "POLL_SECONDS", .01), patch.object(guard.subprocess, "Popen", side_effect=start):
        if outcome == "child_failed":
            assert guard.supervise(["pytest", "backend/tests"], env) == 7
        else:
            with pytest.raises(guard.Rejected, match=outcome):
                guard.supervise(["pytest", "backend/tests"], env)
    assert len(children) == 1 and children[0].poll() is not None
    raw = capsys.readouterr().out
    assert "INVENTED_CI_TOKEN" not in raw and '"complete_backend_exit": 0' not in raw
