"""Three declared five-job waves; only invented documents, no retry or review write."""

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from load_driver import Workload, check, wait_for
from load_metrics import distribution


def run():
    report = {"status": "failed", "synthetic_only": True, "waves_declared": 3, "concurrency": 5,
              "automatic_retries": 0, "review_decisions": 0, "private_documents": 0}
    workload = None
    stage = "configuration"
    try:
        with httpx.Client(base_url="http://api:8000", timeout=30, trust_env=False,
                          headers={"X-Load-Token": os.environ["LA_LOAD_CONTROL_TOKEN"]}) as client:
            workload = Workload(client, {}, report)
            login = workload.call("POST", "/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            client.headers["X-CSRF-Token"] = login["csrf_token"]
            workspaces, sources, versions, corpus = [], [], [], []
            stage = "synthetic_intake"
            for index in range(5):
                matter = workload.call("POST", "/api/v1/matters", expected=201,
                                      json={"title": f"SYNTHETIC provider workspace {index}", "domain": "contracts"})["id"]
                content = f"SYNTHETIC payment odeme evidence: ornek tutar {100 + index} birimdir.\n".encode()
                sources.append(workload.upload(matter, "txt", content, metric="upload_seconds"))
                document = workload.call("GET", f"/api/v1/matters/{matter}/documents/{sources[-1]}")
                versions.append(document["revision"])
                workspaces.append(matter)
                corpus.append({"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            report["corpus"] = corpus
            waves = []
            stage = "real_provider_jobs"
            with ThreadPoolExecutor(5) as pool:
                for wave in range(3):
                    start = time.monotonic()
                    ids = list(pool.map(workload.submit, workspaces))
                    rows = list(pool.map(lambda pair: workload.terminal(*pair), zip(workspaces, ids, strict=True)))
                    statuses = [row["status"] for row in rows]
                    waves.append({"index": wave, "seconds": round(time.monotonic() - start, 6), "statuses": statuses})
                    report["waves"] = waves
                    report["observed_counters"] = workload.call("GET", "/_provider_jobs/state")
                    waves[-1]["error_codes"] = [row.get("error_code") for row in rows]
                    # Every declared wave must pass; do not replace failures with another wave.
                    check(statuses == ["completed"] * 5, "A real-provider job failed")
                    for matter, source, version, row in zip(workspaces, sources, versions, rows, strict=True):
                        product = workload.call("GET", f"/api/v1/matters/{matter}/products/{row['product_id']}")
                        check(product["status"] == "needs_review" and product["snapshots"]["sources"] == {source: version}, "Source version not retained")
                        evidence = {p["id"]: p["text"] for p in product["evidence"]}
                        check(bool(product["claims"]) and all(
                            claim["evidence_ids"] and all(ref in evidence and claim["text"] in evidence[ref]
                                                         for ref in claim["evidence_ids"])
                            for claim in product["claims"]), "Claim grounding failed")
                    wait_for(lambda: workload.call("GET", "/_provider_jobs/state")["admitted_jobs"] == 0)
            final = workload.call("GET", "/_provider_jobs/state")
            report["final_counters"] = final
            check(final == {"provider": {"active": 0, "peak": 5, "calls": 15, "failures": 0, "diagnostics": {}},
                            "admitted_jobs": 0}, "Workers failed to overlap or drain")
            report.update(status="passed", completed_jobs=15, all_claims_grounded=True,
                          wave_seconds=distribution([row["seconds"] for row in waves]))
    except Exception:
        report["failure_stage"] = stage
    return report


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)
