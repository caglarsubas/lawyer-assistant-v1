"""Native read-only operator qualification on owned disposable ext4 volumes."""

import json
import sys
from pathlib import Path

import controller_stage_manifest as external
import operator_enrollment_evidence as operator
import operator_enrollment_fixture as q
import portable_controller_fixture as portable
import portable_controller_native as retained


def campaign(stage, approved, api):
    models, work, anchors = [Path("/" + n) for n in ("models", "work", "anchors")]
    before = retained.inventory(models)
    rows = []
    for name, expected in q.CASES:
        row = q.run_case(name, stage, approved, models, work, anchors, api)
        rows.append(row)
        if row["status"] != expected:
            operator.retain(work / "failed-report.json", operator.encode(rows))
            raise ValueError("Frozen operator qualification failed")
    if retained.inventory(models) != before or any(n == "app" or n.startswith(("app.", "inference_engine")) for n in sys.modules):
        raise ValueError("Readonly model or standalone-import invariant failed")
    return {"schema": "operator-enrollment-native-v1", "cases": rows, "package_manifest_sha256": approved,
            "policy_sha256": operator.sha(operator.encode(q.POLICY)), "read_only_model_inventory_exact": True,
            "application_or_engine_imports": False, "live_provider_requests": 0, "native_inference_calls": 0,
            "trust_enrolled": False, "private_case_inputs": False, "production_activation": False}


if __name__ == "__main__":
    packet = json.loads(Path("/controller/operator-packet.json").read_text())
    preparing = sys.argv[1] == "prepare"
    stage = Path("/stage" if preparing else "/models/stage")
    approved = packet["approved_manifest_sha256"]
    external.inspect_stage(stage, approved, expected_owner=packet["source_owner" if preparing else "owner"])
    sys.path.insert(0, str(stage))
    api = portable.modules()
    result = retained.prepare(int(sys.argv[2]), int(sys.argv[3]), stage, api) if preparing else campaign(stage, approved, api)
    print(json.dumps(result), flush=True)
