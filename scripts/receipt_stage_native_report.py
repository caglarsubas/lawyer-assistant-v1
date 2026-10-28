"""Closed, frozen native packaging gate; does not qualify operator authorization."""

from controller_stage_manifest import hex_digest

CASES = {"N01_valid": "verified", **dict.fromkeys(("N02_pin", "N03_extra", "N04_mode", "N05_symlink",
         "N06_hardlink", "N07_forbidden_import", "N08_writable", "N09_owner", "N10_bytes"), "rejected")}
FALSE = ("application_or_engine_imports", "private_case_inputs", "real_trust_confirmed", "production_activation")


def validate(value, expected_manifest):
    fields = {"schema", "package_manifest_sha256", "cases", "read_only_inventory_exact", "distinct_processes",
              "filesystem", "kernel_readonly", "native_inference_calls", "live_provider_requests", "HTTP_requests",
              "operator_authorization", "key_custody", *FALSE}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "receipt-stage-native-packaging-v1"
            or value["package_manifest_sha256"] != hex_digest(expected_manifest)
            or value["read_only_inventory_exact"] is not True or value["kernel_readonly"] is not True
            or value["filesystem"] != "ext4" or value["operator_authorization"] != "unassessed"
            or value["key_custody"] != "unassessed" or any(value[k] is not False for k in FALSE)
            or any(type(value[k]) is not int or value[k] != 0 for k in ("native_inference_calls", "live_provider_requests", "HTTP_requests"))
            or type(value["distinct_processes"]) is not int or value["distinct_processes"] != len(CASES)
            or not isinstance(value["cases"], list) or len(value["cases"]) != len(CASES)):
        raise ValueError("Native packaging evidence rejected")
    for row, (name, state) in zip(value["cases"], CASES.items(), strict=True):
        if (not isinstance(row, dict) or set(row) != {"id", "state", "inspected_before_import", "package_imported",
                "application_or_engine_imports", "kernel_write_rejected", "disposable_readiness"}
                or row["id"] != name or row["state"] != state or row["inspected_before_import"] is not True
                or row["package_imported"] is not (state == "verified") or row["application_or_engine_imports"] is not False
                or row["kernel_write_rejected"] is not (state == "verified")
                or row["disposable_readiness"] != ("verified" if state == "verified" else "not_checked")):
            raise ValueError("Frozen native packaging case rejected")
    return {"cases": len(CASES), "qualified": True, "scope": "Linux/ext4 read-only package and process isolation only",
            "operator_authorization": "unassessed", "production_activation": False}
