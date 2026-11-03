"""Frozen disposable mount/socket evidence; no operator or legal authorization."""

import json

from controller_stage_manifest import digest, hex_digest

CASES = {"M01_kernel_readonly": "verified", **dict.fromkeys(("M02_pin", "M03_bytes", "M04_extra",
         "M05_symlink", "M06_hardlink", "M07_owner", "M08_writable_stage", "M09_writable_host"), "rejected"),
         **dict.fromkeys(("H01_shell", "H02_session", "H03_preview", "H04_mismatch", "H05_comparison",
                         "H06_csrf", "H07_origin", "H08_host", "H09_forwarded", "H10_body_timeout",
                         "H11_expiry", "H12_revocation", "H13_shutdown"), "verified")}
FALSE = ("private_case_inputs", "real_operator_approval", "external_checksum_channel_verified",
         "production_activation", "legal_review")


def plan_sha256():
    return digest(json.dumps(CASES, separators=(",", ":")).encode())


def validate(value, manifest_pin):
    fields = {"schema", "package_manifest_sha256", "case_plan_sha256", "cases", "filesystem",
              "kernel_readonly", "source_inventory_exact", "stage_inventory_exact", "four_histories_exact",
              "separate_server_and_client", "listener_loopback_only", "listener_closed", "native_inference_calls",
              "provider_requests", "HTTP_requests", "clock_scope", *FALSE}
    truths = ("kernel_readonly", "source_inventory_exact", "stage_inventory_exact", "four_histories_exact",
              "separate_server_and_client", "listener_loopback_only", "listener_closed")
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "native-operator-preview-v1"
            or value["package_manifest_sha256"] != hex_digest(manifest_pin)
            or value["case_plan_sha256"] != plan_sha256() or value["filesystem"] != "ext4"
            or any(value[k] is not True for k in truths) or any(value[k] is not False for k in FALSE)
            or value["clock_scope"] != "controlled_disposable_clock"
            or any(type(value[k]) is not int or value[k] != 0 for k in ("native_inference_calls", "provider_requests"))
            or type(value["HTTP_requests"]) is not int or value["HTTP_requests"] != 12
            or value["cases"] != [{"id": k, "state": v} for k, v in CASES.items()]):
        raise ValueError("Frozen native preview evidence rejected")
    return {"qualified": True, "cases": len(CASES), "scope": "disposable Linux/ext4 mounts and loopback HTTP only",
            "real_operator_approval": False, "production_activation": False, "legal_review": False}
