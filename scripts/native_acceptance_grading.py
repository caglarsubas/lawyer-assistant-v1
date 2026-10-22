"""Offline acceptance-rule preflight; cannot certify native execution or law.

Only exact complete bundle selections earn expected-group credit. Grading data
is independent of the planner/model context; no transport or provider is created.
"""

from collections import Counter

from diverse_quote_bundles import resolve_diverse, sha
from native_acceptance_cases import CASES
from native_acceptance_plan import validate_plan

from app.evidence_prompt import canonical


def grade_selection(declaration, case_id, selected_ids):
    validate_plan(declaration)
    case = next((c for c in CASES if c["id"] == case_id), None)
    if case is None:
        raise ValueError("Unknown frozen acceptance case")
    row = next(c for c in declaration["cases"] if c["id"] == case_id)
    planner, sources = row["planner"], row["originals"]
    if row["disposition"] == "blocked_before_transport":
        if selected_ids != []:
            raise ValueError("Blocked control cannot have a selection")
        bundles = []
    else:
        bundles = resolve_diverse(selected_ids, planner, case["question"], sources,
                                  context_limit=case.get("context_limit", 8192))
    by_id = {p["id"]: p for p in sources}

    def contains(bundle, key, revision, texts):
        expected = case_id + "-doc-" + key
        return all(any(by_id[p["evidence_id"]]["document_id"] == expected
                       and by_id[p["evidence_id"]]["document_revision"] == revision and text in p["text"]
                       for p in bundle["parts"]) for text in texts)

    groups = [{"source_key": key, "revision": revision, "side": side,
               "available": any(contains(b, key, revision, texts) for b in planner["bundles"]),
               "selected": any(contains(b, key, revision, texts) for b in bundles)}
              for key, revision, side, texts in case["groups"]]
    for bundle in bundles:
        for part in bundle["parts"]:
            text = by_id[part["evidence_id"]]["text"][part["original_start"]:part["original_end"]]
            if part["text"] != text or part["text_sha256"] != sha(text):
                raise ValueError("Selected source boundary differs")
    expect_empty = case.get("expect_empty", False)
    # Never treat a no-call overlong positive case or a valid empty response as a
    # quality success. Negative/control and full quality outcomes stay separate.
    quality_pass = (not selected_ids if expect_empty else bool(groups) and all(g["selected"] for g in groups))
    if row["disposition"] == "blocked_before_transport":
        quality_pass = False
    return {"case": case_id, "kind": case["kind"], "disposition": row["disposition"],
            "groups": groups, "expects_empty": expect_empty, "selected_ids": selected_ids,
            "selection_quality_rule_pass": quality_pass, "native_execution_verified": False,
            "exact_selected_bundle_sha256": sha(canonical(bundles)), "all_selected_spans_versions_exact": True,
            "unmatched_fallback_bundles": sum(b["nomination"] == "unmatched_source_fallback" for b in planner["bundles"]),
            "partial_source_bundles": sum(b["partial_source"] for b in planner["bundles"]),
            "not_native_or_legal_qualification": True}


def preflight(declaration):
    validate_plan(declaration)
    rows = []
    for row in declaration["cases"]:
        # Explicit select-all *upper bound*, not a model answer or a claimed
        # positive/negative accuracy result. No hints are sent to an adapter.
        ids = [] if row["disposition"] == "blocked_before_transport" else row["wire"]["bundle_ids"]
        rows.append(grade_selection(declaration, row["id"], ids))
    groups = [g for row in rows for g in row["groups"]]
    return {"schema": "native-acceptance-offline-preflight-v1", "plan_sha256": declaration["plan_sha256"],
            "mode": "select_all_candidate_upper_bound_not_model_results", "cases": rows,
            "summary": {"cases": len(rows), "required_groups": len(groups),
                "available_groups": sum(g["available"] for g in groups),
                "unavailable_groups": sum(not g["available"] for g in groups),
                "source_passages": sum(len(r["originals"]) for r in declaration["cases"]),
                "source_versions": sum(r["planner"]["inventory"]["source_versions"] for r in declaration["cases"]),
                "dispositions": dict(sorted(Counter(r["disposition"] for r in rows).items())),
                "explicit_empty_cases": sum(r["expects_empty"] for r in rows),
                "candidate_upper_bound_failing_cases": [r["case"] for r in rows if not r["selection_quality_rule_pass"]]},
            "native_execution_verified": False, "native_qualification": False, "legal_qualification": False,
            "counts": declaration["counts"], "production_activation": False}
