"""Overlap one isolated Vitest worker and one complete unittest worker; no retries."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commands(arguments):
    if arguments.count(":::") != 1:
        raise ValueError("Two explicit bounded commands required")
    split = arguments.index(":::")
    node, contracts = arguments[:split], arguments[split + 1:]
    if (node[:5] != ["npm", "test", "--", "--shard=2/2", "--maxWorkers=1"] or len(node) != 8
            or node[5:7] != ["--reporter=default", "--reporter=json"] or not node[7].startswith("--outputFile=")
            or contracts != ["bash", "scripts/run_ci_contracts.sh", "backend/.venv/bin/python", "-m", "unittest", "discover", "-s", "deploy", "-p", "test_*.py"]):
        raise ValueError("Complete discovery and exactly two test workers required")
    return node, contracts


def run(node, contracts, *, node_cwd, contract_cwd):
    owned = []
    try:
        for argv, cwd in ((node, node_cwd), (contracts, contract_cwd)):
            owned.append(subprocess.Popen(argv, cwd=cwd, start_new_session=True))
        while True:
            states = [p.poll() for p in owned]
            failure = next((s for s in states if s is not None and s != 0), None)
            if failure is not None:
                return failure if failure > 0 else 128 - failure
            if all(s is not None for s in states):
                return 0
            time.sleep(0.05)
    finally:
        for process in owned:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for process in owned:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)


def main():
    def stop(signum, _frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    node, contracts = commands(sys.argv[1:])
    return run(node, contracts, node_cwd=ROOT / "frontend", contract_cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
