"""Frozen, synthetic metadata HTTP qualification of an isolated full server.

Importing starts nothing. Only run_campaign starts the fixed disposable binary;
it refuses ordinary host execution. No app settings, signer or provider credential.
"""

import base64
import hashlib
import http.client
import json
import os
import resource
import signal
import struct
import subprocess
import time
from pathlib import Path

from metadata_phase_probe import strict_json

FIXTURES = Path(__file__).resolve().parents[1] / "deploy" / "fixtures"
HOST, PORT = "127.0.0.1", 11579
VERSION = "isolated-http-675150d-integrity1"
BINARY_SHA256 = "e4743bfe2882029f3d88643ae233857211654a36d9316dca3fae9103468b265f"
BUILD_SHA256 = "c64349220731806a912f64304f908d01e6e741f5afa8cb85f75a8f42cb164736"
CASES_SHA256 = "d2bcfb39a083800e96a75a75b2ed8cff8238a6cb90a8fb2994db53967c0c063f"
NAMED = "http-qualifier-s26:review"
MAX_REPLY = 1024 * 1024


class QualificationRejected(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def cases():
    raw = (FIXTURES / "server_http_cases.json").read_bytes()
    if digest(raw) != CASES_SHA256:
        raise QualificationRejected("Frozen case inventory changed")
    value = strict_json(raw)
    if len(value["cases"]) != 26 or len({c["id"] for c in value["cases"]}) != 26:
        raise QualificationRejected("Invalid case inventory")
    return value


def build_definition():
    raw = (FIXTURES / "server_http_build.json").read_bytes()
    if digest(raw) != BUILD_SHA256:
        raise QualificationRejected("Frozen build definition changed")
    return strict_json(raw)


def regular_source_tree(root):
    root = Path(root).absolute()
    if root != root.resolve() or not root.is_dir():
        raise QualificationRejected("Unlinked source root required")
    nodes = list(root.rglob("*"))
    if len(nodes) > 10000 or any(p.is_symlink() for p in nodes):
        raise QualificationRejected("Unexpected source tree")
    files, size = {}, 0
    for p in sorted(nodes):
        if p.is_dir():
            continue
        if not p.is_file() or p.stat().st_nlink != 1 or p.stat().st_size > 32 * 1024 * 1024:
            raise QualificationRejected("Unexpected source file")
        size += p.stat().st_size
        if size > 512 * 1024 * 1024:
            raise QualificationRejected("Source tree bound")
        files[str(p.relative_to(root))] = file_hash(p)
    return files


def verify_build_inputs(original, derived):
    spec = build_definition()
    before, after = regular_source_tree(original), regular_source_tree(derived)
    if (len(before) != spec["upstream_files"] or before.keys() != after.keys()
            or digest(canonical(before)) != spec["upstream_tree_sha256"]
            or digest(canonical(after)) != spec["derived_tree_sha256"]):
        raise QualificationRejected("Build source identity mismatch")
    changed = sorted(n for n in before if before[n] != after[n])
    if changed != ["go.sum", "manifest/manifest.go"]:
        raise QualificationRejected("Unexpected derived source changes")
    old = set((Path(original) / "go.sum").read_text().splitlines())
    new = set((Path(derived) / "go.sum").read_text().splitlines())
    if not old <= new or sorted(new - old) != spec["added_checksum_lines"]:
        raise QualificationRejected("Dependency lock changed")
    return {"upstream_files": len(before), "changed_paths": changed,
            "go_mod_unchanged": before["go.mod"] == after["go.mod"],
            "derived_tree_sha256": digest(canonical(after))}


def inventory(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            result[rel] = {"link": os.readlink(path)}
        elif path.is_dir():
            result[rel] = {"directory": True}
        elif path.is_file():
            result[rel] = {"sha256": file_hash(path), "bytes": path.stat().st_size}
        else:
            raise QualificationRejected("Unexpected fixture node")
    return result


def minimal_gguf():
    """Invented GGUF metadata, zero tensors and no executable weights."""
    values = {
        "general.architecture": "llama", "general.name": "invented-metadata-S26",
        "general.file_type": 1, "llama.context_length": 128,
        "llama.embedding_length": 8, "llama.block_count": 0,
    }

    def string(value):
        raw = value.encode()
        return struct.pack("<Q", len(raw)) + raw

    raw = b"GGUF" + struct.pack("<IQQ", 3, 0, len(values))
    for key, value in sorted(values.items()):
        raw += string(key)
        raw += struct.pack("<I", 8) + string(value) if isinstance(value, str) else struct.pack("<II", 4, value)
    return raw + b"\0" * (-len(raw) % 32)


def prepare(root):
    root = Path(root).absolute()
    if root != root.resolve() or root.exists() or not root.parent.is_dir():
        raise QualificationRejected("Fresh unlinked fixture destination required")
    root.mkdir(mode=0o700)
    models = root / "models"
    for name in ("manifests", "manifests-v2", "blobs"):
        (models / name).mkdir(parents=True, mode=0o700)

    def write(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(raw)

    def blob(raw):
        sha = digest(raw)
        path = models / "blobs" / ("sha256-" + sha)
        if not path.exists():
            write(path, raw)
        return {"digest": "sha256:" + sha, "size": len(raw)}

    def named(name, raw):
        model, tag = name.split(":", 1)
        write(models / "manifests/registry.ollama.ai/library" / model / tag, raw)

    config = blob(canonical({"model_format": "gguf", "model_family": "llama", "model_families": ["llama"],
                             "model_type": "invented-zero-tensor", "file_type": "F16",
                             "architecture": "arm64", "os": "linux"}))
    config["mediaType"] = "application/vnd.docker.container.image.v1+json"
    layer = blob(minimal_gguf())
    layer["mediaType"] = "application/vnd.ollama.image.model"
    template = blob(b"{{ .Prompt }}")
    template["mediaType"] = "application/vnd.ollama.image.template"

    def manifest(label, model_layer=layer):
        return canonical({"schemaVersion": 2,
                          "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                          "config": config, "layers": [model_layer, template], "annotation": label})

    raw = manifest("fresh-http-S26-main")
    valid = digest(raw)
    blob(raw)
    named(NAMED, raw)
    legacy_raw = manifest("fresh-http-S26-legacy")
    legacy = digest(legacy_raw)
    named("legacy-s26:review", legacy_raw)
    corrupt_raw = manifest("fresh-http-S26-corrupt")
    corrupt = digest(corrupt_raw)
    write(models / "blobs" / ("sha256-" + corrupt), corrupt_raw + b" ")
    link = digest(manifest("fresh-http-S26-link"))
    (models / "blobs" / ("sha256-" + link)).symlink_to("sha256-" + valid)
    alias = digest(manifest("fresh-http-S26-never-a-blob"))
    named("sha256:" + alias, raw)
    bad_layer = blob(b"INVENTED-S26-NOT-GGUF")
    bad_layer["mediaType"] = "application/vnd.ollama.image.model"
    bad_raw = manifest("fresh-http-S26-invalid-metadata", bad_layer)
    blob(bad_raw)
    named("bad-gguf-s26:review", bad_raw)
    result = {"schema": "synthetic-server-fixtures-v1", "valid": valid, "legacy": legacy,
              "corrupt": corrupt, "link": link, "alias": alias, "model_tensors": 0,
              "model_weights": False, "invented_only": True}
    write(root / "fixture.json", canonical(result))
    return result


class MetadataHTTP:
    ALLOWED = {("GET", "/api/version"), ("GET", "/api/tags"), ("GET", "/api/ps"),
               ("GET", "/api/show"), ("GET", "/qualification-not-found"), ("POST", "/api/show")}

    def __init__(self, factory=http.client.HTTPConnection):
        self.factory, self.frames = factory, []

    def exchange(self, method, path, body=b"", case_id="startup"):
        if (method, path) not in self.ALLOWED or not isinstance(body, bytes) or len(body) > 2048:
            raise QualificationRejected("Forbidden request")
        if method != "POST" and body:
            raise QualificationRejected("Unexpected body")
        connection = self.factory(HOST, PORT, timeout=2)
        start = time.monotonic()
        active_socket = None

        def remaining():
            value = 2 - (time.monotonic() - start)
            if value <= 0:
                raise QualificationRejected("Response deadline")
            if active_socket is not None:
                active_socket.settimeout(value)
            return value

        try:
            connection.connect()
            active_socket = connection.sock
            remaining()
            connection.request(method, path, body=body, headers={
                "Content-Type": "application/json", "User-Agent": "isolated-synthetic-qualification/1"})
            remaining()
            response = connection.getresponse()
            if response.getheader("Content-Encoding", "").lower() not in {"", "identity"}:
                raise QualificationRejected("Compressed response")
            raw = bytearray()
            while True:
                remaining()
                chunk = response.read1(min(65536, MAX_REPLY + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > MAX_REPLY:
                    raise QualificationRejected("Response bound")
            wire = bytes(raw)
            row = {"id": case_id, "method": method, "path": path, "status": response.status,
                   "request_sha256": digest(body), "response_sha256": digest(wire),
                   "request_base64": base64.b64encode(body).decode(),
                   "response_base64": base64.b64encode(wire).decode(),
                   "content_type": response.getheader("Content-Type", "")}
            self.frames.append(row)
            return row, wire
        finally:
            connection.close()


def payload(fixture, info):
    refs = {"named": NAMED, "colon": "sha256:" + info["valid"], "dash": "sha256-" + info["valid"],
            "bare": info["valid"], "prefix": info["valid"][:12],
            "uppercase": "SHA256:" + info["valid"].upper(), "absent_digest": "sha256:" + "0" * 64,
            "absent_name": "http-qualifier-s26:absent", "corrupt_manifest": "sha256:" + info["corrupt"],
            "direct_link": "sha256:" + info["link"], "alias_no_fallback": "sha256:" + info["alias"],
            "legacy_named": "legacy-s26:review", "legacy_digest": "sha256:" + info["legacy"],
            "named_cloud": NAMED + ":cloud", "digest_cloud": "sha256:" + info["valid"] + ":cloud",
            "bad_gguf": "bad-gguf-s26:review", "verbose": NAMED, "invalid_runner": NAMED}
    if fixture == "malformed_json":
        return b"{"
    if fixture == "missing_model":
        return b"{}"
    if fixture not in refs:
        return b""
    value = {"model": refs[fixture], "verbose": fixture == "verbose"}
    if fixture == "invalid_runner":
        value["runner"] = "not-a-runner"
    return canonical(value)


def validate_case(case, row, raw, info, projection, reference):
    if row["status"] != case["expected_status"]:
        return False, reference
    fixture = case["fixture"]
    if fixture in {"wrong_method", "unknown_route"}:
        return True, reference
    value = strict_json(raw)
    if not isinstance(value, dict):
        return False, reference
    if row["status"] >= 400:
        valid = isinstance(value.get("error"), str) and bool(value["error"])
        if fixture == "corrupt_manifest":
            valid = valid and "digest mismatch" in value["error"]
        if fixture == "direct_link":
            valid = valid and "invalid regular manifest blob" in value["error"]
        return valid, reference
    if fixture == "version":
        return value.get("version") == VERSION, reference
    if fixture == "tags":
        found = [v for v in value.get("models", []) if v.get("name") == NAMED]
        return len(found) == 1 and found[0].get("digest") == info["valid"], reference
    if fixture == "empty_inventory":
        return value.get("models") == [], reference
    valid = value.get("model_info", {}).get("general.architecture") == "llama"
    valid = valid and value.get("model_info", {}).get("general.parameter_count") == 0
    valid = valid and value.get("details", {}).get("format") == "gguf"
    if fixture == "verbose":
        valid = valid and value.get("tensors", []) == []
    selected = {k: value.get(k) for k in projection}
    if fixture == "named":
        reference = selected
    elif fixture in {"colon", "dash", "bare", "prefix", "uppercase"}:
        valid = valid and reference is not None and selected == reference
    return valid, reference


def run_campaign():
    if not Path("/.dockerenv").is_file() or os.environ.get("QUALIFICATION_ISOLATED") != "1":
        raise QualificationRejected("Isolated operator container required")
    spec = cases()
    build = build_definition()
    binary, fixtures, receipts = Path("/bin-stage/ollama"), Path("/fixtures"), Path("/receipts")
    if file_hash(binary) != BINARY_SHA256:
        raise QualificationRejected("Unexpected binary")
    info = strict_json((fixtures / "fixture.json").read_bytes())
    before = inventory(fixtures)
    if (digest(canonical(before)) != build["fixture_inventory_sha256"]
            or build["binary_sha256"] != BINARY_SHA256 or build["version_label"] != VERSION):
        raise QualificationRejected("Fixture or build identity changed")
    client, rows, reference = MetadataHTTP(), [], None
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/scratch/home", "TMPDIR": "/scratch",
           "OLLAMA_HOST": HOST + ":" + str(PORT), "OLLAMA_MODELS": "/fixtures/models",
           "OLLAMA_NO_CLOUD": "1", "OLLAMA_NOPRUNE": "1", "OLLAMA_KEEP_ALIVE": "0",
           "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1", "GOMAXPROCS": "2"}
    Path(env["HOME"]).mkdir(mode=0o700, parents=True, exist_ok=True)
    error, executable_before, executable_after, child = None, None, None, None
    forced_kill, exit_code, ready_attempts = False, None, 0

    def child_limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))

    with (receipts / "server.private.log").open("xb") as log:
        try:
            child = subprocess.Popen([str(binary), "serve"], env=env, cwd="/scratch", stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=log, start_new_session=True, preexec_fn=child_limits)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and ready_attempts < 100:
                ready_attempts += 1
                if child.poll() is not None:
                    raise QualificationRejected("Server startup failed")
                try:
                    row, raw = client.exchange("GET", "/api/version")
                    if row["status"] == 200 and strict_json(raw).get("version") == VERSION:
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(0.1)
            else:
                raise QualificationRejected("Server readiness deadline")
            executable_before = file_hash(Path("/proc") / str(child.pid) / "exe")
            for case in spec["cases"]:
                row, raw = client.exchange(case["method"], case["path"], payload(case["fixture"], info), case["id"])
                valid, reference = validate_case(case, row, raw, info, spec["comparison_fields"], reference)
                rows.append({"id": case["id"], "fixture": case["fixture"], "status": row["status"],
                             "expected_status": case["expected_status"], "matches_expected": bool(valid),
                             "request_sha256": row["request_sha256"], "response_sha256": row["response_sha256"]})
            executable_after = file_hash(Path("/proc") / str(child.pid) / "exe")
        except (ValueError, OSError, KeyError, TypeError, http.client.HTTPException):
            error = "isolated_run_unmeasured_or_invalid"
        finally:
            if child is not None:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    exit_code = child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    forced_kill = True
                    os.killpg(child.pid, signal.SIGKILL)
                    exit_code = child.wait(timeout=5)
    unchanged = inventory(fixtures) == before
    identity = executable_before == executable_after == BINARY_SHA256 == file_hash(binary)
    passed = (len(rows) == 26 and all(r["matches_expected"] for r in rows) and unchanged and identity
              and exit_code == 0 and not forced_kill and error is None)
    private = {"schema": "isolated-server-http-private-v1", "frames": client.frames,
               "fixture_inventory": before, "fixture_info": info, "invented_only": True}
    raw = canonical(private)
    (receipts / "wire.private.json").write_bytes(raw)
    report = {"schema": "isolated-server-http-result-v1", "cases": rows, "expected_results": sum(
        r["matches_expected"] for r in rows), "case_count": len(rows), "qualified_metadata_HTTP": passed,
        "fixture_inventory_unchanged": unchanged, "observed_child_executable_matches_binary": identity,
        "binary_sha256": BINARY_SHA256, "version_label": VERSION, "startup_probe_attempts": ready_attempts,
        "successful_startup_probe_responses": sum(f["id"] == "startup" for f in client.frames),
        "exact_wire_receipt_sha256": digest(raw), "child_exit_code": exit_code, "forced_kill": forced_kill,
        "error": error, "request_inventory": [{k: f[k] for k in ("id", "method", "path", "status",
        "request_sha256", "response_sha256")} for f in client.frames], "private_case_inputs": False,
        "provider_credentials_used": False, "completion_requests": 0, "native_inference_qualified": False,
        "executed_weights_qualified": False, "installed_backend_qualified": False,
        "full_artifact_store_qualified": False, "production_activation": False,
        "owner_review_completed": False, "independent_trust_confirmed": False}
    (receipts / "report.json").write_bytes(canonical(report))
    return report


def _qualify_report(report, wire):
    """Recheck exact synthetic wire evidence; never confer native/installed trust."""
    spec, build = cases(), build_definition()
    if (not isinstance(wire, bytes) or len(wire) > 32 * MAX_REPLY
            or digest(wire) != report.get("exact_wire_receipt_sha256")):
        raise QualificationRejected("Wire receipt mismatch")
    private = strict_json(wire)
    frames, info = private["frames"], private["fixture_info"]
    if (private.get("invented_only") is not True
            or digest(canonical(private["fixture_inventory"])) != build["fixture_inventory_sha256"]
            or digest(canonical(info)) != private["fixture_inventory"]["fixture.json"]["sha256"]):
        raise QualificationRejected("Fixture binding mismatch")
    if (report.get("case_count") != 26 or report.get("expected_results") != 26
            or report.get("binary_sha256") != BINARY_SHA256 or report.get("version_label") != VERSION
            or build["binary_sha256"] != BINARY_SHA256 or report.get("child_exit_code") != 0
            or report.get("error") is not None):
        raise QualificationRejected("Incomplete or wrong build result")
    if any(report.get(k) is not True for k in ("qualified_metadata_HTTP", "fixture_inventory_unchanged",
                                             "observed_child_executable_matches_binary")):
        raise QualificationRejected("Qualification gate failed")
    if any(report.get(k) is not False for k in ("forced_kill", "private_case_inputs", "provider_credentials_used",
            "native_inference_qualified", "executed_weights_qualified", "installed_backend_qualified",
            "full_artifact_store_qualified", "production_activation", "owner_review_completed",
            "independent_trust_confirmed")) or report.get("completion_requests") != 0:
        raise QualificationRejected("Invalid qualification scope")
    startup = [f for f in frames if f["id"] == "startup"]
    if (not 1 <= len(startup) <= report["startup_probe_attempts"] <= 100
            or len(startup) != report["successful_startup_probe_responses"]
            or frames[:len(startup)] != startup or len(frames) != len(startup) + 26):
        raise QualificationRejected("Unexpected request inventory")
    reference, projections = None, []
    for frame in startup:
        if (frame["method"], frame["path"]) != ("GET", "/api/version"):
            raise QualificationRejected("Invalid startup request")
    for index, frame in enumerate(frames):
        request = base64.b64decode(frame["request_base64"], validate=True)
        response = base64.b64decode(frame["response_base64"], validate=True)
        if (len(request) > 2048 or len(response) > MAX_REPLY or digest(request) != frame["request_sha256"]
                or digest(response) != frame["response_sha256"]):
            raise QualificationRejected("Exact wire hash mismatch")
        if index < len(startup):
            if request or frame["status"] != 200 or strict_json(response).get("version") != VERSION:
                raise QualificationRejected("Invalid startup response")
        else:
            case = spec["cases"][index - len(startup)]
            if ((frame["id"], frame["method"], frame["path"]) !=
                    (case["id"], case["method"], case["path"]) or request != payload(case["fixture"], info)):
                raise QualificationRejected("Case/request binding mismatch")
            passed, reference = validate_case(case, frame, response, info, spec["comparison_fields"], reference)
            if not passed:
                raise QualificationRejected("HTTP case failed")
            projections.append({"id": case["id"], "fixture": case["fixture"], "status": frame["status"],
                "expected_status": case["expected_status"], "matches_expected": True,
                "request_sha256": frame["request_sha256"], "response_sha256": frame["response_sha256"]})
    if projections != report["cases"] or report["request_inventory"] != [
        {k: f[k] for k in ("id", "method", "path", "status", "request_sha256", "response_sha256")} for f in frames
    ]:
        raise QualificationRejected("Public projection mismatch")
    return {"metadata_HTTP_cases": 26, "exact_wire_binding": True, "binary_sha256": BINARY_SHA256,
            "installed_backend_qualified": False, "completion_or_executed_weights_qualified": False,
            "full_artifact_store_qualified": False, "production_activation": False,
            "owner_review_completed": False, "independent_trust_confirmed": False}


def qualify_report(report, wire):
    try:
        return _qualify_report(report, wire)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        raise QualificationRejected("Invalid or unqualified HTTP evidence") from exc


if __name__ == "__main__":
    os.umask(0o077)
    try:
        result = run_campaign()
        print(json.dumps({k: result[k] for k in ("case_count", "expected_results", "qualified_metadata_HTTP",
              "fixture_inventory_unchanged", "observed_child_executable_matches_binary", "child_exit_code", "error")}))
        raise SystemExit(0 if result["qualified_metadata_HTTP"] else 1)
    except (ValueError, OSError, KeyError, TypeError):
        raise SystemExit("Isolated qualification unavailable; no runtime diagnostics emitted.")
