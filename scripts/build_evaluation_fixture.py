#!/usr/bin/env python3
"""Write four invented scoring examples. Never supplies real adjudication or approval."""

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.qualification_scoring import (  # noqa: E402
    CONNECTED_SLICES,
    LOCAL_SLICES,
    METRIC_DENOMINATORS,
    PAIR_MODES,
    SNAPSHOT_KEYS,
    Protocol,
    digest,
)


def fixture(provider=None):
    snapshot = {key: "synthetic-only" for key in sorted(SNAPSHOT_KEYS)}
    catalog = LOCAL_SLICES | (CONNECTED_SLICES if provider else {})
    protocol = {"schema_version": "legal-evaluation-protocol-v1", "protocol_id": "synthetic-example",
                "registered_at": "2026-01-01T00:00:00Z", "mode": "connected" if provider else "local",
                "provider": provider, "provider_configuration_sha256": digest("synthetic-provider") if provider else None,
                "snapshot_sha256": digest(snapshot), "rubric_sha256": digest("synthetic-rubric"),
                "task_target": 1000, "claim_target": 3000,
                "practice_minimums": dict.fromkeys(("contracts", "commercial", "employment")),
                "slice_minimums": dict.fromkeys(sorted(catalog)),
                "pair_minimums": dict.fromkeys(PAIR_MODES if provider else ("correction", "standard_deep")),
                "metric_minimums": dict.fromkeys(sorted(METRIC_DENOMINATORS)),
                "independent_family_minimum": None, "development_family_sha256": [digest("synthetic-development")]}
    Protocol.model_validate(protocol)
    rows = []
    for index in range(4):
        task_hash = digest(f"synthetic-task-{index}")
        trial = {"task_input_sha256": task_hash, "snapshot_sha256": digest(snapshot),
                 "substantive_claims": 3, "supported_claims": 3, "claims_with_resolvable_citations": 3, "adverse_found": ["synthetic-adverse"],
                 "argument_quality": 0.8, "critical_errors": 0, "elapsed_seconds": 2.0,
                 "compute_seconds": 2.0, "external_cost_usd": 0.0, "preparation_seconds": 10.0,
                 "review_seconds": 8.0, "verification_and_correction_included": True}
        pairs = [{"kind": kind, "baseline": {**trial, "mode": PAIR_MODES[kind][0]},
                  "candidate": {**trial, "mode": PAIR_MODES[kind][1]},
                  "seeded_defects": int(kind == "correction"), "repaired_with_evidence": int(kind == "correction"),
                  "explicitly_withheld": 0, "unresolved_defects": 0, "introduced_regressions": 0}
                 for kind in protocol["pair_minimums"]]
        rows.append({"schema_version": "legal-evaluation-task-v1", "protocol_sha256": digest(protocol),
                     "snapshot_sha256": digest(snapshot), "rubric_sha256": protocol["rubric_sha256"],
                     "mode": protocol["mode"], "provider": provider,
                     "provider_configuration_sha256": protocol["provider_configuration_sha256"],
                     "sample_kind": "synthetic", "measured_at": "2026-01-02T00:00:00Z",
                     "task_input_sha256": task_hash, "split_family_sha256": digest(f"synthetic-family-{index}"),
                     "adjudication_evidence_sha256": digest(f"synthetic-labels-{index}"),
                     "annotators": ["synthetic-a", "synthetic-b"], "disagreements_resolved": True,
                     "score": {"task_id": f"synthetic-{index}", "adjudicator": "synthetic-arbiter", "held_out": True,
                               "domain": ("contracts", "commercial", "employment")[index % 3], "period": "synthetic",
                               "relationship_types": ["synthetic-citation"],
                               "claims": [{"supported": True, "citation_resolves": True}] * 3,
                               "critical_errors": 0, "answerable": index != 3, "satisfactory": index != 3,
                               "appropriate_abstention": True if index == 3 else None,
                               "gold_authorities": ["synthetic-authority"], "retrieved_authorities": ["synthetic-authority"],
                               "exact_identifier_success": True, "legitimate_sensitive_task_passed": True,
                               "baseline_seconds": 100.0, "assisted_seconds": 60.0, "verification_and_correction_included": True},
                     "analysis": {"consequential_steps": 3, "grounded_steps": 3, "critical_unsupported_inferences": 0,
                                  "critical_fact_substitutions": 0, "critical_omissions": 0, "critical_role_errors": 0,
                                  "gold_adverse_authorities": ["synthetic-adverse"],
                                  "retrieved_adverse_authorities": ["synthetic-adverse"]},
                     "slices": sorted(catalog), "checks": dict.fromkeys(sorted(set().union(*catalog.values())), True),
                     "pairs": deepcopy(pairs)})
    return protocol, snapshot, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--provider", choices=["openai", "anthropic", "gemini"])
    args = parser.parse_args()
    protocol, snapshot, rows = fixture(args.provider)
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, value in (("protocol.json", protocol), ("snapshot.json", snapshot)):
        (args.output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    (args.output / "tasks.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    print("Created four synthetic scoring examples with unknown sample minima; no qualification or provider access.")


if __name__ == "__main__":
    main()
