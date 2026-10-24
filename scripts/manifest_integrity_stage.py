"""Inert source-pinned package patch staging and fresh frozen log qualification.

No downloader, subprocess, server, model-store or application configuration access.
The source fix is applied only to an explicit, fresh disposable destination.
"""

import os
from pathlib import Path

from metadata_phase_probe import strict_json
from qualify_backend_store import MAX_LOG, MAX_SOURCE, MODULE, QualificationRejected, digest, read_regular

FIXTURES = Path(__file__).resolve().parents[1] / "deploy" / "fixtures"
SOURCE_LOCK_SHA256 = "14303acbd27213ec55a283ab5c5aee80706da942d6af72006ec59ec97c4b674b"
PATCH_SHA256 = "e675337c9f16a060c68eb63b448a5a3f298d5000e244068d9a5d5861440779dd"
CASES_SHA256 = "90ff5c2faf67edd2b2e96437d3797390add3ede292fcdde26d5dfb7bead5dfe5"
TEST_SHA256 = "ac557e49765801a8399da7a8ff1f826b3e91fb920103ce458bd9d6eb0c7b2fd5"


def locked(name, expected):
    raw = read_regular(FIXTURES / name, MAX_SOURCE)
    if digest(raw) != expected:
        raise QualificationRejected("Frozen input hash mismatch")
    return raw


def patched_manifest(raw):
    patch = strict_json(locked("manifest_integrity_patch.json", PATCH_SHA256))
    if patch["path"] != "manifest/manifest.go" or digest(raw) != patch["before_sha256"]:
        raise QualificationRejected("Patch preimage mismatch")
    text = raw.decode("utf-8")
    for change in patch["replacements"]:
        if text.count(change["before"]) != 1:
            raise QualificationRejected("Ambiguous patch context")
        text = text.replace(change["before"], change["after"], 1)
    result = text.encode("utf-8")
    if digest(result) != patch["after_sha256"]:
        raise QualificationRejected("Patch result mismatch")
    return result


def stage(source_root, destination, variant):
    if variant not in {"baseline", "patched"}:
        raise QualificationRejected("Unknown isolated variant")
    entry = strict_json(locked("backend_store_sources.json", SOURCE_LOCK_SHA256))["profiles"]["candidate"]
    raw_sources = {}
    for name, sha in entry["source_sha256"].items():
        raw = read_regular(Path(source_root) / name, MAX_SOURCE)
        if digest(raw) != sha:
            raise QualificationRejected("Upstream source changed")
        raw_sources[name] = raw
    for folder in ("envconfig", "manifest", "types/model"):
        actual = {str(p.relative_to(source_root)) for p in (Path(source_root) / folder).rglob("*.go")}
        if actual != {n for n in entry["compile_paths"] if str(Path(n).parent) == folder}:
            raise QualificationRejected("Unexpected package source")
    sources = {n: raw_sources[n] for n in entry["compile_paths"]}
    if variant == "patched":
        sources["manifest/manifest.go"] = patched_manifest(sources["manifest/manifest.go"])
    sources.update({
        "go.mod": MODULE, "LICENSE": raw_sources["LICENSE"],
        "manifest/integrity_frozen_test.go": locked("manifest_integrity_qualifier.go", TEST_SHA256),
        "manifest/integrity_cases.json": locked("manifest_integrity_cases.json", CASES_SHA256),
    })
    target = Path(destination).absolute()
    if target != target.resolve() or target.exists() or not target.parent.is_dir():
        raise QualificationRejected("Fresh unlinked destination required")
    target.mkdir(mode=0o700)
    for name, raw in sources.items():
        path = target / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(raw)
    return {
        "schema": "isolated-manifest-integrity-build-v1", "variant": variant,
        "upstream_commit": entry["commit"], "upstream_source_sha256": entry["source_sha256"],
        "generated_sha256": {n: digest(b) for n, b in sources.items()},
        "patch_sha256": PATCH_SHA256 if variant == "patched" else None,
        "cases_sha256": CASES_SHA256, "test_sha256": TEST_SHA256,
        "modified_upstream_paths": ["manifest/manifest.go"] if variant == "patched" else [],
        "scope": "isolated Linux manifest package only; no full server or live installation",
        "native_inference_calls": 0, "production_activation": False,
    }


def observe_log(raw, variant):
    if not isinstance(raw, bytes) or len(raw) > MAX_LOG or variant not in {"baseline", "patched"}:
        raise QualificationRejected("Invalid isolated log")
    cases = strict_json(locked("manifest_integrity_cases.json", CASES_SHA256))["cases"]
    expected = {c["id"]: c for c in cases}
    if len(cases) != len(expected) or len(cases) != 20:
        raise QualificationRejected("Invalid frozen inventory")
    seen, completions, roots, packages = {}, {}, [], []
    prefix = "TestFreshFrozenManifestIntegrity/"
    try:
        for line in raw.splitlines():
            event = strict_json(line)
            if event.get("Package") != "github.com/ollama/ollama/manifest" or event.get("Action") == "skip":
                raise QualificationRejected("Foreign or skipped work")
            action, test = event.get("Action"), event.get("Test")
            if action in {"pass", "fail"}:
                if test is None:
                    packages.append(action)
                elif test == "TestFreshFrozenManifestIntegrity":
                    roots.append(action)
                elif test.startswith(prefix) and test[len(prefix):] in expected:
                    key = test[len(prefix):]
                    if key in completions:
                        raise QualificationRejected("Duplicate completion")
                    completions[key] = action
                else:
                    raise QualificationRejected("Unknown completed test")
            output = event.get("Output", "")
            if "INTEGRITY_RESULT " in output:
                row = strict_json(output.split("INTEGRITY_RESULT ", 1)[1].strip())
                key = row["id"]
                if (
                    set(row) != {"id", "variant", "reader", "actual", "store_unchanged"}
                    or key not in expected or key in seen or row["variant"] != variant
                    or row["reader"] != expected[key]["reader"] or row["store_unchanged"] is not True
                    or row["actual"] not in {"matched", "missing", "rejected", "mismatched"}
                    or action != "output" or test != prefix + key
                ):
                    raise QualificationRejected("Invalid case result")
                seen[key] = row
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise QualificationRejected("Invalid qualification log") from exc
    if set(seen) != set(expected) or set(completions) != set(expected):
        raise QualificationRejected("Incomplete qualification log")
    matches = {k: seen[k]["actual"] == expected[k]["expected"] for k in seen}
    status = "pass" if all(matches.values()) else "fail"
    if roots != [status] or packages != [status] or any(
        completions[k] != ("pass" if matches[k] else "fail") for k in seen
    ):
        raise QualificationRejected("Inconsistent result and completion")
    return {
        "variant": variant, "cases": [dict(seen[k], expected=expected[k]["expected"],
                                          matches_expected=matches[k]) for k in sorted(seen)],
        "expected_results": sum(matches.values()), "failed_results": sum(not v for v in matches.values()),
        "raw_log_sha256": digest(raw), "scratch_store_unchanged": True,
        "scope": "fixed-scratch Linux manifest package tests; no HTTP/native/full-store qualification",
        "installed_backend_qualified": False, "executed_weights_qualified": False,
        "production_activation": False, "owner_review_completed": False,
    }


def qualify_log(raw):
    result = observe_log(raw, "patched")
    if result["failed_results"] or result["expected_results"] != 20:
        raise QualificationRejected("Isolated integrity gate failed")
    return result
