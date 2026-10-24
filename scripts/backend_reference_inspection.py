"""Read-only loopback backend identity and reference lookup; never generation."""

import base64
import hashlib
import http.client
import json
import os
import re
import socket
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from metadata_phase_probe import strict_json

HOST, PORT, MAX_BODY = "127.0.0.1", 11434, 1024 * 1024
GET_PATHS = {"/api/version", "/api/tags", "/api/ps"}
IDENTITY_FIELDS = {
    "pid",
    "start",
    "uid",
    "binary_path",
    "binary_sha256",
    "binary_bytes",
    "binary_mtime_ns",
    "binary_inode",
    "loopback_only",
}


class InspectionRejected(ValueError):
    pass


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def model_label(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value)
        or "://" in value
        or value.count(":") > 1
        or value.lower().endswith((":cloud", "-cloud"))
    ):
        raise InspectionRejected("invalid_model_label")
    return value


def digest(value):
    if isinstance(value, str) and value.startswith("sha256:"):
        value = value[7:]
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise InspectionRejected("invalid_manifest_digest")
    return value


@dataclass(frozen=True)
class Reply:
    status: int
    headers: tuple
    body: bytes


def parsed(reply):
    if (
        type(reply) is not Reply
        or type(reply.status) is not int
        or not 100 <= reply.status <= 599
    ):
        raise InspectionRejected("invalid_metadata_reply")
    if not isinstance(reply.body, bytes) or not 0 < len(reply.body) <= MAX_BODY:
        raise InspectionRejected("metadata_body_budget")
    headers = [(k.lower(), v) for k, v in reply.headers]
    types = [v.lower().split(";")[0].strip() for k, v in headers if k == "content-type"]
    encodings = [v.lower() for k, v in headers if k == "content-encoding"]
    if types != ["application/json"] or encodings not in ([], ["identity"]):
        raise InspectionRejected("metadata_headers_rejected")
    return strict_json(reply.body) if reply.status == 200 else None


