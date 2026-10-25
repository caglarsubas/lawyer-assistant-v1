"""Replay retained invented qualification evidence, never grant runtime authority."""

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from portable_controller_fixture import CASES, ISSUER, POLICY, encode, sha
from signed_provider_contract import ResponseChallenge


def grade(report):
    if (report["schema"] != "portable-controller-native-v1" or len(report["cases"]) != len(CASES)
            or report["actual_loopback_servers"] != 2 or report["actual_HTTP_requests"] != 5
            or report["read_only_model_inventory_exact"] is not True
            or any(report[n] is not False for n in ("application_or_engine_imports", "real_trust_confirmed", "private_case_inputs", "production_activation"))
            or report["native_inference_calls"] != 0 or report["live_provider_requests"] != 0
            or report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none",
                                    "process_environment_cleared": True, "single_attempt": True}
            or set(report["preparation"]["filesystems"].values()) != {"ext4"}
            or report["preparation"]["tensor_count"] != 0 or report["preparation"]["private_inputs"] is not False):
        raise ValueError("Portable qualification posture rejected")
    candidate = report["candidate"]
    if candidate["single_attempt"] is not True or candidate["new_volumes_only"] is not True or candidate["real_credentials_or_inputs"] is not False or candidate["production_activation"] is not False:
        raise ValueError("Frozen candidate boundary rejected")
    if report["policy_sha256"] != sha(encode(POLICY)):
        raise ValueError("Frozen expectations differ")
    for row, (name, expected) in zip(report["cases"], CASES, strict=True):
        if row["id"] != name or row["status"] != expected:
            raise ValueError("Fresh portable case failed")
        if name in {"A27_HTTP", "A28_receipt_rollback"}:
            if row["HTTP_requests"] != (2 if name == "A27_HTTP" else 3) or row["simulated_backend_sends"] != 1 or row["nonce_counts"] != {"consumed": 1}:
                raise ValueError("Portable effect/replay binding failed")
            f = row["frame"]
            key = Ed25519PublicKey.from_public_bytes(base64.b64decode(f["public_key_base64"], validate=True))
            raw = base64.b64decode(f["request_base64"], validate=True)
            if not raw.endswith(b" \n"):
                raise ValueError("Exact original request lost")
            pending = ResponseChallenge(raw, f["identity_proof"], trusted_key=key, issuer_key_id=ISSUER,
                                        expected_pin=f["pin"], identity_nonce=f["identity_nonce"], now=f["now"], challenge=f["response_nonce"])
            pending.consume(base64.b64decode(f["response_envelope_base64"], validate=True), now=f["now"])
        elif row["HTTP_requests"] != 0 or row["simulated_backend_sends"] != 0:
            raise ValueError("Read-only case dispatched work")
        if "gates" in row:
            if set(row["gates"]) != {"package", "dependencies", "binding", "model", "enrollment"}:
                raise ValueError("Incomplete readiness evidence")
            if row["read_only_state_exact"] is not (name != "A25_revoked_during_check") or row["external_revocation_injected"] is not (name == "A25_revoked_during_check"):
                raise ValueError("Read-only state preservation failed")
            if name in {"A11_ready", "A26_no_privileged_helpers"} and set(row["gates"].values()) != {"verified"}:
                raise ValueError("Positive readiness gates incomplete")
    return {"cases_passed": len(CASES), "package_modules": 14, "actual_loopback_servers": 2, "actual_HTTP_requests": 5,
            "portable_signed_responses_verified_by_retained_consumer": 2, "read_only_inventory_exact": True,
            "real_trust_confirmed": False, "runtime_installation": False, "native_execution_qualified": False, "legal_qualification": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(grade(json.loads((root / "deploy/fixtures/portable_controller_first_report.json").read_text()))))
