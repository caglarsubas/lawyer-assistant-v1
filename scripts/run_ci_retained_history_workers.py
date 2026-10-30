"""Validate/delegate to the frozen two-worker executor with one declared overlay."""

import run_ci_history_workers as retained
from run_ci_retained_deployment import profile

ORIGINAL_COMMANDS = retained.commands
EXECUTOR = ["--executor", "python", "scripts/run_ci_history_workers.py"]


def commands(arguments):
    profile()  # Includes the exact retained executor and driver source hashes.
    if arguments[:3] != EXECUTOR:
        raise ValueError("Explicit retained executor identity required")
    node, contracts = ORIGINAL_COMMANDS(arguments[3:])
    if node[5] != "--shard=2/2" or contracts[4] != "--shard=2":
        raise ValueError("Only the declared one-worker history partition may overlap")
    contracts = [*contracts]
    contracts[3] = "scripts/run_ci_retained_deployment.py"
    return node, contracts


def main():
    retained.commands = commands
    return retained.main()


if __name__ == "__main__":
    raise SystemExit(main())
