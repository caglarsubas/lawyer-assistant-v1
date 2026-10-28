"""Frozen native HTTP protocol; package consistency does not grant real authority."""

from controller_stage_manifest import hex_digest

CASES = [("H01_readiness", 200, "ready_for_disposable_validation", None), ("H02_retain", 200, "retained", None),
         ("H03_reobserve", 200, "pending_anchors", "unchanged_metadata"), ("H04_cookie", 403, "denied", None),
         ("H05_origin", 403, "denied", None), ("H06_csrf", 400, "unavailable", None),
         ("H07_role", 403, "denied", None), ("H08_query", 400, "unavailable", None),
         ("H09_source_pin", 404, "unavailable", None), ("H10_record_pin", 409, "unverifiable", None),
         ("H11_restart", 200, "pending_anchors", "unchanged_metadata"),
         ("H12_destination", 200, "pending_anchors", "changed_metadata"),
         ("H13_window", 200, "reconciled_metadata", "changed_metadata"),
         ("H14_source_changed", 200, "source_changed", "changed_metadata"), ("H15_revocation", 403, "denied", None)]
TRUE = {"actual_app_auth_used", "disposable_identities_only", "read_only_package_inventory_exact", "all_processes_exited_cleanly"}
FALSE = {"private_case_inputs", "live_provider_requests", "native_inference_calls", "real_trust_enrolled", "runtime_installation", "production_activation"}


def validate(value, receipt_manifest, controller_manifest):
    keys = {"schema", "receipt_manifest_sha256", "controller_manifest_sha256", "modes", "filesystem", "key_custody",
            "operator_appointments", *TRUE, *FALSE}
    if (not isinstance(value, dict) or set(value) != keys or value["schema"] != "native-receipt-http-v1"
            or value["receipt_manifest_sha256"] != hex_digest(receipt_manifest)
            or value["controller_manifest_sha256"] != hex_digest(controller_manifest) or value["filesystem"] != "ext4"
            or any(value[k] is not True for k in TRUE)
            or any(type(value[k]) is not int or value[k] != 0 for k in ("live_provider_requests", "native_inference_calls"))
            or any(value[k] is not False for k in FALSE - {"live_provider_requests", "native_inference_calls"})
            or value["key_custody"] != "unassessed" or value["operator_appointments"] != "unassessed"
            or not isinstance(value["modes"], list) or len(value["modes"]) != 2):
        raise ValueError("Native receipt HTTP scope rejected")
    for mode, expected in zip(value["modes"], ("retirement", "rollback"), strict=True):
        if (not isinstance(mode, dict) or set(mode) != {"mode", "cases", "distinct_processes", "loopback_servers",
                "receipt_worker_restarts", "receipt_HTTP_requests", "controller_reads", "campaign_controller_requests",
                "source_and_ciphertext_exact", "four_histories_exact_across_reads", "negative_requests_no_controller_io"}
                or mode["mode"] != expected or type(mode["distinct_processes"]) is not int or mode["distinct_processes"] != 4
                or mode["loopback_servers"] != mode["distinct_processes"] or type(mode["loopback_servers"]) is not int
                or type(mode["receipt_worker_restarts"]) is not int or mode["receipt_worker_restarts"] != 1
                or type(mode["receipt_HTTP_requests"]) is not int or mode["receipt_HTTP_requests"] != len(CASES)
                or any(mode[k] is not True for k in ("source_and_ciphertext_exact", "four_histories_exact_across_reads", "negative_requests_no_controller_io"))
                or any(type(mode[k]) is not int or not 1 <= mode[k] <= 2048 for k in ("controller_reads", "campaign_controller_requests"))
                or mode["campaign_controller_requests"] != (52 if expected == "retirement" else 73)
                or not isinstance(mode["cases"], list) or len(mode["cases"]) != len(CASES)):
            raise ValueError("Native mode evidence rejected")
        reads = 0
        for row, (ident, status, state, outcome) in zip(mode["cases"], CASES, strict=True):
            if (not isinstance(row, dict) or set(row) != {"id", "status", "state", "outcome", "controller_reads"}
                    or row["id"] != ident or type(row["status"]) is not int or row["status"] != status
                    or row["state"] != state or row["outcome"] != outcome or type(row["controller_reads"]) is not int
                    or row["controller_reads"] != (0 if status != 200 or ident == "H01_readiness" else 2)):
                raise ValueError("Frozen native HTTP case rejected")
            reads += row["controller_reads"]
        if reads != mode["controller_reads"]:
            raise ValueError("Exact native request accounting required")
    return {"qualified_modes": 2, "frozen_HTTP_cases": 30, "actual_receipt_HTTP_requests": 30, "production_activation": False}
