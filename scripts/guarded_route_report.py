"""Retained synthetic HTTP/protocol evidence, never runtime admission or trust."""

import base64
import json

import artifact_store as a
import guarded_route_fixture as q
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from signed_provider_contract import IdentityChallenge, ResponseChallenge, encode, sha


def grade(report):
    expected = {n: (s, c) for n, s, c in q.CASES}
    rows = report["cases"]
    if (report["schema"] != "guarded-controller-native-report-v1" or len(rows) != len(expected)
            or len({r["id"] for r in rows}) != len(expected)
            or {r["id"]: (r["status"], r["simulated_backend_sends"]) for r in rows} != expected
            or report["policy_sha256"] != sha((json.dumps(q.POLICY, indent=2) + "\n").encode())
            or report["backend_transport"] != "explicit_httpx_mock_only"
            or report["read_only_model_inventory_exact"] is not True
            or report["actual_loopback_servers"] != 24 or report["actual_HTTP_requests"] != 53
            or report["actual_HTTP_requests"] != sum(r["HTTP_requests"] for r in rows)
            or report["actual_loopback_servers"] != sum(r["loopback_server"] for r in rows)
            or any(report[n] != 0 or type(report[n]) is not int for n in ("live_provider_requests", "native_inference_calls"))
            or any(report[n] is not False for n in ("runtime_keys_used", "independent_real_trust_confirmed", "private_case_inputs", "production_activation", "model_performance_retested"))):
        raise ValueError("Guarded protocol evidence rejected")
    if report["profile"] != {"filesystem": "ext4", "cpu": 2, "memory_mib": 768, "network": "none", "process_environment_cleared": True, "single_attempt": True}:
        raise ValueError("Guarded profile changed")
    proofs = set()
    for row in rows:
        proof = row["fixture_proof"]
        a.validate_proof(proof, proof["manifest_digest"], a.Budget(), strategy="windowed-pinned")
        if (proof["mapped_bytes"] != 65561 or row["privacy_sentinels_absent"] is not True
                or row["native_execution_authorized"] is not False or row["production_activation"] is not False):
            raise ValueError("Guarded scope changed")
        proofs.add(proof["content_identity_sha256"])
        if row["status"] == "setup_rejected" and (row["loopback_server"] is not False or row["HTTP_requests"] != 0):
            raise ValueError("Rejected factory served HTTP")
    if len(proofs) != 1:
        raise ValueError("Model content changed across cases")
    by_id = {r["id"]: r for r in rows}
    for name in ("G04_before_admission", "G05_after_admission", "G06_during_backend", "G07_before_complete", "G08_before_consume", "G09_before_release"):
        if by_id[name]["operation_state"] != "revoked":
            raise ValueError("Revocation not retained")
    for name, states in {"G20_commit_gap": {"reserved": 1}, "G21_lost_admission": {"consumed": 1},
                         "G22_receipt_rollback": {"consumed": 1}, "G24_concurrent": {"consumed": 1}}.items():
        if by_id[name]["nonce_counts"] != states:
            raise ValueError("Nonce history lost")
    verified = []
    for row in rows:
        frame = row["frame"]
        if row["status"] != 200:
            if frame is not None:
                raise ValueError("Unreleased signed response retained as success")
            continue
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(frame["public_key_base64"], validate=True))
        raw = base64.b64decode(frame["request_base64"], validate=True)
        identity = IdentityChallenge(key, q.ISSUER, frame["pin"], challenge=frame["identity_nonce"]).consume(encode(frame["identity_proof"]), now=frame["now"])
        consumer = ResponseChallenge(raw, identity, trusted_key=key, issuer_key_id=q.ISSUER, expected_pin=frame["pin"],
                                     identity_nonce=frame["identity_nonce"], now=frame["now"], challenge=frame["response_nonce"])
        result = consumer.consume(base64.b64decode(frame["response_envelope_base64"], validate=True), now=frame["now"])
        if sha(raw) != row["request_sha256"] or any(result[n] is not False for n in ("native_execution_authorization", "production_activation", "legal_qualification")):
            raise ValueError("Exact response binding rejected")
        if row["id"] == "G29_exact_wire" and not raw.endswith(b" \n"):
            raise ValueError("Original request bytes lost")
        verified.append(row["id"])
    if verified != ["G01_valid", "G29_exact_wire"]:
        raise ValueError("Positive response coverage changed")
    return {"native_cases": 29, "loopback_servers": 24, "actual_HTTP_requests": 53,
            "verified_signed_frames": 2, "factory_rejections": 5, "direct_hook_rejection": True,
            "read_only_model_inventory_exact": True, "mock_backend_only": True, "native_inference_qualified": False,
            "production_activation": False}
