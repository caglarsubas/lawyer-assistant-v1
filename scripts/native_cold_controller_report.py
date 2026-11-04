"""Frozen cold-controller qualification; independently retained fixture pins only."""

import json

from controller_stage_manifest import digest, hex_digest

CASES = dict.fromkeys((
    "C01_seed_process_exited", "K01_idle_controller_SIGKILL", "K02_idle_listener_closed",
    "B01_missing_independent_pins", "B02_wrong_descriptor_pin", "B03_wrong_handoff_pin",
    "B04_wrong_profile_pin", "B05_wrong_database_inode", "B06_expired_original_handoff",
    "R01_missing_cookie", "R02_wrong_CSRF", "R03_fresh_bootstrap", "R04_exact_original_preview",
    "K03_partial_controller_SIGKILL", "K04_partial_response_withheld", "K05_partial_listener_closed",
    "R05_cold_bootstrap", "R06_original_version_and_expiry", "R07_missing_independent_entry",
    "R08_wrong_independent_entry", "R09_explicit_independent_comparison",
    "K06_completed_observation_SIGKILL", "K07_completed_listener_closed", "R10_revoked_cookie_bootstrap",
    "R11_revoked_cookie_preview", "R12_clean_shutdown_closed", "B07_revoked_preparer",
    "S01_original_six_stores_and_retained_keys", "S02_no_recovery_account_writes", "C02_distinct_cold_interpreters",
), "verified")
TRUE = ("kernel_readonly", "source_inventory_exact", "stage_inventory_exact", "six_stores_exact",
        "retained_keys_exact", "cold_interpreters", "independent_pins_required", "read_only_account_reopen",
        "all_listeners_closed", "same_handoff_and_expiry", "no_inherited_controller_objects")
FALSE = ("private_case_inputs", "real_operator_approval", "external_checksum_channel_verified",
         "production_activation", "legal_review", "automatic_replay", "authority_renewed", "new_sessions_on_recovery")
COUNTS = {"processes": 12, "controller_processes": 11, "seed_processes": 1, "HTTP_requests": 12,
          "native_inference_calls": 0, "provider_requests": 0, "explicit_fixture_session_revocations": 2}


def plan_sha256():
    return digest(json.dumps(CASES, separators=(",", ":")).encode())


def validate(value, package_pin):
    fields = {"schema", "package_manifest_sha256", "case_plan_sha256", "cases", "filesystem",
              "SIGKILL_exitcodes", "fixture_scope", "restart_scope", *COUNTS, *TRUE, *FALSE}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "native-cold-controller-v1"
            or value["package_manifest_sha256"] != hex_digest(package_pin)
            or value["case_plan_sha256"] != plan_sha256() or value["filesystem"] != "ext4"
            or value["cases"] != [{"id": k, "state": v} for k, v in CASES.items()]
            or any(type(value[k]) is not int or value[k] != v for k, v in COUNTS.items())
            or any(value[k] is not True for k in TRUE) or any(value[k] is not False for k in FALSE)
            or value["SIGKILL_exitcodes"] != [-9, -9, -9] or any(type(n) is not int for n in value["SIGKILL_exitcodes"])
            or value["fixture_scope"] != "invented_accounts_and_encrypted_metadata_only"
            or value["restart_scope"] != "spawned_cold_interpreters_original_pins_and_retained_files_only"):
        raise ValueError("Frozen cold-controller evidence rejected")
    return {"qualified": True, "cases": len(CASES),
            "scope": "disposable Linux/ext4 cold controller reconstruction with original fixture bindings",
            "production_activation": False, "real_operator_approval": False, "legal_review": False}