class ReadOnlyBackendHTTP:
    """One direct connection per allowed metadata request. No proxies or retries."""

    def __init__(self, *, clock=time.monotonic, connection_factory=None):
        self.clock, self.connection_factory = clock, connection_factory

    def exchange(self, method, path, body):
        if method == "GET":
            if path not in GET_PATHS or body is not None:
                raise InspectionRejected("request_not_read_only")
        elif method == "POST" and path == "/api/show":
            value = strict_json(body)
            if (
                not isinstance(value, dict)
                or set(value) != {"model", "verbose"}
                or value["verbose"] is not False
            ):
                raise InspectionRejected("request_not_read_only")
            model_label(value["model"])
        else:
            raise InspectionRejected("request_not_read_only")
        deadline = self.clock() + 4

        def remaining():
            left = deadline - self.clock()
            if left <= 0:
                raise TimeoutError()
            return left

        class OneConnection(http.client.HTTPConnection):
            attempted = False

            def connect(inner):
                if inner.attempted or inner._tunnel_host:
                    raise InspectionRejected("metadata_reconnect_rejected")
                inner.attempted = True
                raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    raw.settimeout(remaining())
                    raw.connect((HOST, PORT))
                    inner.sock = raw
                except BaseException:
                    raw.close()
                    raise

            def send(inner, data):
                if inner.sock is None:
                    raise InspectionRejected("metadata_reconnect_rejected")
                inner.sock.settimeout(remaining())
                super().send(data)

        factory = self.connection_factory or OneConnection
        connection = factory(HOST, PORT, timeout=remaining())
        response = None
        try:
            connection.connect()
            connection.request(
                method,
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            connection.sock.settimeout(remaining())
            response = connection.getresponse()
            chunks, length = [], 0
            while True:
                if response.isclosed():
                    if response.length not in (None, 0):
                        raise InspectionRejected("incomplete_metadata_body")
                    break
                sock = connection.sock or getattr(
                    getattr(getattr(response, "fp", None), "raw", None), "_sock", None
                )
                if sock is None:
                    raise InspectionRejected("metadata_socket_unavailable")
                sock.settimeout(remaining())
                chunk = response.read1(65536)
                remaining()
                length += len(chunk)
                if length > MAX_BODY:
                    raise InspectionRejected("metadata_body_budget")
                chunks.append(chunk)
                if not chunk:
                    if response.length not in (None, 0):
                        raise InspectionRejected("incomplete_metadata_body")
                    break
            return Reply(
                response.status, tuple(response.getheaders()), b"".join(chunks)
            )
        finally:
            if response is not None:
                response.close()
            connection.close()


def binary_fingerprint(path, *, clock=time.monotonic):
    path = Path(path).resolve(strict=True)
    if path.name.lower() != "ollama":
        raise InspectionRejected("unexpected_backend_executable")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    deadline = clock() + 6
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in {0, os.getuid()}
            or not info.st_mode & 0o111
            or not 0 < info.st_size <= 1024**3
        ):
            raise InspectionRejected("backend_executable_rejected")
        h, size = hashlib.sha256(), 0
        while chunk := stream.read(1024 * 1024):
            if clock() > deadline:
                raise InspectionRejected("backend_hash_budget")
            size += len(chunk)
            if size > info.st_size:
                raise InspectionRejected("backend_executable_changed")
            h.update(chunk)
        after = os.fstat(stream.fileno())
        if size != info.st_size or (info.st_ino, info.st_size, info.st_mtime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise InspectionRejected("backend_executable_changed")
    return {
        "binary_path": str(path),
        "binary_sha256": h.hexdigest(),
        "binary_bytes": size,
        "binary_inode": info.st_ino,
        "binary_mtime_ns": info.st_mtime_ns,
    }


def observe_listener():
    """macOS operator evidence, not loaded-code or remote signed attestation.

    Read only command name/start/UID; never process arguments or environment.
    All paths, PID and raw process evidence belong only in the private receipt.
    """
    if sys.platform != "darwin":
        return None

    def run(args):
        p = subprocess.run(args, capture_output=True, text=True, timeout=3)
        if p.returncode:
            raise InspectionRejected("backend_process_unavailable")
        return p.stdout.strip()

    try:
        rows = run(
            ["/usr/sbin/lsof", "-nP", "-iTCP:11434", "-sTCP:LISTEN", "-Fpn"]
        ).splitlines()
        pids = {v[1:] for v in rows if v.startswith("p")}
        addresses = {v[1:] for v in rows if v.startswith("n")}
        if (
            len(pids) != 1
            or not addresses
            or not all(v in {"127.0.0.1:11434", "[::1]:11434"} for v in addresses)
        ):
            raise InspectionRejected("backend_listener_ambiguous")
        pid = int(next(iter(pids)))
        uid = int(run(["/bin/ps", "-p", str(pid), "-o", "uid="]))
        start = run(["/bin/ps", "-p", str(pid), "-o", "lstart="])
        path = run(["/bin/ps", "-p", str(pid), "-o", "comm="])
        value = {
            "pid": pid,
            "uid": uid,
            "start": start,
            "loopback_only": True,
            **binary_fingerprint(path),
        }
        if run(["/bin/ps", "-p", str(pid), "-o", "lstart="]) != start:
            raise InspectionRejected("backend_process_changed")
        return value
    except Exception:
        return None  # Never emit subprocess errors, paths or process content.


def identity_valid(value):
    return (
        isinstance(value, dict)
        and set(value) == IDENTITY_FIELDS
        and type(value["pid"]) is int
        and value["pid"] > 0
        and type(value["uid"]) is int
        and value["uid"] >= 0
        and isinstance(value["start"], str)
        and 0 < len(value["start"]) <= 100
        and isinstance(value["binary_path"], str)
        and Path(value["binary_path"]).is_absolute()
        and isinstance(value["binary_sha256"], str)
        and re.fullmatch("[0-9a-f]{64}", value["binary_sha256"]) is not None
        and type(value["binary_bytes"]) is int
        and 0 < value["binary_bytes"] <= 1024**3
        and type(value["binary_mtime_ns"]) is int
        and value["binary_mtime_ns"] >= 0
        and type(value["binary_inode"]) is int
        and value["binary_inode"] > 0
        and value["loopback_only"] is True
    )


def selected_digest(payload, model):
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) > 4096:
        raise InspectionRejected("model_inventory_rejected")
    chosen = [
        v
        for v in rows
        if isinstance(v, dict) and model in (v.get("name"), v.get("model"))
    ]
    if len(chosen) != 1:
        raise InspectionRejected("selected_model_ambiguous")
    row = chosen[0]
    if (
        row.get("name") != row.get("model")
        or not isinstance(row.get("details"), dict)
        or row["details"].get("format") != "gguf"
        or row.get("remote_host")
        or row.get("remote_model")
    ):
        raise InspectionRejected("selected_model_not_local_gguf")
    return digest(row.get("digest"))


def running_hash(payload):
    rows = payload.get("models") if isinstance(payload, dict) else None
    if (
        not isinstance(rows, list)
        or len(rows) > 4096
        or any(not isinstance(v, dict) for v in rows)
    ):
        raise InspectionRejected("running_inventory_rejected")
    # Expiry timestamps advance independently; retain full raw evidence privately.
    stable = [{k: v for k, v in row.items() if k != "expires_at"} for row in rows]
    return sha(canonical(sorted(stable, key=lambda v: canonical(v))))


def show_hash(payload):
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("details"), dict)
        or payload["details"].get("format") != "gguf"
        or not isinstance(payload.get("model_info"), dict)
        or not isinstance(payload.get("capabilities"), list)
        or "completion" not in payload["capabilities"]
        or any(not isinstance(v, str) or len(v) > 64 for v in payload["capabilities"])
        or payload.get("remote_host")
        or payload.get("remote_model")
    ):
        raise InspectionRejected("model_details_rejected")
    return sha(canonical({k: v for k, v in payload.items() if k != "modified_at"}))


