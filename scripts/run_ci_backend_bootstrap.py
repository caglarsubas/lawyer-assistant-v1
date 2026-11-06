"""Run the non-test frontend compile alongside the existing two test workers."""

import json
import signal
import sys
from pathlib import Path

from run_ci_history_workers import run

ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_absolute():
        raise SystemExit("An absolute deployment report path is required")

    def stop(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    build = ["timeout", "--kill-after=2s", "60s", "npm", "run", "build"]
    contracts = ["bash", "scripts/run_ci_contracts.sh", "backend/.venv/bin/python",
                 "scripts/run_ci_retained_deployment.py", "--shard=3", "--workers=2",
                 "--report=" + sys.argv[1]]
    status = run(build, contracts, node_cwd=ROOT / "frontend", contract_cwd=ROOT)
    if status == 0:
        print(json.dumps({"backend_bootstrap": "complete", "frontend_builds": 1, "test_workers": 2}), flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
