"""Second frozen corpus for descriptor-pinned mapped verification; invented only."""

import concurrent.futures
import hashlib
import json
import multiprocessing
import os
import random
import resource
import shutil
import time
from pathlib import Path

import artifact_store as a

CASES = [("P01_tiny", "ok"), ("P02_two_windows_tail", "ok"), ("P03_exact_three_windows", "ok"),
         ("P04_below_window", "ok"), ("P05_maximum_layers", "ok"), ("P06_maximum_text", "ok"),
         ("P07_corrupt_config", "digest"), ("P08_boolean_text_size", "descriptor"),
         ("P09_missing_final_text", "missing"), ("P10_model_symlink", "links"),
         ("P11_writable", "readonly"), ("P12_cancel_after_start", "cancelled"),
         ("P13_descriptor_exhaustion", "invalid")]
POLICY = {"schema": "pinned-windowed-acceptance-v1", "cases": [dict(id=n, expected=v) for n, v in CASES],
          "fresh_seed": 20261027, "strategy": "windowed-pinned", "window_bytes": 16 * 1024**2,
          "model_bytes": 8 * a.GIB, "pre_post_target_seconds": 20, "shared_job_seconds": 60,
          "wave_seconds": 75, "rss_kib": 128 * 1024, "jobs": 5, "cpu_limit": 2,
          "memory_limit_mib": 768, "order": ["candidate", "baseline"], "attempts_per_profile": 1,
          "cache_condition": "warm_creation_and_prior_read_no_eviction",
          "descriptor_failure_soft_limit": 24, "max_pinned_blobs": 18,
          "native_inference_qualified": False, "cold_cache_qualified": False}


def write(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def descriptor(media, raw):
    return {"mediaType": media, "digest": "sha256:" + a.digest(raw), "size": len(raw)}


def snapshot(root, variant="P01_tiny", *, large=None):
    if root.exists() or root.is_symlink() or root.parent != root.parent.resolve():
        raise ValueError("Fresh unlinked pinned fixture required")
    root.mkdir(mode=0o700)
    for name in ("blobs", "manifests", "manifests-v2"):
        (root / name).mkdir(mode=0o700)
    size = {"P02_two_windows_tail": 2 * a.WINDOW + 137, "P03_exact_three_windows": 3 * a.WINDOW,
            "P04_below_window": a.WINDOW - 257}.get(variant, 8193)
    model_raw = None
    if large is None:
        model_raw = b"GGUF\x03\0\0\0" + b"\0" * 16 + random.Random(20261027).randbytes(size - 24)
        model = descriptor(a.MODEL, model_raw)
    else:
        model = {k: large[k] for k in ("mediaType", "digest", "size")}
    text_count = 15 if variant in {"P05_maximum_layers", "P13_descriptor_exhaustion"} else 3
    texts = [b"Fresh descriptor-pin qualification P27 text " + str(n).encode() for n in range(text_count)]
    if variant == "P06_maximum_text":
        texts[0] = b"p" * a.CHUNK
    kinds = ["template", "system", "license"]
    layers = [model, *[descriptor("application/vnd.ollama.image." + kinds[n % 3], raw) for n, raw in enumerate(texts)]]
    config = {"model_format": "gguf", "model_family": "llama", "model_families": ["llama"],
              "rootfs": {"type": "layers", "diff_ids": [v["digest"] for v in layers]}}
    cr = a.canonical(config)
    manifest = {"schemaVersion": 2, "mediaType": a.MANIFEST, "config": descriptor(a.CONFIG, cr),
                "layers": [dict(v) for v in layers]}
    if variant == "P08_boolean_text_size":
        manifest["layers"][-1]["size"] = True
    mr = a.canonical(manifest)
    pin = "sha256:" + a.digest(mr)
    data = [(pin, mr), (manifest["config"]["digest"], cr),
            *[(v["digest"], raw) for v, raw in zip(layers[1:], texts)]]
    if model_raw is not None:
        data.append((model["digest"], model_raw))
    for ref, raw in data:
        write(root / "blobs" / ref.replace(":", "-"), raw)
    model_path = root / "blobs" / model["digest"].replace(":", "-")
    if large is not None:
        shutil.copyfile(large["path"], model_path)
        model_path.chmod(0o600)
    if variant == "P07_corrupt_config":
        write(root / "blobs" / manifest["config"]["digest"].replace(":", "-"), cr[:-1] + b"!")
    if variant == "P09_missing_final_text":
        (root / "blobs" / layers[-1]["digest"].replace(":", "-")).unlink()
    if variant == "P10_model_symlink":
        model_path.unlink()
        model_path.symlink_to("/absent-invented-pin-fixture")
    return {"manifest_digest": pin, "model_digest": model["digest"], "model_bytes": model["size"],
            "artifact_count": len(layers) + 2}


def prepare(root):
    root.mkdir(mode=0o700)
    rows = {n: snapshot(root / n, n) for n, _ in CASES}
    write(root / "fixtures.json", a.canonical(rows))
    return rows


def create_large(path):
    generator, h, total = random.Random(POLICY["fresh_seed"]), hashlib.sha256(), 0
    with path.open("xb", buffering=0) as stream:
        path.chmod(0o600)
        while total < POLICY["model_bytes"]:
            block = generator.randbytes(a.CHUNK)
            if total == 0:
                block = b"GGUF\x03\0\0\0" + b"\0" * 16 + block[24:]
            pending = memoryview(block)
            while pending:
                count = stream.write(pending)
                if not count:
                    raise OSError("Incomplete pinned fixture write")
                pending = pending[count:]
            h.update(block)
            total += len(block)
        os.fsync(stream.fileno())
    return {"mediaType": a.MODEL, "digest": "sha256:" + h.hexdigest(), "size": total,
            "path": str(path), "bytes_written": total, "blocks_512": path.stat().st_blocks,
            "real_model_weights": False, "GGUF_tensors": 0}


def _limited_worker(pipe, root, pin):
    try:
        _, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (24, hard))
        a.verify_core(root, pin, a.Budget(seconds=5), time.monotonic() + 5, strategy="windowed-pinned")
        result = "ok"
    except a.StoreRejected as exc:
        result = exc.code
    try:
        pipe.send_bytes(a.canonical({"outcome": result}))
    finally:
        pipe.close()


