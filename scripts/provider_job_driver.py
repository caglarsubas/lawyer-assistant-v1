"""Three declared five-job waves; only invented documents, no retry or review write."""

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from load_driver import Workload, check, documents, wait_for
from load_metrics import distribution
from provider_job_checks import WORKLOADS, ProductRejected, verify_product


def corpus(index, profile):
    if profile == "short-txt-v1":
        yield "txt", f"SYNTHETIC payment odeme evidence: ornek tutar {100 + index} birimdir.\n".encode()
    elif profile == "mixed-formats-v1":
        for suffix, content in documents(index):
            if suffix == "txt":
                # One long Unicode paragraph forces visible exact-span packing.
                long = ("SYNTHETIC payment odeme evidence: Örnek çalışma kaydıdır, hukuki dayanak değildir. " * 40)
                content = long.encode() + b"\n\n" + content
            yield suffix, content
    else:
        raise ValueError("Unknown declared workload")


def original_hash(client, matter, document):
    response = client.get(f"/api/v1/matters/{matter}/documents/{document}/original")
    check(response.status_code == 200, "Original unavailable")
    return hashlib.sha256(response.content).hexdigest()


def run():
    report = {"status": "failed", "synthetic_only": True, "waves_declared": 3, "concurrency": 5,
              "automatic_retries": 0, "review_decisions": 0, "private_documents": 0}
    workload = None
    profile = os.environ.get("LA_REAL_JOB_WORKLOAD", "short-txt-v1")
    report.update(workload_profile=profile, intake_mode="demo parser subprocess; no malware or isolated-service qualification")
    stage = "configuration"
    try:
        context_limit = int(os.environ.get("LA_REAL_JOB_CONTEXT_UNITS", "8192"))
        check(profile in WORKLOADS and 3072 <= context_limit <= 16384, "Invalid declared workload")
        with httpx.Client(base_url="http://api:8000", timeout=30, trust_env=False,
                          headers={"X-Load-Token": os.environ["LA_LOAD_CONTROL_TOKEN"]}) as client:
            workload = Workload(client, {}, report)
            login = workload.call("POST", "/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
            client.headers["X-CSRF-Token"] = login["csrf_token"]
            workspaces, frozen_sources, files = [], [], []
            stage = "synthetic_intake"
            for index in range(5):
                matter = workload.call("POST", "/api/v1/matters", expected=201,
                                      json={"title": f"SYNTHETIC provider workspace {index}", "domain": "contracts"})["id"]
                sources = []
                for suffix, content in corpus(index, profile):
                    identity = workload.upload(matter, suffix, content, metric="upload_seconds")
                    document = workload.call("GET", f"/api/v1/matters/{matter}/documents/{identity}")
                    check(original_hash(client, matter, identity) == document["sha256"] == hashlib.sha256(content).hexdigest(),
                          "Original bytes changed on intake")
                    check(all(p["text_sha256"] == hashlib.sha256(p["text"].encode()).hexdigest()
                              for p in document["passages"]), "Frozen passage hash differs")
                    sources.append(document)
                    files.append({"format": suffix, "bytes": len(content), "sha256": document["sha256"],
                                  "extracted_passages": len(document["passages"])})
                workspaces.append(matter)
                frozen_sources.append(sources)
            report["corpus"] = files
            waves = []
            stage = "real_provider_jobs"
            with ThreadPoolExecutor(5) as pool:
                for wave in range(3):
                    stage = "real_provider_jobs"
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
                    stage = "product_verification"
                    verified = []
                    waves[-1]["verified_products"] = verified
                    for matter, sources, row in zip(workspaces, frozen_sources, rows, strict=True):
                        product = workload.call("GET", f"/api/v1/matters/{matter}/products/{row['product_id']}")
                        check_result = verify_product(product, sources, context_limit)
                        if profile == "mixed-formats-v1":
                            check(check_result["selected_documents"] == 4 and check_result["omitted_passages"] > 0
                                  and check_result["shortened_passages"] > 0, "Mixed-source partial coverage not exercised")
                        verified.append(check_result)
                    waves[-1]["verified_products"] = verified
                    wait_for(lambda: workload.call("GET", "/_provider_jobs/state")["admitted_jobs"] == 0)
            stage = "originals_after_research"
            for matter, sources in zip(workspaces, frozen_sources, strict=True):
                for source in sources:
                    current = workload.call("GET", f"/api/v1/matters/{matter}/documents/{source['id']}")
                    check(current == source and original_hash(client, matter, source["id"]) == source["sha256"],
                          "Source revision, passage or original changed after research")
            final = workload.call("GET", "/_provider_jobs/state")
            report["final_counters"] = final
            check(final == {"provider": {"active": 0, "peak": 5, "calls": 15, "failures": 0, "diagnostics": {}},
                            "admitted_jobs": 0}, "Workers failed to overlap or drain")
            report.update(status="passed", completed_jobs=15, all_claims_grounded=True, originals_and_versions_unchanged=True,
                          wave_seconds=distribution([row["seconds"] for row in waves]))
    except ProductRejected as error:
        report.update(failure_stage=stage, failure_code=error.code)
    except Exception:
        report.update(failure_stage=stage, failure_code="qualification_failed")
    return report


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)
