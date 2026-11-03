"""Read-only sibling-reserve supervision; stop only our own pytest process group."""

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CAPS = {"backend-and-contracts": 1140, "frontend": 300, "frontend-history": 300,
        "postgres-snapshot-concurrency": 300, "backend-review-contracts": 360,
        "final-release-authorization": 360, "graph-runtime-contracts": 360,
        "analysis-recovery-contracts": 360, "publication-planning-contracts": 240,
        "graph-candidate-contracts": 180, "source-publication-contracts": 180,
        "retained-release-withdrawal": 120}
SELF, FLOOR, POLL_SECONDS = "backend-and-contracts", 30, 20
STEP_CAPS = {"Test manifest-bound authenticated qualification": (120, 30),
             "Test manifest-bound reader lifecycle slice 5": (60, 15),
             "Test manifest-bound reader lifecycle slice 6": (60, 15),
             "Test manifest-bound reader namespace slice": (60, 15),
             **{"Test manifest-bound review headroom slice " + str(n): (60, 15) for n in (8, 9, 10)},
             "Test complete provision binding qualification": (120, 30),
             "Test complete workbench qualification": (120, 30),
             "Test complete disposition restart qualification": (120, 30),
             "Test complete analysis and recovery qualification": (360, 30),
             "Test complete publication and planning qualification": (240, 30),
             "Test complete portfolio review qualification": (120, 30)}


class Rejected(RuntimeError):
    """Only fixed codes and closed job names may appear in public diagnostics."""


def context(env):
    if (env.get("GITHUB_ACTIONS") != "true" or not env.get("GH_TOKEN")
            or env.get("GITHUB_JOB") != SELF
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", env.get("GITHUB_REPOSITORY", ""))
            or not re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", ""))):
        raise Rejected("github_context_required")
    path = Path(env["GITHUB_EVENT_PATH"])
    if not path.is_file() or path.stat().st_size > 2 * 1024**2:
        raise Rejected("event_identity_required")
    event = json.loads(path.read_bytes())
    sha = event.get("pull_request", {}).get("head", {}).get("sha", env.get("GITHUB_SHA", ""))
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Rejected("event_identity_required")
    return env["GITHUB_REPOSITORY"], int(env["GITHUB_RUN_ID"]), sha


def snapshot(repo, run, env):
    for _ in range(2):
        try:
            result = subprocess.run(["gh", "api", "--hostname", "github.com",
                f"repos/{repo}/actions/runs/{run}/jobs?filter=latest&per_page=100"],
                env=env, capture_output=True, timeout=4, check=False)
            if result.returncode == 0 and 0 < len(result.stdout) <= 2 * 1024**2:
                return json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    raise Rejected("metadata_unavailable")


def policy_sha256():
    return hashlib.sha256(json.dumps({"caps": CAPS, "steps": STEP_CAPS, "floor": FLOOR, "self": SELF},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def elapsed(row):
    try:
        start = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(row["completed_at"].replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError
        return (end - start).total_seconds()
    except (ValueError, TypeError, AttributeError):
        raise Rejected("job_timestamps_invalid") from None


def inspect(value, run, sha, *, final=False):
    if (not isinstance(value, dict) or not isinstance(value.get("jobs"), list)
            or len(value["jobs"]) != len(CAPS)):
        raise Rejected("complete_job_inventory_required")
    jobs, margins = value["jobs"], []
    if len({j["name"] for j in jobs}) != len(CAPS) or {j["name"] for j in jobs} != set(CAPS):
        raise Rejected("closed_unique_jobs_required")
    for job in jobs:
        name = job["name"]
        if job["head_sha"] != sha or type(job["run_id"]) is not int or job["run_id"] != run:
            raise Rejected("job_identity_mismatch")
        for step in job.get("steps", []):
            if step["status"] == "completed" and step["name"] in STEP_CAPS:
                cap, floor = STEP_CAPS[step["name"]]
                if step["conclusion"] != "success" or cap - elapsed(step) < floor:
                    raise Rejected("phase_reserve:" + name)
        if name == SELF:
            continue  # Its final duration is independently qualified after exit.
        if job["status"] != "completed":
            if final:
                raise Rejected("siblings_incomplete")
            continue  # Never reject from a stale in-progress API observation.
        if job["conclusion"] != "success":
            raise Rejected("sibling_failed:" + name)
        margin = CAPS[name] - elapsed(job)
        if margin < FLOOR:
            raise Rejected("sibling_reserve:" + name)
        margins.append(margin)
    return {"completed_siblings": len(margins), "minimum_reserve": min(margins, default=None)}


def child_environment(env):
    return {k: v for k, v in env.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN"}}


def stop(process):
    if process is None or process.poll() is not None:
        return
    if os.getpgid(process.pid) != process.pid:
        raise Rejected("owned_process_group_required")
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)


def supervise(command, env):
    if command[:2] != ["pytest", "backend/tests"] or "--collect-only" in command:
        raise Rejected("complete_backend_command_required")
    repo, run, sha = context(env)
    binding = {"run_id": run, "head_sha": sha, "policy_sha256": policy_sha256()}
    previous = inspect(snapshot(repo, run, env), run, sha)
    print("CI_RESERVE " + json.dumps({**binding, **previous}), flush=True)
    process = None
    try:
        process = subprocess.Popen(command, env=child_environment(env), start_new_session=True)
        while True:
            try:
                code = process.wait(timeout=POLL_SECONDS)
            except subprocess.TimeoutExpired:
                observed = inspect(snapshot(repo, run, env), run, sha)
                if observed != previous:
                    print("CI_RESERVE " + json.dumps({**binding, **observed}), flush=True)
                    previous = observed
                continue
            if code != 0:
                return code if code > 0 else 1
            observed = inspect(snapshot(repo, run, env), run, sha, final=True)
            print("CI_RESERVE " + json.dumps({**binding, **observed, "complete_backend_exit": 0}), flush=True)
            return 0
    finally:
        stop(process)  # The outer tmpfs wrapper runs its original EXIT cleanup.


if __name__ == "__main__":
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        if sys.argv[1:2] != ["--"]:
            raise Rejected("explicit_command_required")
        raise SystemExit(supervise(sys.argv[2:], dict(os.environ)))
    except Rejected as exc:
        print("CI_RESERVE_REJECTED " + json.dumps({"reason": str(exc)}), flush=True)
        raise SystemExit(1) from None
    except (KeyError, TypeError, ValueError, OSError, KeyboardInterrupt):
        raise SystemExit("CI reserve qualification failed; owned backend child stopped") from None
