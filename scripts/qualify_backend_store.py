"""Build an inert, hash-locked Go package test module and check its JSON log.

No downloader, subprocess launcher, server, config, model-store or secret import.
Only explicitly supplied public source is copied. Container execution is an
operator step; a passing report never authorizes activation or generation.
"""

import hashlib
import json
import os
import re
import stat
from pathlib import Path

from metadata_phase_probe import strict_json

FIXTURES = Path(__file__).resolve().parents[1] / "deploy" / "fixtures"
MAX_SOURCE = 512 * 1024
MAX_LOG = 2 * 1024 * 1024
MODULE = b"module github.com/ollama/ollama\n\ngo 1.26.10\n"


class QualificationRejected(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path, limit):
    """Reject linked paths and read one bounded regular-file descriptor."""
    path = Path(path).absolute()
    if path != path.resolve():
        raise QualificationRejected("Linked source path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise QualificationRejected("Invalid source file")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise QualificationRejected("Source changed")
    return raw


def build(source_root, destination, profile):
    lock = json.loads(read_regular(FIXTURES / "backend_store_sources.json", MAX_SOURCE))
    if profile not in {"release", "candidate"}:
        raise QualificationRejected("Unknown profile")
    entry = lock["profiles"][profile]
    expected = entry["source_sha256"]
    payload = {}
    for name, sha in expected.items():
        if name not in {"go.mod", "LICENSE", "server/routes.go", "server/images.go"} and not re.fullmatch(
            r"(?:envconfig|manifest|types/model)/[a-z_]+\.go", name
        ):
            raise QualificationRejected("Source inventory invalid")
        raw = read_regular(Path(source_root) / name, MAX_SOURCE)
        if digest(raw) != sha:
            raise QualificationRejected("Source hash mismatch")
        payload[name] = raw
    compile_paths = entry["compile_paths"]
    if set(compile_paths) != {n for n in expected if n.endswith(".go") and not n.startswith("server/")}:
        raise QualificationRejected("Incomplete package inventory")
    # Extra executable package files must not silently join a qualified build.
    for folder in ("envconfig", "manifest", "types/model"):
        actual = {str(p.relative_to(source_root)) for p in (Path(source_root) / folder).rglob("*.go")}
        if actual != {n for n in compile_paths if str(Path(n).parent) == folder}:
            raise QualificationRejected("Unexpected package source")
    generated = {n: payload[n] for n in compile_paths}
    generated.update({
        "go.mod": MODULE,
        "LICENSE": payload["LICENSE"],
        "qualifier/qualifier_test.go": read_regular(FIXTURES / "backend_store_qualifier.go", MAX_SOURCE),
        "qualifier/cases.json": read_regular(FIXTURES / "backend_store_cases.json", MAX_SOURCE),
    })
    target = Path(destination).absolute()
    if target != target.resolve() or target.exists() or not target.parent.is_dir():
        raise QualificationRejected("Fresh unlinked destination required")
    target.mkdir(mode=0o700)
    for name, raw in generated.items():
        path = target / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(raw)
    receipt = {
        "schema": "isolated-backend-build-v1", "profile": profile, "commit": entry["commit"],
        "source_sha256": expected, "module_scope": lock["build_scope"],
        "upstream_go_requirement": entry["upstream_go_requirement"],
        "generated_sha256": {n: digest(raw) for n, raw in generated.items()},
        "server_built": False, "model_files_copied": False, "native_inference_calls": 0,
    }
    return receipt


def check_log(raw, profile, cases=None):
    """Grade only complete, successful, unique go-test events against frozen cases."""
    if not isinstance(raw, bytes) or len(raw) > MAX_LOG or profile not in {"release", "candidate"}:
        raise QualificationRejected("Invalid qualification log")
    cases = cases or json.loads(read_regular(FIXTURES / "backend_store_cases.json", MAX_SOURCE))["cases"]
    expected = {c["id"]: c["expected"][profile] for c in cases}
    if len(expected) != 15 or len(cases) != 15:
        raise QualificationRejected("Invalid case inventory")
    seen, passes, package_pass = {}, set(), 0
    try:
        for line in raw.splitlines():
            event = strict_json(line)
            if event.get("Package") != "github.com/ollama/ollama/qualifier":
                raise QualificationRejected("Unexpected package")
            if event.get("Action") in {"fail", "skip"}:
                raise QualificationRejected("Failed or skipped qualification")
            if event.get("Action") == "pass":
                test = event.get("Test")
                if test is None:
                    package_pass += 1
                elif test.startswith("TestFrozenReferences/"):
                    case_id = test.removeprefix("TestFrozenReferences/")
                    if case_id in passes:
                        raise QualificationRejected("Duplicate successful case")
                    passes.add(case_id)
            text = event.get("Output", "")
            marker = "QUALIFIER_RESULT "
            if marker in text:
                row = strict_json(text.split(marker, 1)[1].strip())
                case_id = row["id"]
                if (
                    set(row) != {"id", "profile", "actual", "store_unchanged"}
                    or case_id not in expected or case_id in seen
                    or row["profile"] != profile or row["actual"] != expected[case_id]
                    or row["store_unchanged"] is not True
                    or event.get("Test") != "TestFrozenReferences/" + case_id
                    or event.get("Action") != "output"
                ):
                    raise QualificationRejected("Unexpected case result")
                seen[case_id] = row
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise QualificationRejected("Invalid or incomplete qualification") from exc
    if set(seen) != set(expected) or passes != set(expected) or package_pass != 1:
        raise QualificationRejected("Incomplete qualification")
    return {
        "profile": profile, "cases": [seen[k] for k in sorted(seen)], "expected_results": 15,
        "store_unchanged": True, "raw_log_sha256": digest(raw),
        "scope": "compiled upstream parser/manifest package lookup, not HTTP/native execution",
        "installed_backend_qualified": False, "executed_weights_qualified": False,
        "production_activation": False, "owner_review_completed": False,
    }