def limited_case(root, pin):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_limited_worker, args=(child, str(root), pin))
    try:
        process.start()
        child.close()
        if not parent.poll(5):
            return "deadline"
        value = a.strict_json(parent.recv_bytes(1024))
        process.join(timeout=0.5)
        if process.is_alive() or process.exitcode != 0:
            return "worker"
        return value["outcome"]
    finally:
        parent.close()
        child.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
        process.close()


def run_cases(root, writable):
    info = json.loads((Path(root) / "fixtures.json").read_bytes())
    rows = []
    for name, expected in CASES:
        calls = [0]

        def cancelled():
            calls[0] += 1
            return calls[0] >= 3

        path = Path(writable) if name == "P11_writable" else Path(root) / name
        started, proof = time.monotonic(), None
        if name == "P13_descriptor_exhaustion":
            outcome = limited_case(path, info[name]["manifest_digest"])
        else:
            try:
                proof = a.supervised_verify(path, info[name]["manifest_digest"], a.Budget(seconds=5),
                                            strategy="windowed-pinned", cancelled=cancelled if name == "P12_cancel_after_start" else None)
                outcome = "ok"
            except a.StoreRejected as exc:
                outcome = exc.code
        rows.append({"id": name, "expected": expected, "observed": outcome, "proof": proof,
                     "info": info[name], "elapsed_seconds": time.monotonic() - started,
                     "children_reaped": not multiprocessing.active_children()})
    return {"schema": "pinned-cases-v1", "cases": rows, "attempts": 1,
            "matches": sum(r["observed"] == r["expected"] and r["children_reaped"] for r in rows)}


