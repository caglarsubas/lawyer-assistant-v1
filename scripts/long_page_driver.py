"""One frozen five-task long-page wave; synthetic documents, no retries or private data."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
from load_driver import Workload, check, wait_for
from long_page_cases import CASES, PAGES, SUITE, SUITE_SHA256, document, selection_result
from provider_call_checks import correlate
from provider_job_checks import ProductRejected, verify_product
from provider_job_driver import original_hash
from quote_volume_driver import digest, peak_overlap

from app.context_packing import pack_private_context


def run():
    report = {"status": "failed", "suite": SUITE, "suite_sha256": SUITE_SHA256, "tasks_declared": len(CASES),
              "maximum_concurrency": 5, "attempts_per_task": 1, "automatic_retries": 0, "private_documents": 0,
              "review_decisions": 0, "synthetic_only": True, "corpus": [], "results": []}
    stage = "configuration"
    try:
        check(os.environ.get("LA_REAL_JOB_WORKLOAD") == SUITE, "Explicit long-page profile required")
        limit = int(os.environ["LA_REAL_JOB_CONTEXT_UNITS"])
        check(3072 <= limit <= 16384, "Invalid declared budget")
        with httpx.Client(base_url="http://api:8000", timeout=30, trust_env=False,
                          headers={"X-Load-Token": os.environ["LA_LOAD_CONTROL_TOKEN"]}) as client:
            work = Workload(client, {}, report)
            login = work.call("POST", "/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            client.headers["X-CSRF-Token"] = login["csrf_token"]
            inventory = []
            stage = "synthetic_intake_and_oracle_visibility"
            for case in CASES:
                matter = work.call("POST", "/api/v1/matters", expected=201,
                                   json={"title": "SYNTHETIC long page " + case["id"], "domain": "contracts"})["id"]
                content = document(case)
                ident = work.upload(matter, "pdf", content, metric="upload_seconds")
                source = work.call("GET", f"/api/v1/matters/{matter}/documents/{ident}")
                check(original_hash(client, matter, ident) == source["sha256"] == hashlib.sha256(content).hexdigest(),
                      "Original bytes changed")
                check(len(source["passages"]) == PAGES and all(len(p["text"]) > 2000 for p in source["passages"]),
                      "Long pages not exercised")
                passages = []
                for p in source["passages"]:
                    check(p["text_sha256"] == hashlib.sha256(p["text"].encode()).hexdigest(), "Passage differs")
                    passages.append({**p, "document_id": ident, "document_revision": source["revision"],
                                     "document_sha256": source["sha256"]})
                packed = pack_private_context(case["question"], passages, context_limit=limit, candidate_profile=True)
                check(selection_result(case, {"evidence": packed["evidence"], "claims": []})["oracle_visible"],
                      "Required oracle omitted before inference")
                report["corpus"].append({"case": case["id"], "bytes": len(content), "sha256": source["sha256"],
                    "revision": source["revision"], "passages": len(passages), "frozen_source_sha256": digest(source),
                    "preflight_manifest_sha256": digest(packed["manifest"])})
                inventory.append((case, matter, source))
            report["frozen_inventory_sha256"] = digest(report["corpus"])

            def evaluate(item):
                case, matter, source = item
                result = {"case": case["id"], "status": "failed"}
                try:
                    ident = work.call("POST", f"/api/v1/matters/{matter}/research", expected=202,
                                      json={"question": case["question"]})["id"]
                    row = work.terminal(matter, ident)
                    if row["status"] != "completed":
                        return {**result, "failure_code": "application_job_failed"}
                    product = work.call("GET", f"/api/v1/matters/{matter}/products/{row['product_id']}")
                    # Seal the received artifact before grading, including empty or
                    # wrong selections. A failed assessment must not lose its pins.
                    result.update(product_sha256=digest(product), source_snapshot_sha256=digest(product["snapshots"]["sources"]),
                                  prompt_sha256=product["context_pack"]["prompt"]["messages_sha256"],
                                  selected_manifest_sha256=digest(product["context_pack"]["selected"]))
                    result.update(selection_result(case, product))
                    result["evidence_check"] = verify_product(product, [source], limit, question=case["question"],
                                                              require_claims=bool(case["expected"]))
                    check(result["evidence_check"]["shortened_passages"] > 0, "Partial long page not exercised")
                    result.update(status="passed" if result["selection_passed"] else "failed",
                                  failure_code=None if result["selection_passed"] else "selection_relevance_failed")
                except ProductRejected as error:
                    result["failure_code"] = error.code
                except Exception:
                    result["failure_code"] = "evaluation_case_failed"
                return result

            stage = "declared_evaluation"
            with ThreadPoolExecutor(5) as pool:
                report["results"] = list(pool.map(evaluate, inventory))
            wait_for(lambda: work.call("GET", "/_provider_jobs/state")["admitted_jobs"] == 0)
            report["final_counters"] = work.call("GET", "/_provider_jobs/state")
            report["http_observations"] = work.call("GET", "/_provider_jobs/http")
            events = work.call("GET", "/_provider_jobs/events")
            try:
                report["call_observations"] = correlate(CASES, events)
                report["peak_application_calls"] = peak_overlap(events, range(1, len(CASES) + 1))
                report["caller_events_verified"] = True
            except (ValueError, TypeError, KeyError):
                report["caller_events_verified"] = False
            stage = "originals_and_versions_after_evaluation"
            for _, matter, source in inventory:
                check(work.call("GET", f"/api/v1/matters/{matter}/documents/{source['id']}") == source
                      and original_hash(client, matter, source["id"]) == source["sha256"], "Frozen source changed")
            report["originals_and_versions_unchanged"] = True
            report["passed_tasks"] = sum(r["status"] == "passed" for r in report["results"])
            counters = report["final_counters"]
            stage = "evaluation_gate"
            check(counters["provider"]["calls"] == len(CASES) and counters["provider"]["active"] == 0
                  and counters["provider"]["failures"] == 0 and counters["admitted_jobs"] == 0
                  and report["caller_events_verified"] and report["peak_application_calls"] == 5
                  and report["passed_tasks"] == len(CASES), "Declared long-page evaluation did not pass")
            report["status"] = "passed"
    except Exception:
        report.update(failure_stage=stage, failure_code="long_page_evaluation_failed")
    return report


if __name__ == "__main__":
    value = run()
    print(json.dumps(value, sort_keys=True))
    raise SystemExit(0 if value["status"] == "passed" else 1)
