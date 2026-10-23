"""Disposable metadata-only comparison. Never a route change or inference grant."""
import os
import re
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace

from metadata_phase_probe import FIELDS, probe

RECIPE = "readonly-origin-route-comparison-v1"
PHASES = {"configuration", "tcp_connect", "tls_handshake", "request_send", "response_headers", "response_body", "metadata_validation"}
ERRORS = {None, "socket_timeout", "tls_error", "provider_connection_closed", "provider_connection_refused",
          "provider_network_unreachable", "provider_connection_reset", "provider_network_denied",
          "provider_transport_resource_exhausted", "provider_upstream_transport_failed", "http_protocol_error", "configuration_rejected",
          "route_rejected", "tls_policy_rejected", "connection_replay_rejected", "response_socket_unavailable",
          "invalid_http_status", "http_status_rejected", "encoding_rejected", "body_budget_exceeded", "incomplete_body",
          "invalid_metadata", "model_unresolved", "local_metadata_rejected", "invalid_input_or_metadata",
          "unclassified_rejection", "cleanup_failed"}


def origin_owner(engine_root, *, runner=subprocess.run):
    """Bounded host inspection, no HTTP. Exact loopback listener, UID, cwd and argv.

    This identifies the current local process, not the bytes loaded by a running
    interpreter. No commands, paths, PID or exception text leave the function.
    """
    try:
        root = Path(engine_root).resolve(strict=True)
        if not (root / "src/inference_engine/main.py").is_file():
            return False

        def read(args):
            result = runner(args, capture_output=True, timeout=2, check=True)
            if len(result.stdout) > 65536:
                raise ValueError("bounded ownership output required")
            return result.stdout.decode()

        lines = read(["/usr/sbin/lsof", "-nP", "-iTCP:8080", "-sTCP:LISTEN", "-Fpn"]).splitlines()
        pids = {line[1:] for line in lines if line.startswith("p")}
        names = {line[1:] for line in lines if line.startswith("n")}
        if len(pids) != 1 or names != {"127.0.0.1:8080"}:
            return False
        pid = next(iter(pids))
        if not re.fullmatch(r"[1-9][0-9]{0,9}", pid):
            return False
        uid, command = read(["/bin/ps", "-p", pid, "-o", "uid=,command="]).strip().split(None, 1)
        argv = shlex.split(command)
        expected = ["-m", "uvicorn", "inference_engine.main:app", "--host", "127.0.0.1", "--port", "8080"]
        if (int(uid) != os.getuid() or argv[1:] != expected
                or Path(argv[0]).resolve(strict=True) != (root / ".venv/bin/python").resolve(strict=True)):
            return False
        cwd = read(["/usr/sbin/lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"]).splitlines()
        return {line[1:] for line in cwd if line.startswith("n")} == {str(root)}
    except Exception:  # noqa: BLE001 - ownership failure must never reveal private process information
        return False


def local_observation(binding, relay, engine_root, *, verifier=origin_owner, **probe_options):
    """One GET to fixed host loopback after ownership verification. No TLS bypass.

    Loopback plaintext is an explicit host-only diagnostic, never a private-relay
    target or a change to the approved HTTPS route. Shared probe is unchanged.
    """
    result = {"context": "host_loopback_origin", "owner_verified": False, "diagnostic": None}
    if (not isinstance(binding, dict) or set(binding) != FIELDS
            or verifier(engine_root) is not True):
        return result
    result["owner_verified"] = True
    local = dict(binding, transport_mode="native_private", approved_hostname=None, route_sha256=None)
    facade = SimpleNamespace(configured_upstream=lambda _: SimpleNamespace(address="127.0.0.1", port=8080, hostname=None),
                             transport_failure=relay.transport_failure)
    result["diagnostic"] = probe(local, facade, {}, **probe_options)
    return result


