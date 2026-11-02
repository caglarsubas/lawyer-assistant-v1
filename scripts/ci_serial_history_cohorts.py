"""CI-only serial child of the closed two-process history controller."""

import json
import os

import pytest

from scripts import ci_authority_cohorts as original
from scripts import run_ci_history_review_pair as pair


def pytest_addoption(parser):
    original.pytest_addoption(parser)
    parser.addoption("--ci-serial-role", choices=("cohort", "inspection"))


def pytest_configure(config):
    try:
        profile = json.loads(pair.PROFILE.read_text())
        pair.validate(pair.COMMANDS, profile)
        if (hasattr(config, "workerinput") or config.getoption("numprocesses", default=None) is not None
                or os.environ.get("CI_HISTORY_PAIR_PARENT") != str(os.getppid())
                or os.environ.get("CI_HISTORY_PAIR_PROFILE") != pair.identity(profile)):
            raise ValueError("Closed controller child required")
        role = config.getoption("ci_serial_role")
        lane = config.getoption("authority_cohort_lane")
        if role == "cohort" and lane == "history":
            config.pluginmanager.register(original.Partition(original.load_contract(), "history"),
                                          "closed-authority-cohort-partition")
        elif role != "inspection" or lane is not None:
            raise ValueError("Exact serial role required")
    except (OSError, ValueError, TypeError, KeyError):
        raise pytest.UsageError("Source-bound history controller child required") from None
