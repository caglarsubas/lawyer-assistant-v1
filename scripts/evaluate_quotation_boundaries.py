"""Evaluate only fixed invented fixtures, with zero inference or private inputs."""

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

from offline_quotation_boundaries import candidate_catalog, candidate_prompt
from quotation_boundary_cases import CASES, SUITE, SUITE_SHA256, pdf_bytes

from app.context_packing import pack_private_context
from app.evidence_prompt import canonical, measure_prompt, quote_catalog
from app.extract import extract


def fixture(case):
    if case.get("pdf"):
        original_bytes = pdf_bytes(case)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SYNTHETIC.pdf"
            path.write_bytes(original_bytes)
            texts = [p["text"] for p in extract(path, ".pdf")["passages"]]
    else:
        # Preserve Unicode and CRLF exactly to test source-code-point offsets.
        texts = case["texts"]
        original_bytes = canonical(texts).encode()
    doc_hash = hashlib.sha256(original_bytes).hexdigest()
    return [{"id": f"{case['id']}-{n}", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
             "document_id": f"{case['id']}-doc", "document_revision": 1, "document_sha256": doc_hash}
            for n, text in enumerate(texts)], doc_hash


def availability(groups, catalog):
    counts, sizes = [], []
    for group in groups:
        matching = [q for q in catalog.values() if all(text in q["text"] for text in group)]
        counts.append(bool(matching))
        sizes.append(min((len(q["text"].encode()) for q in matching), default=None))
    return {"expected_groups": len(groups), "available_groups": sum(counts), "group_available": counts,
            "smallest_covering_quote_utf8_bytes": sizes, "oracle_applicable": bool(groups)}


def evaluate():
    report = {"schema": "offline-quotation-boundary-evaluation-v1", "suite": SUITE, "suite_sha256": SUITE_SHA256,
              "scope": "synthetic_boundary_geometry_only", "inference_calls": 0, "http_calls": 0,
              "private_documents": 0, "review_decisions": 0, "production_changes": 0,
              "native_or_legal_qualification": False, "context_limit_units": 8192, "cases": []}
    for case in CASES:
        originals, document_hash = fixture(case)
        sealed = canonical(originals)
        pack = pack_private_context(case["question"], originals, context_limit=8192, candidate_profile=True)
        evidence = pack["evidence"]
        baseline = quote_catalog(evidence)
        plan = candidate_catalog(evidence, originals)
        measurement = candidate_prompt(case["question"], evidence, plan, 8192)
        baseline_result = availability(case["groups"], baseline)
        candidate_result = availability(case["groups"], plan["catalog"])
        reasons = dict(sorted(Counter(row["reason"] for row in plan["omitted_windows"]).items()))
        missing = candidate_result["available_groups"] < candidate_result["expected_groups"]
        geometry_admitted = not missing and not reasons and measurement["within_budget"] and bool(plan["catalog"])
        assert canonical(originals) == sealed
        assert all(q["text"] == next(p["text"] for p in originals if p["id"] == q["evidence_id"])[q["original_start"]:q["original_end"]]
                   for q in plan["catalog"].values())
        report["cases"].append({"case": case["id"], "format": "text_pdf" if case.get("pdf") else "exact_text_fixture",
            "original_bytes_sha256": document_hash, "source_inventory_sha256": hashlib.sha256(sealed.encode()).hexdigest(),
            "source_pins": plan["source_pins"], "packed_inventory": pack["manifest"]["inventory"],
            "pack_recipe": pack["manifest"]["recipe"], "pack_manifest_sha256": hashlib.sha256(canonical(pack["manifest"]).encode()).hexdigest(),
            "baseline": {**baseline_result, "quotes": len(baseline), "prompt": measure_prompt(case["question"], evidence)},
            "candidate": {**candidate_result, "quotes": len(plan["catalog"]), "prompt": measurement,
                "omission_counts": reasons, "catalog_sha256": hashlib.sha256(canonical(plan).encode()).hexdigest(),
                "geometry_admitted": geometry_admitted},
            "source_spans_and_versions_exact": True, "originals_unchanged": True,
            "model_selection_relevance_abstention_or_injection_resistance_measured": False})
    report["summary"] = {"cases": len(CASES), "expected_groups": sum(len(c["groups"]) for c in CASES),
        "baseline_available_groups": sum(c["baseline"]["available_groups"] for c in report["cases"]),
        "candidate_available_groups": sum(c["candidate"]["available_groups"] for c in report["cases"]),
        "candidate_geometry_admitted_cases": sum(c["candidate"]["geometry_admitted"] for c in report["cases"]),
        "candidate_budget_exceeded_cases": sum(not c["candidate"]["prompt"]["within_budget"] for c in report["cases"]),
        "candidate_omissions_present_cases": sum(bool(c["candidate"]["omission_counts"]) for c in report["cases"])}
    report["conclusion"] = "offline_candidate_not_production_qualified"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate()
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"suite": SUITE, "inference_calls": 0, "summary": report["summary"], "conclusion": report["conclusion"]}))


if __name__ == "__main__":
    main()
