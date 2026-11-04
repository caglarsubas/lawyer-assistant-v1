"""Explicit13-job reserve policy; the qualified12-job core remains immutable."""

import hashlib
import importlib.util
import json
import os
import signal
import sys
from pathlib import Path

CORE = Path(__file__).with_name("run_ci_reserve_guard.py")
CORE_SHA256 = "ecde14eea0eb7a3c0835010e856c1c3e6ea0db286f3def41b15195ade18fd7a2"


def load_policy():
    if hashlib.sha256(CORE.read_bytes()).hexdigest() != CORE_SHA256:
        raise ValueError("CI reserve core source changed")
    spec = importlib.util.spec_from_file_location("isolated_ci_reserve_v2", CORE)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    assert len(core.CAPS) == 12 and sum(core.CAPS.values()) == 4200 and core.FLOOR == 30
    core.CAPS = {**core.CAPS, "backend-capacity": 180}
    return core


def main():
    core = load_policy()

    def interrupted(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
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