def inspect_backend(model, *, exchange, observer=observe_listener):
    """Return separate public projection and confidential raw receipt; no writes."""
    model_label(model)
    report = {
        "schema": "readonly-backend-reference-v1",
        "model_id_sha256": sha(model.encode()),
        "classification": "metadata_unmeasured",
        "reported_version": None,
        "manifest_digest_sha256": None,
        "backend_identity_observed": False,
        "backend_identity_stable": False,
        "binary_sha256": None,
        "reference_lookup_resolved": None,
        "named_reference_metadata_equal": None,
        "running_inventory_stable": None,
        "metadata_requests": [],
        "show_comparison_excludes": ["modified_at"],
        "running_comparison_excludes": ["expires_at"],
        "error": None,
        "generation_requests": 0,
        "native_inference_calls": 0,
        "signed_identity_qualified": False,
        "executed_weights_qualified": False,
        "native_execution_compatibility": "not_tested",
        "native_admission": False,
        "production_activation": False,
    }

    def observe():
        try:
            return observer()
        except Exception:
            return None

    private = {"before": observe(), "after": None, "frames": []}

    def get(method, path, value=None):
        body = canonical(value) if value is not None else None
        row = {"method": method, "path": path, "status": None}
        report["metadata_requests"].append(row)
        reply = exchange(method, path, body)
        private["frames"].append(
            {
                **row,
                "status": reply.status,
                "request_sha256": sha(body or b""),
                "body_sha256": sha(reply.body),
                "body_base64": base64.b64encode(reply.body).decode(),
            }
        )
        row.update(status=reply.status, body_sha256=sha(reply.body))
        return reply.status, parsed(reply)

    try:
        status, version = get("GET", "/api/version")
        if (
            status != 200
            or not isinstance(version, dict)
            or set(version) != {"version"}
            or not isinstance(version["version"], str)
            or not re.fullmatch(
                r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9_.-]+)?", version["version"]
            )
        ):
            raise InspectionRejected("backend_version_rejected")
        report["reported_version"] = version["version"]
        status, tags = get("GET", "/api/tags")
        if status != 200:
            raise InspectionRejected("model_inventory_unavailable")
        selected = selected_digest(tags, model)
        report["manifest_digest_sha256"] = selected
        status, before = get("GET", "/api/ps")
        if status != 200:
            raise InspectionRejected("running_inventory_unavailable")
        before_hash = running_hash(before)
        named_status, named = get(
            "POST", "/api/show", {"model": model, "verbose": False}
        )
        ref_status, reference = get(
            "POST", "/api/show", {"model": "sha256:" + selected, "verbose": False}
        )
        status, after_tags = get("GET", "/api/tags")
        if status != 200:
            raise InspectionRejected("model_inventory_unavailable")
        after_selected = selected_digest(after_tags, model)
        status, after = get("GET", "/api/ps")
        if status != 200:
            raise InspectionRejected("running_inventory_unavailable")
        report["running_inventory_stable"] = before_hash == running_hash(after)
        if after_selected != selected or not report["running_inventory_stable"]:
            report["classification"] = "observation_changed"
        elif named_status == 200 and ref_status in {400, 404}:
            show_hash(named)
            report.update(
                classification="lookup_rejected", reference_lookup_resolved=False
            )
        elif named_status == ref_status == 200:
            equal = show_hash(named) == show_hash(reference)
            report.update(
                classification="lookup_resolved" if equal else "metadata_mismatch",
                reference_lookup_resolved=True,
                named_reference_metadata_equal=equal,
            )
    except InspectionRejected as error:
        allowed = {
            "invalid_model_label",
            "invalid_manifest_digest",
            "invalid_metadata_reply",
            "metadata_body_budget",
            "metadata_headers_rejected",
            "backend_version_rejected",
            "model_inventory_rejected",
            "selected_model_ambiguous",
            "selected_model_not_local_gguf",
            "running_inventory_rejected",
            "model_details_rejected",
            "model_inventory_unavailable",
            "running_inventory_unavailable",
            "request_not_read_only",
            "metadata_reconnect_rejected",
            "incomplete_metadata_body",
            "metadata_socket_unavailable",
        }
        report["error"] = (
            str(error) if str(error) in allowed else "backend_metadata_unavailable"
        )
    except Exception:
        report["error"] = "backend_metadata_unavailable"
    finally:
        private["after"] = observe()
    valid = identity_valid(private["before"]) and identity_valid(private["after"])
    report["backend_identity_observed"] = bool(valid)
    report["backend_identity_stable"] = bool(
        valid and private["before"] == private["after"]
    )
    if valid:
        report["binary_sha256"] = private["before"]["binary_sha256"]
    if valid and not report["backend_identity_stable"]:
        report["classification"] = "observation_changed"
    elif not valid:
        report["classification"] = "metadata_unmeasured"
    return report, private
