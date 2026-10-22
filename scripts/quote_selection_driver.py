"""One attempt per declared task, at most five jobs; no private data or model retry."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
from load_driver import Workload, check, wait_for
from provider_job_checks import ProductRejected, verify_product
from provider_job_driver import original_hash
from quote_selection_cases import CASES, SUITE, SUITE_SHA256, documents, selection_result

from app.context_packing import pack_private_context


def run():
    report = {"status": "failed", "suite": SUITE, "suite_sha256": SUITE_SHA256,
              "tasks_declared": len(CASES), "maximum_concurrency": 5, "attempts_per_task": 1,
              "automatic_retries": 0, "private_documents": 0, "review_decisions": 0,
              "synthetic_only": True, "results": []}
    stage = "configuration"
    try:
        check(os.environ.get("LA_REAL_JOB_WORKLOAD") == SUITE, "Explicit evaluation profile required")
        limit = int(os.environ["LA_REAL_JOB_CONTEXT_UNITS"])
        check(3072 <= limit <= 16384, "Invalid evaluation budget")
        with httpx.Client(base_url="http://api:8000", timeout=30, trust_env=False,
                          headers={"X-Load-Token": os.environ["LA_LOAD_CONTROL_TOKEN"]}) as client:
            work = Workload(client, {}, report)
            login = work.call("POST", "/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            client.headers["X-CSRF-Token"] = login["csrf_token"]
            inventory = []
            stage = "synthetic_intake_and_oracle_visibility"
            for case in CASES:
                matter = work.call("POST", "/api/v1/matters", expected=201,
                                   json={"title": "SYNTHETIC " + case["id"], "domain": "contracts"})["id"]
                sources, passages = [], []
                for suffix, content in documents(case):
                    ident = work.upload(matter, suffix, content, metric="upload_seconds")
                    source = work.call("GET", f"/api/v1/matters/{matter}/documents/{ident}")
                    check(original_hash(client, matter, ident) == source["sha256"] == hashlib.sha256(content).hexdigest(),
                          "Original bytes changed")
                    for passage in source["passages"]:
                        check(passage["text_sha256"] == hashlib.sha256(passage["text"].encode()).hexdigest(), "Passage differs")
                        passages.append({**passage, "document_id": ident, "document_revision": source["revision"],
                                         "document_sha256": source["sha256"]})
                    sources.append(source)
                packed = pack_private_context(case["question"], passages, context_limit=limit)
                check(selection_result(case, {"evidence": packed["evidence"], "claims": []})["oracle_visible"],
                      "Required oracle was omitted before inference")
                inventory.append((case, matter, sources))
            # Complete the declared independent tasks even if another fails; these
            # are different cases, never replacement attempts for a failed case.
            stage = "declared_evaluation"

            def evaluate(item):
                case, matter, sources = item
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
                    result.update(status="passed" if result["selection_passed"] else "failed",
                                  failure_code=None if result["selection_passed"] else "selection_relevance_failed")
                except ProductRejected as error:
                    result["failure_code"] = error.code
                except Exception:
                    result["failure_code"] = "evaluation_case_failed"
                return result

            with ThreadPoolExecutor(5) as pool:
                report["results"] = list(pool.map(evaluate, inventory))
            wait_for(lambda: work.call("GET", "/_provider_jobs/state")["admitted_jobs"] == 0)
            report["final_counters"] = work.call("GET", "/_provider_jobs/state")
            report["http_observations"] = work.call("GET", "/_provider_jobs/http")
            stage = "originals_and_versions_after_evaluation"
            for _, matter, sources in inventory:
                for source in sources:
                    check(work.call("GET", f"/api/v1/matters/{matter}/documents/{source['id']}") == source
                          and original_hash(client, matter, source["id"]) == source["sha256"], "Frozen source changed")
            report["originals_and_versions_unchanged"] = True
            counters = report["final_counters"]
            report["passed_tasks"] = sum(r["status"] == "passed" for r in report["results"])
            stage = "evaluation_gate"
            check(counters["provider"]["calls"] == len(CASES) and counters["provider"]["active"] == 0
                  and counters["provider"]["failures"] == 0 and counters["admitted_jobs"] == 0
                  and report["passed_tasks"] == len(CASES), "Declared evaluation did not pass")
            report["status"] = "passed"
    except Exception:
        report.update(failure_stage=stage, failure_code="evaluation_failed")
    return report


if __name__ == "__main__":
    value = run()
    print(json.dumps(value, sort_keys=True))
    raise SystemExit(0 if value["status"] == "passed" else 1)
