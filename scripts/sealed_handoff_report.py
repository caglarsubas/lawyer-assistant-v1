"""Replay disposable evidence without admitting a volume or provisioning trust."""

import json

import artifact_store as a
import sealed_handoff_qualification as q
import sealed_relay_handoff as relay
import sealed_volume as v


def grade(report):
    expected = dict(q.TRANSFER_CASES + q.HANDOFF_CASES + q.LIFECYCLE_CASES)
    rows = report["cases"]
    if (report["schema"] != "sealed-volume-native-receipt-v1"
            or report["policy_sha256"] != a.digest((json.dumps(q.POLICY, indent=2) + "\n").encode())
            or len(rows) != len(expected) or len({r["id"] for r in rows}) != len(expected)
            or {r["id"]: r["expected"] for r in rows} != expected
            or any(r["observed"] != expected[r["id"]] or r.get("original_preserved", True) is not True for r in rows)
            or report["real_issuers_or_credentials"] is not False
            or type(report["inference_calls"]) is not int or report["inference_calls"] != 0
            or type(report["provider_requests"]) is not int or report["provider_requests"] != 0
            or report["production_activation"] is not False
            or report["original_nonempty_target_preserved"] is not True
            or report["control_recovery_readonly"] is not True
            or report["fresh_restore_generation"] is not True
            or report["separate_live_control_volume"] is not True):
        v.reject()
    if report["profile"] != {"filesystem": "native_ext4", "cpu": 2, "memory_mib": 768,
                             "kernel_readonly_store": True, "single_attempt": True}:
        v.reject()
    prep = report["preparation"]
    index = prep["model_index"]
    index_sha = a.digest(a.canonical(index))
    v.parse_index(a.canonical(index), index_sha)
    if (prep["bytes_written"] != q.POLICY["model_bytes"] or prep["tensor_count"] != 0
            or prep["fresh_seed"] != q.POLICY["fresh_seed"] or prep["fsynced"] is not True
            or set(prep["filesystems"].values()) != {"ext4"}):
        v.reject()
    records = []
    times = []
    for name in ("import", "restore"):
        transfer = report[name]
        sealed = report[name + "_seal"]
        record = v.validate_record(sealed["record"])
        proof = sealed["proof"]
        a.validate_proof(proof, index["manifest"], a.Budget(), strategy="windowed-pinned")
        if (transfer["record"] != record or record["purpose"] != name
                or record["bundle_index_sha256"] != index_sha
                or record["content_sha256"] != index["content_sha256"]
                or transfer["copied_bytes"] != index["total_bytes"]
                or transfer["requires_readonly_reverification"] is not True
                or transfer["production_activation"] is not False
                or proof["mapped_bytes"] != q.POLICY["model_bytes"]
                or proof["bytes_hashed"] != index["total_bytes"]
                or proof["artifacts"] != index["artifacts"]
                or sealed["native_execution_authorized"] is not False
                or sealed["production_activation"] is not False):
            v.reject()
        records.append(record)
        times.append(proof["elapsed_seconds"])
    if (records[0]["generation_id"] == records[1]["generation_id"]
            or records[0]["operation_id"] == records[1]["operation_id"]
            or records[0]["volume_binding_sha256"] == records[1]["volume_binding_sha256"]
            or records[1]["parent_operation"] != records[0]["operation_id"]):
        v.reject()
    exported = report["export"]
    if (exported["bundle_index_sha256"] != index_sha or exported["content_sha256"] != index["content_sha256"]
            or exported["copied_bytes"] != index["total_bytes"] or exported["production_activation"] is not False):
        v.reject()
    frames = report["retained_frames"]
    if len(frames) != 3 or [frames[i]["record"] for i in (0, 2)] != records:
        v.reject()
    for frame in frames:
        v.validate_record(frame["record"])
        q.verify_retained(relay.unb64(frame["wire_base64"]), frame["context"], frame["record"], wire_sha256=frame["wire_sha256"])
    return {"native_cases": len(rows), "expected_rejections": sum(r["observed"] == "rejected" for r in rows),
            "signature_report_replays": 3, "import_seal_seconds": times[0], "restore_seal_seconds": times[1],
            "fresh_restore_generation": True, "exact_artifact_bytes_per_copy": index["total_bytes"],
            "metadata_handoff_only": True, "native_execution_authorized": False, "production_activation": False}