def safe_diagnostic(value):
    """Validate and project finite, non-identifying fields; do not copy raw input."""
    if not isinstance(value, dict):
        raise ValueError("diagnostic required")
    phase, error, outcome = value.get("last_phase"), value.get("error"), value.get("outcome")
    if phase not in PHASES or error not in ERRORS or outcome not in {"rejected", "timeout", "metadata_accepted_identity_unqualified"}:
        raise ValueError("diagnostic vocabulary rejected")
    for key in ("connection_attempts", "metadata_GET_attempts"):
        if type(value.get(key)) is not int or value[key] not in (0, 1):
            raise ValueError("bounded count required")
    if (type(value.get("completion_POST_requests")) is not int or value["completion_POST_requests"] != 0
            or value.get("qualified_identity") is not False or value.get("native_execution_authorization") is not False
            or value.get("production_activation") is not False or value.get("budget_seconds") != 4):
        raise ValueError("metadata-only boundary required")
    status = value.get("http_status")
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        raise ValueError("HTTP status rejected")
    for key in ("metadata_accepted", "tls_verified", "cleanup_complete", "deadline_reached"):
        if type(value.get(key)) is not bool:
            raise ValueError("boolean required")
    if value.get("tls_required") is not None and type(value["tls_required"]) is not bool:
        raise ValueError("TLS flag rejected")
    if (value["metadata_GET_attempts"] > value["connection_attempts"]
            or (status is not None and value["metadata_GET_attempts"] != 1)
            or (value["tls_verified"] and value["tls_required"] is not True)
            or (value["connection_attempts"] and value["tls_required"] is None)):
        raise ValueError("inconsistent transport observation")
    accepted = value["metadata_accepted"]
    if accepted != (outcome == "metadata_accepted_identity_unqualified") or (accepted and (
            status != 200 or error is not None or phase != "metadata_validation" or not value["cleanup_complete"]
            or value["connection_attempts"] != 1 or value["metadata_GET_attempts"] != 1)):
        raise ValueError("inconsistent acceptance")
    return {key: value[key] for key in ("last_phase", "outcome", "error", "http_status", "connection_attempts",
            "metadata_GET_attempts", "completion_POST_requests", "metadata_accepted", "tls_required", "tls_verified",
            "cleanup_complete", "deadline_reached")}


def compare(local, approved_route):
    """Sequential path observations, not simultaneous or proof of component fault."""
    if (not isinstance(local, dict) or local.get("context") != "host_loopback_origin"
            or type(local.get("owner_verified")) is not bool):
        raise ValueError("origin context rejected")
    left = safe_diagnostic(local["diagnostic"]) if local["owner_verified"] else None
    if not local["owner_verified"] and local.get("diagnostic") is not None:
        raise ValueError("unverified origin observation rejected")
    right = safe_diagnostic(approved_route)
    if left and left["tls_required"] is not False:
        raise ValueError("loopback context rejected")
    if right["connection_attempts"] and (right["tls_required"] is not True or (
            right["metadata_GET_attempts"] and not right["tls_verified"])):
        raise ValueError("approved HTTPS context required")
    a, b = bool(left and left["metadata_accepted"]), right["metadata_accepted"]
    classification = ("origin_unobserved" if left is None else "both_metadata_accepted" if a and b
                      else "origin_only_metadata_accepted" if a else "route_only_metadata_accepted" if b
                      else "neither_metadata_accepted")
    return {"recipe": RECIPE, "classification": classification, "local_origin": left, "approved_route": right,
            "origin_owner_verified": local["owner_verified"], "observations_sequential": True,
            "network_budget_seconds_per_observation": 4, "aggregate_connection_attempts": (left or {}).get("connection_attempts", 0) + right["connection_attempts"],
            "aggregate_metadata_GET_attempts": (left or {}).get("metadata_GET_attempts", 0) + right["metadata_GET_attempts"],
            "completion_POST_requests": 0, "qualified_identity": False, "native_execution_authorization": False,
            "production_activation": False, "historical_timeout_cause_established": False,
            "responsible_component_identified": False, "serving_request_trace": False}
