"""Closed frozen native failure matrix; process crash is not power-loss proof."""

from controller_stage_manifest import hex_digest

CASES = [
    ("F01_seed", 200, "retained", 2),
    ("F02_read_revoked", 403, "denied", 1),
    ("F03_read_reauthorized", 200, "pending_anchors", 2),
    ("F04_retain_revoked", 403, "denied", 2),
    ("F05_retain_reauthorized", 200, "retained", 2),
    ("F06_ack_revoked", 403, "denied", 2),
    ("F07_ack_reauthorized", 200, "pending_anchors", 2),
    ("F08_before_link", None, "connection_closed", 2),
    ("F09_before_link_restart", 503, "unavailable", 0),
    ("F10_before_link_retry", 200, "retained", 2),
    ("F11_after_link", None, "connection_closed", 2),
    ("F12_after_link_restart", 409, "unverifiable", 0),
    ("F13_after_link_retry", 409, "conflict", 2),
    ("F14_after_sync", None, "connection_closed", 2),
    ("F15_after_sync_restart", 200, "pending_anchors", 2),
    ("F16_after_sync_retry", 409, "conflict", 2),
    ("F17_original", 200, "pending_anchors", 2),
]
TRUE = {"actual_app_auth_used", "disposable_identities_only", "read_only_package_inventory_exact",
        "all_expected_process_exits_verified"}
FALSE = {"private_case_inputs", "live_provider_requests", "native_inference_calls", "real_trust_enrolled",
         "runtime_installation", "production_activation", "power_loss_qualified", "automatic_orphan_repair"}
COUNTS = {"distinct_processes": 15, "loopback_servers": 15, "intentional_SIGKILL_exits": 3,
          "fresh_receipt_sessions": 3, "clean_receipt_worker_exits": 10, "receipt_HTTP_attempts": 17,
          "controller_reads": 29, "orphan_entries_preserved": 2}
PRESERVED = {"source_ciphertext_and_four_histories_exact", "no_failed_response_metadata", "same_binding_restarts", "create_only_recovery"}


def validate(value, receipt_manifest, controller_manifest):
    fields = {"schema", "receipt_manifest_sha256", "controller_manifest_sha256", "modes", "filesystem",
              "key_custody", "operator_appointments", *TRUE, *FALSE}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "native-receipt-fault-v1"
            or value["receipt_manifest_sha256"] != hex_digest(receipt_manifest)
            or value["controller_manifest_sha256"] != hex_digest(controller_manifest) or value["filesystem"] != "ext4"
            or any(value[k] is not True for k in TRUE)
            or any(type(value[k]) is not int or value[k] != 0 for k in ("live_provider_requests", "native_inference_calls"))
            or any(value[k] is not False for k in FALSE - {"live_provider_requests", "native_inference_calls"})
            or value["key_custody"] != "unassessed" or value["operator_appointments"] != "unassessed"
            or not isinstance(value["modes"], list) or len(value["modes"]) != 2):
        raise ValueError("Native fault scope rejected")
    for mode, expected in zip(value["modes"], ("retirement", "rollback"), strict=True):
        if (not isinstance(mode, dict) or set(mode) != {"mode", "cases", "campaign_controller_requests", *COUNTS, *PRESERVED}
                or mode["mode"] != expected or any(mode[k] is not True for k in PRESERVED)
                or any(type(mode[k]) is not int or mode[k] != v for k, v in COUNTS.items())
                or type(mode["campaign_controller_requests"]) is not int
                or mode["campaign_controller_requests"] != (48 if expected == "retirement" else 66)
                or not isinstance(mode["cases"], list) or len(mode["cases"]) != len(CASES)):
            raise ValueError("Native fault process evidence rejected")
        for row, (ident, status, state, reads) in zip(mode["cases"], CASES, strict=True):
            if (not isinstance(row, dict) or set(row) != {"id", "status", "state", "controller_reads"}
                    or row["id"] != ident or row["status"] != status
                    or (status is not None and type(row["status"]) is not int)
                    or row["state"] != state or type(row["controller_reads"]) is not int or row["controller_reads"] != reads):
                raise ValueError("Frozen native failure outcome rejected")
    return {"qualified_modes": 2, "frozen_HTTP_cases": 34, "intentional_SIGKILL_exits": 6, "production_activation": False}
