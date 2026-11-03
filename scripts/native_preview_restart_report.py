"""Closed native restart evidence; never authority renewal or operator approval."""

import json

from controller_stage_manifest import digest, hex_digest

CASES = dict.fromkeys((
    "K01_idle_SIGKILL", "K02_idle_socket_closed", "R01_missing_session", "R02_wrong_CSRF",
    "R03_current_bootstrap", "R04_exact_preview", "K03_partial_body_SIGKILL",
    "K04_partial_response_withheld", "K05_partial_socket_closed", "R05_revoked_cookie",
    "R06_old_CSRF_new_cookie", "R07_new_session_bootstrap", "R08_new_session_preview",
    "R09_independent_comparison", "K06_after_observation_SIGKILL", "K07_observation_socket_closed",
    "R10_restart_bootstrap", "R11_original_version_and_expiry", "R12_missing_independent_entry",
    "R13_wrong_independent_entry", "R14_explicit_comparison", "R15_clean_shutdown_closed",
    "B01_expired_handoff", "B02_changed_trusted_pin", "B03_revoked_preparer",
), "verified")
FALSE = ("private_case_inputs", "real_operator_approval", "external_checksum_channel_verified",
         "production_activation", "legal_review", "automatic_replay", "authority_renewed")
TRUE = ("kernel_readonly", "source_inventory_exact", "stage_inventory_exact", "six_stores_exact",
        "fresh_connection_pools", "listener_loopback_only", "all_listeners_closed", "same_handoff_and_expiry")


def plan_sha256():
    return digest(json.dumps(CASES, separators=(",", ":")).encode())


def validate(value, manifest_pin):
    fields = {"schema", "package_manifest_sha256", "case_plan_sha256", "cases", "filesystem",
              "processes", "SIGKILL_exitcodes", "HTTP_requests", "native_inference_calls", "provider_requests",
              "session_replacements", "fixture_scope", "restart_scope", *FALSE, *TRUE}
    counts = {"processes": 7, "HTTP_requests": 15, "session_replacements": 1,
              "native_inference_calls": 0, "provider_requests": 0}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "native-preview-restart-v1"
            or value["package_manifest_sha256"] != hex_digest(manifest_pin)
            or value["case_plan_sha256"] != plan_sha256() or value["filesystem"] != "ext4"
            or any(value[k] is not True for k in TRUE) or any(value[k] is not False for k in FALSE)
            or any(type(value[k]) is not int or value[k] != n for k, n in counts.items())
            or value["SIGKILL_exitcodes"] != [-9, -9, -9]
            or any(type(n) is not int for n in value["SIGKILL_exitcodes"])
            or value["fixture_scope"] != "invented_accounts_and_encrypted_metadata_only"
            or value["restart_scope"] != "forked_workers_controller_retains_fixture_in_memory"
            or value["cases"] != [{"id": k, "state": v} for k, v in CASES.items()]):
        raise ValueError("Frozen native restart evidence rejected")
    return {"qualified": True, "cases": len(CASES),
            "scope": "disposable Linux/ext4 forked-listener interruption and fresh request authorization only",
            "real_operator_approval": False, "production_activation": False, "legal_review": False}
