"""Three declared five-task waves over frozen invented mixed-format documents."""

import hashlib
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
from load_driver import Workload, check, wait_for
from provider_job_checks import ProductRejected, verify_product
from provider_job_driver import original_hash
from quote_volume_cases import CASES, SUITE, SUITE_SHA256, WORKSPACES, documents, selection_result

from app.context_packing import pack_private_context
from app.evidence_prompt import canonical


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def peak_overlap(events, sequences):
    selected = [event for event in events if event["sequence"] in sequences]
    check(len(selected) == len(sequences) and {e["sequence"] for e in selected} == set(sequences), "Missing caller events")
    points = []
    for event in selected:
        start, end = event["started"], event["finished"]
        check(type(start) in (int, float) and type(end) in (int, float) and math.isfinite(start)
              and math.isfinite(end) and 0 < start < end, "Invalid caller interval")
        points += [(start, 1), (end, -1)]
    active = peak = 0
    for _, change in sorted(points):  # End before start at equal timestamps.
        active += change
        peak = max(peak, active)
    check(active == 0, "Caller intervals did not drain")
    return peak


def run():
    report = {"status": "failed", "suite": SUITE, "suite_sha256": SUITE_SHA256, "tasks_declared": 15,
              "waves_declared": 3, "maximum_concurrency": 5, "attempts_per_task": 1, "automatic_retries": 0,
              "private_documents": 0, "review_decisions": 0, "synthetic_only": True, "corpus": [], "waves": []}
    stage = "configuration"
    try:
        check(os.environ.get("LA_REAL_JOB_WORKLOAD") == SUITE, "Explicit volume profile required")
        limit = int(os.environ["LA_REAL_JOB_CONTEXT_UNITS"])
        check(3072 <= limit <= 16384, "Invalid declared budget")
        with httpx.Client(base_url="http://api:8000", timeout=30, trust_env=False,
                          headers={"X-Load-Token": os.environ["LA_LOAD_CONTROL_TOKEN"]}) as client:
            work = Workload(client, {}, report)
            login = work.call("POST", "/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            client.headers["X-CSRF-Token"] = login["csrf_token"]
            inventory = []
            stage = "synthetic_intake_and_oracle_visibility"
            for value in WORKSPACES:
                matter = work.call("POST", "/api/v1/matters", expected=201,
                                   json={"title": "SYNTHETIC volume " + value["id"], "domain": "contracts"})["id"]
                sources, passages = [], []
                for suffix, content in documents(value):
                    ident = work.upload(matter, suffix, content, metric="upload_seconds")
                    source = work.call("GET", f"/api/v1/matters/{matter}/documents/{ident}")
                    check(original_hash(client, matter, ident) == source["sha256"] == hashlib.sha256(content).hexdigest(),
                          "Original bytes changed")
                    for p in source["passages"]:
                        check(p["text_sha256"] == hashlib.sha256(p["text"].encode()).hexdigest(), "Passage differs")
                        passages.append({**p, "document_id": ident, "document_revision": source["revision"],
                                         "document_sha256": source["sha256"]})
                    sources.append(source)
                    report["corpus"].append({"workspace": value["id"], "format": suffix, "bytes": len(content),
                        "sha256": source["sha256"], "revision": source["revision"], "passages": len(source["passages"]),
                        "frozen_source_sha256": digest(source)})
                for case in value["tasks"]:
                    packed = pack_private_context(case["question"], passages, context_limit=limit, candidate_profile=True)
                    check(selection_result(case, {"evidence": packed["evidence"], "claims": []})["oracle_visible"],
                          "Required oracle omitted before inference")
                inventory.append((matter, sources))
            report["frozen_inventory_sha256"] = digest(report["corpus"])

            def evaluate(case):
                matter, sources = inventory[case["workspace"]]
                result = {"case": case["id"], "status": "failed"}
                try:
                    ident = work.call("POST", f"/api/v1/matters/{matter}/research", expected=202,
                                      json={"question": case["question"]})["id"]
                    row = work.terminal(matter, ident)
                    if row["status"] != "completed":
                        return {**result, "failure_code": "application_job_failed"}
                    product = work.call("GET", f"/api/v1/matters/{matter}/products/{row['product_id']}")
                    result.update(selection_result(case, product))
                    result["evidence_check"] = verify_product(product, sources, limit, question=case["question"],
                                                              require_claims=bool(case["expected"]))
                    counts = result["evidence_check"]
                    check(counts["selected_documents"] == 4 and counts["omitted_passages"] > 0
                          and counts["shortened_passages"] > 0, "Mixed partial context not exercised")
                    result.update(prompt_sha256=product["context_pack"]["prompt"]["messages_sha256"],
                                  selected_manifest_sha256=digest(product["context_pack"]["selected"]),
                                  product_sha256=digest(product), source_snapshot_sha256=digest(product["snapshots"]["sources"]))
                    result.update(status="passed" if result["selection_passed"] else "failed",
                                  failure_code=None if result["selection_passed"] else "selection_relevance_failed")
                except ProductRejected as error:
                    result["failure_code"] = error.code
                except Exception:
                    result["failure_code"] = "evaluation_case_failed"
                return result

            stage = "declared_evaluation"
            with ThreadPoolExecutor(5) as pool:
                for index in range(3):
                    # All distinct cases are declared up front. A later wave never
                    # replaces a failed task, and no task is attempted twice.
                    rows = list(pool.map(evaluate, [c for c in CASES if c["wave"] == index]))
                    wait_for(lambda: work.call("GET", "/_provider_jobs/state")["admitted_jobs"] == 0)
                    counters = work.call("GET", "/_provider_jobs/state")
                    events = work.call("GET", "/_provider_jobs/events")
                    wave = {"index": index, "results": rows, "counters": counters,
                            "http_observations": work.call("GET", "/_provider_jobs/http"), "peak_application_calls": None}
                    report["waves"].append(wave)
                    try:
                        wave["peak_application_calls"] = peak_overlap(events, range(index * 5 + 1, index * 5 + 6))
                    except (ValueError, TypeError, KeyError):
                        wave["caller_intervals_verified"] = False  # Retain all case results and check originals anyway.
            stage = "originals_and_versions_after_evaluation"
            for matter, sources in inventory:
                for source in sources:
                    check(work.call("GET", f"/api/v1/matters/{matter}/documents/{source['id']}") == source
                          and original_hash(client, matter, source["id"]) == source["sha256"], "Frozen source changed")
            report["originals_and_versions_unchanged"] = True
            report["passed_tasks"] = sum(r["status"] == "passed" for w in report["waves"] for r in w["results"])
            counters = report["waves"][-1]["counters"]
            stage = "evaluation_gate"
            check(counters["provider"]["calls"] == 15 and counters["provider"]["active"] == 0
                  and counters["provider"]["failures"] == 0 and counters["admitted_jobs"] == 0
                  and all(w["peak_application_calls"] == 5 for w in report["waves"])
                  and report["passed_tasks"] == 15, "Declared volume evaluation did not pass")
            report["status"] = "passed"
    except Exception:
        report.update(failure_stage=stage, failure_code="volume_evaluation_failed")
    return report


if __name__ == "__main__":
    value = run()
    print(json.dumps(value, sort_keys=True))
    raise SystemExit(0 if value["status"] == "passed" else 1)
