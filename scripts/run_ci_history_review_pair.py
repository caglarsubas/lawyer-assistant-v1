"""CI-only closed serial pair. Two active test workers, no retry or runtime access."""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".github/fixtures/history_review_pair.json"
SECONDS = 50
FILES = ("backend/tests/test_authority_model_cohorts.py", "backend/tests/test_ci_authority_partition.py",
         "backend/tests/test_ci_budgeted_deployment.py", "backend/tests/test_ci_retained_history.py",
         "backend/tests/test_final_release_inspection.py", "scripts/ci_authority_cohorts.py",
         "deploy/fixtures/authority_cohort_partition.json", "scripts/run_ci_history_review_pair.py", "scripts/ci_serial_history_cohorts.py")
COMMANDS = (
    ("backend/.venv/bin/python", "-m", "pytest", "-p", "scripts.ci_serial_history_cohorts", "--authority-cohort-lane=history", "--ci-serial-role=cohort",
     *FILES[:4], "-q", "--maxfail=1"),
    ("backend/.venv/bin/python", "-m", "pytest", "-p", "scripts.ci_serial_history_cohorts",
     "--ci-serial-role=inspection", FILES[4], "-q", "--maxfail=1"),
)


def identity(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(commands, profile):
    if os.environ.get("PYTEST_ADDOPTS") or os.environ.get("PYTEST_PLUGINS"):
        raise ValueError("Unapproved pytest environment overrides")
    hashes = {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in FILES}
    if (tuple(tuple(x) for x in commands) != COMMANDS or not isinstance(profile, dict)
            or set(profile) != {"schema", "source_sha256", "seconds", "counts", "active_workers"}
            or profile["schema"] != "ci-history-review-pair-v1" or profile["source_sha256"] != hashes
            or type(profile["seconds"]) is not int or profile["seconds"] != SECONDS
            or profile["counts"] != [45, 8] or any(type(n) is not int for n in profile["counts"])
            or type(profile["active_workers"]) is not int or profile["active_workers"] != 2):
        raise ValueError("Closed source-bound serial pair required")
    return hashes


def run(commands, temporary, profile):
    hashes = validate(commands, profile)
    if temporary != temporary.resolve() or not temporary.is_dir() or any(temporary.iterdir()):
        raise ValueError("Fresh resolved disposable test directory required")
    processes = []
    started = time.monotonic()
    try:
        for i, command in enumerate(commands):
            processes.append(subprocess.Popen([*command, "--basetemp=" + str(temporary / str(i))], cwd=ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env={**os.environ, "CI_HISTORY_PAIR_PARENT": str(os.getpid()), "CI_HISTORY_PAIR_PROFILE": identity(profile)}))
        with ThreadPoolExecutor(max_workers=2) as reader:
            results = [reader.submit(p.communicate, timeout=max(.001, SECONDS - (time.monotonic() - started))) for p in processes]
            outputs = [future.result()[0] for future in results]
        if time.monotonic() - started > SECONDS or validate(commands, profile) != hashes:
            raise TimeoutError
        for raw in outputs:
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("Child output budget exceeded")
            print(raw.decode("utf-8"), end="", flush=True)
        for i, (process, raw) in enumerate(zip(processes, outputs, strict=True)):
            if process.returncode != 0:
                raise ValueError("Serial child did not exit successfully")
            value = raw.decode("utf-8")
            counts = re.findall(r"^\s*(\d+) passed(?:, [^\n]*)? in [^\n]+$", value, re.M)
            if counts != [str(profile["counts"][i])]:
                raise ValueError("Complete child execution counts required")
        if time.monotonic() - started > SECONDS:
            raise TimeoutError
        print(json.dumps({"history_review_pair": 1, "tests_run": 53, "child_counts": [45, 8],
            "clean_exits": [0, 0], "active_workers": 2, "seconds": round(time.monotonic() - started, 3),
            "source_sha256": hashes}), flush=True)
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[-1].startswith("--basetemp="):
        temporary = Path(args.pop().split("=", 1)[1])
    elif len(args) >= 2 and args[-2] == "--basetemp":
        temporary = Path(args[-1])
        args = args[:-2]
    else:
        raise ValueError("Disposable base directory required")
    if args.count(":::") != 1:
        raise ValueError("Two closed commands required")
    split = args.index(":::")
    profile = json.loads(PROFILE.read_text())
    commands = (args[:split], args[split + 1:])
    validate(commands, profile)
    temporary.mkdir(mode=0o700, exist_ok=False)
    return run(commands, temporary, profile)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError, TimeoutError, subprocess.SubprocessError):
        raise SystemExit("CI history pair rejected; no retry or budget extension") from None