def grade_cases(report):
    if (report["schema"] != "pinned-cases-v1" or report["attempts"] != 1
            or report["matches"] != len(CASES) or len(report["cases"]) != len(CASES)):
        raise ValueError("Pinned case inventory rejected")
    for row, (name, expected) in zip(report["cases"], CASES):
        if (row["id"] != name or row["observed"] != expected or row["expected"] != expected
                or not row["children_reaped"] or not 0 <= row["elapsed_seconds"] < 8):
            raise ValueError("Pinned case outcome rejected")
        if expected == "ok":
            a.validate_proof(row["proof"], row["info"]["manifest_digest"], a.Budget(seconds=5), strategy="windowed-pinned")
            if (row["proof"]["mapped_model_digest"] != row["info"]["model_digest"]
                    or row["proof"]["mapped_bytes"] != row["info"]["model_bytes"]
                    or row["proof"]["retained_blob_descriptors"] != row["info"]["artifact_count"]):
                raise ValueError("Pinned identity rejected")
        elif row["proof"] is not None:
            raise ValueError("Rejected pinned case produced proof")
    return {"passed": len(CASES), "total": len(CASES)}


def run_profile(root, pin, profile, verify):
    def job(ident):
        started, proofs, error = time.monotonic(), [], None
        deadline = started + 60
        for _ in ("pre", "post"):
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise a.StoreRejected("deadline")
                proofs.append(verify(root, pin, a.Budget(seconds=min(60, remaining))))
            except ValueError as exc:
                error = getattr(exc, "code", "worker")
                break
        return {"id": ident, "proofs": proofs, "elapsed_seconds": time.monotonic() - started, "error": error}
    single = job("single")
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        jobs = list(pool.map(job, range(5)))
    return {"schema": "pinned-profile-v1", "profile": profile, "single": single, "jobs": jobs,
            "wave_elapsed_seconds": time.monotonic() - started, "attempts": 1,
            "children_reaped": not multiprocessing.active_children(), "cache_condition": POLICY["cache_condition"]}


def grade_profile(report, info):
    profile = report["profile"]
    if (profile not in POLICY["order"] or report["schema"] != "pinned-profile-v1"
            or report["attempts"] != 1 or not report["children_reaped"]
            or report["cache_condition"] != POLICY["cache_condition"] or report["single"]["id"] != "single"
            or len(report["jobs"]) != 5 or [r["id"] for r in report["jobs"]] != list(range(5))):
        raise ValueError("Pinned profile inventory rejected")
    rows, identities, total = [report["single"], *report["jobs"]], set(), 0
    for row in rows:
        if not 0 <= row["elapsed_seconds"] < 63 or len(row["proofs"]) > 2:
            raise ValueError("Pinned job observation rejected")
        for proof in row["proofs"]:
            a.validate_proof(proof, info["manifest_digest"], a.Budget(seconds=60),
                             strategy="windowed-pinned" if profile == "candidate" else "stream")
            if sum(v["digest"] == info["model_digest"] and v["bytes"] == POLICY["model_bytes"] for v in proof["artifacts"]) != 1:
                raise ValueError("Fresh pinned full-size artifact required")
            if profile == "candidate" and (proof["mapped_bytes"] != POLICY["model_bytes"]
                                            or proof["mapped_windows"] != 512
                                            or proof["retained_blob_descriptors"] != info["artifact_count"]):
                raise ValueError("Full pinned mapped coverage required")
            identities.add(proof["content_identity_sha256"])
            total += proof["bytes_hashed"]
    if len(identities) > 1:
        raise ValueError("Mixed pinned snapshot identities")
    complete = all(r["error"] is None and len(r["proofs"]) == 2 for r in rows)
    return {"completed_verifications": sum(len(r["proofs"]) for r in rows), "total_bytes_hashed": total,
            "hard_budget_pass": complete and all(r["elapsed_seconds"] < 60 for r in rows) and report["wave_elapsed_seconds"] < 75,
            "twenty_second_pre_post_target_pass": complete and all(r["elapsed_seconds"] <= 20 for r in rows),
            "memory_target_pass": complete and all(p["peak_rss_kib"] <= 128 * 1024 for r in rows for p in r["proofs"]),
            "native_inference_qualified": False, "research_jobs_qualified": False}
