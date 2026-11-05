"""Validate gradually exposed jobs; require the complete inventory at final exit."""

import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

PARENT = Path(__file__).with_name("run_ci_reserve_guard_v2.py")
PARENT_SHA256 = "ec1aefdb5f96bf72259c3e2fe1fd72366064b01a0ad48058468dbfe5431eb341"


def snapshot(repo, run, env, rejected):
    """One bounded request uses the original aggregate eight-second allowance."""
    try:
        response = subprocess.run(["gh", "api", "--hostname", "github.com",
            f"repos/{repo}/actions/runs/{run}/jobs?filter=latest&per_page=100"],
            env={**env, "GODEBUG": "http2client=0"}, capture_output=True, timeout=8, check=False)
    except subprocess.TimeoutExpired:
        raise rejected("metadata_transport_deadline") from None
    except OSError:
        raise rejected("metadata_client_unavailable") from None
    if response.returncode != 0:
        raise rejected("metadata_cli_rejected")
    if not 0 < len(response.stdout) <= 2 * 1024**2:
        raise rejected("metadata_payload_bound")
    try:
        return json.loads(response.stdout)
    except (ValueError, UnicodeError):
        raise rejected("metadata_invalid_json") from None


def load_policy():
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA256:
        raise ValueError("CI thirteen-job policy changed")
    spec = importlib.util.spec_from_file_location("isolated_ci_reserve_v3_parent", PARENT)
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    core = parent.load_policy()
    complete_inspect, seen = core.inspect, set()
    policy = hashlib.sha256(json.dumps({"parent": core.policy_sha256(),
        "inventory": "monotonic-visible-jobs-complete-final-v1",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def inspect(value, run, sha, *, final=False):
        if final:
            return complete_inspect(value, run, sha, final=True)
        if (type(value) is not dict or type(value.get("jobs")) is not list
                or not 1 <= len(value["jobs"]) <= len(core.CAPS)
                or any(type(j) is not dict or type(j.get("name")) is not str for j in value["jobs"])):
            raise core.Rejected("visible_job_inventory_required")
        jobs = value["jobs"]
        names = {j["name"] for j in jobs}
        if len(names) != len(jobs) or not names <= set(core.CAPS) or core.SELF not in names:
            raise core.Rejected("closed_unique_jobs_required")
        if not seen <= names:
            raise core.Rejected("observed_job_inventory_regressed")
        margins = []
        for job in jobs:
            name = job["name"]
            if job.get("head_sha") != sha or type(job.get("run_id")) is not int or job["run_id"] != run:
                raise core.Rejected("job_identity_mismatch")
            for step in job.get("steps", []):
                if step["status"] == "completed" and step["name"] in core.STEP_CAPS:
                    cap, floor = core.STEP_CAPS[step["name"]]
                    if step["conclusion"] != "success" or cap - core.elapsed(step) < floor:
                        raise core.Rejected("phase_reserve:" + name)
            if name == core.SELF or job["status"] != "completed":
                continue
            if job["conclusion"] != "success":
                raise core.Rejected("sibling_failed:" + name)
            margin = core.CAPS[name] - core.elapsed(job)
            if margin < core.FLOOR:
                raise core.Rejected("sibling_reserve:" + name)
            margins.append(margin)
        seen.update(names)
        return {"completed_siblings": len(margins), "minimum_reserve": min(margins, default=None)}

    core.inspect = inspect
    core.snapshot = lambda repo, run, env: snapshot(repo, run, env, core.Rejected)
    core.policy_sha256 = lambda: policy
    return core


def admission(env, core=None):
    """Read-only transport admission in the existing capacity job, never a verdict."""
    core = core if core is not None else load_policy()
    # This isolated policy instance checks the actual admission-job identity.
    # It never starts a child or issues the backend's final qualification receipt.
    core.SELF = "backend-capacity"
    repo, run, sha = core.context(env)
    core.inspect(core.snapshot(repo, run, env), run, sha)
    return {"metadata_admission": 1, "run_id": run, "head_sha": sha,
            "job": core.SELF, "transport": "http1", "request_budget_seconds": 8,
            "complete_run_qualified": False}


def main():
    core = load_policy()

    def interrupted(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        if sys.argv[1:] == ["--admission"]:
            print("CI_METADATA_ADMISSION " + json.dumps(admission(dict(os.environ), core)), flush=True)
            return 0
        if sys.argv[1:2] != ["--"]:
            raise core.Rejected("explicit_command_required")
        return core.supervise(sys.argv[2:], dict(os.environ))
    except core.Rejected as exc:
        print("CI_RESERVE_REJECTED " + json.dumps({"reason": str(exc)}), flush=True)
        return 1
    except (KeyError, TypeError, ValueError, OSError, KeyboardInterrupt):
        raise SystemExit("CI reserve qualification failed; owned backend child stopped") from None


if __name__ == "__main__":
    raise SystemExit(main())
