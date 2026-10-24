"""Invented snapshot qualification only; no provider, inference or live-store access."""

import concurrent.futures
import hashlib
import json
import multiprocessing
import os
import random
import shutil
import time
from pathlib import Path

import artifact_store as a

CASES = [
    ("valid", "ok"), ("writable", "readonly"), ("root_link", "root"),
    ("blobs_link", "root"), ("manifest_link", "links"), ("config_link", "links"),
    ("model_link", "links"), ("config_hardlink", "links"), ("model_hardlink", "links"),
    ("missing_config", "missing"), ("missing_model", "missing"),
    ("corrupt_manifest", "digest"), ("corrupt_config", "digest"), ("corrupt_model", "digest"),
    ("wrong_size", "size"), ("boolean_size", "descriptor"), ("duplicate_layer", "duplicates"),
    ("duplicate_json_key", "invalid"), ("remote", "remote"), ("manifest_list", "manifest"),
    ("adapter", "model_type"), ("projector", "model_type"), ("bad_header", "gguf_header"),
    ("bad_version", "gguf_header"), ("extra_blob", "inventory"), ("alias", "inventory"),
    ("extra_root", "inventory"), ("root_mode", "permissions"), ("file_mode", "links"),
    ("byte_budget", "byte_budget"), ("deadline", "deadline"), ("cancelled", "cancelled"),
    ("bad_config", "config"), ("bad_rootfs", "config"), ("foreign_digest", "manifest_identity"),
    ("config_oversize", "size"), ("model_directory", "links"), ("model_fifo", "links"),
]
POLICY = {
    "schema": "artifact-store-qualification-v1", "cases": [dict(id=n, expected=v) for n, v in CASES],
    "chunk_bytes": a.CHUNK, "max_model_bytes": a.MAX_MODEL, "max_total_bytes": a.MAX_TOTAL,
    "small_case_seconds": 5, "large_model_bytes": 8 * a.GIB,
    "large_verification_seconds": 60, "shared_pre_post_job_seconds": 60,
    "five_job_wave_seconds": 75, "pre_post_target_seconds": 20,
    "peak_worker_rss_limit_kib": 128 * 1024, "jobs": 5,
    "attempts": 1, "cold_cache_qualified": False, "native_inference_qualified": False,
}


def write(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def descriptor(media, raw):
    return {"mediaType": media, "digest": "sha256:" + a.digest(raw), "size": len(raw)}


def snapshot(root, variant="valid", *, large=None):
    """Fresh local fixture. Padding is arbitrary bytes, not model tensor data."""
    if root.exists() or root.is_symlink() or root.parent != root.parent.resolve():
        raise ValueError("Fresh unlinked fixture destination required")
    root.mkdir(mode=0o700)
    for d in ("blobs", "manifests", "manifests-v2"):
        (root / d).mkdir(mode=0o700)
    model = b"GGUF\x03\0\0\0" + b"\0" * 16 + b"invented padding only"
    if variant == "bad_header":
        model = b"FAIL" + model[4:]
    if variant == "bad_version":
        model = model[:4] + b"\x09\0\0\0" + model[8:]
    md = {k: large[k] for k in ("mediaType", "digest", "size")} if large else descriptor(a.MODEL, model)
    config = {"model_format": "gguf", "model_family": "llama", "model_families": ["llama"],
              "rootfs": {"type": "layers", "diff_ids": [md["digest"]]}}
    if variant == "remote":
        config["remote_host"] = "https://example.invalid"
    if variant == "bad_config":
        config["unexpected"] = "forbidden"
    if variant == "bad_rootfs":
        config["rootfs"]["diff_ids"] = ["sha256:" + "f" * 64]
    cr = a.canonical(config)
    if variant == "config_oversize":
        cr += b" " * a.META
    cd = descriptor(a.CONFIG, cr)
    manifest = {"schemaVersion": 2, "mediaType": a.MANIFEST, "config": cd, "layers": [dict(md)]}
    if variant == "wrong_size":
        manifest["layers"][0]["size"] += 1
    if variant == "boolean_size":
        manifest["layers"][0]["size"] = True
    if variant == "duplicate_layer":
        manifest["layers"].append(dict(md))
    if variant in {"adapter", "projector"}:
        manifest["layers"].append({"mediaType": "application/vnd.ollama.image." + variant,
                                   "digest": "sha256:" + a.digest(b"invented extra"), "size": 14})
    raw = a.canonical(manifest)
    if variant == "manifest_list":
        raw = a.canonical({"schemaVersion": 2, "manifests": []})
    if variant == "duplicate_json_key":
        raw = raw[:-1] + b',"schemaVersion":2}'
    pin = "sha256:" + a.digest(raw)
    blobs = {pin: raw, cd["digest"]: cr}
    if not large:
        blobs[md["digest"]] = model
    if variant in {"adapter", "projector"}:
        blobs[manifest["layers"][-1]["digest"]] = b"invented extra"
    for ref, content in blobs.items():
        write(root / "blobs" / ref.replace(":", "-"), content)
    if large:
        shutil.copyfile(large["path"], root / "blobs" / md["digest"].replace(":", "-"))
        (root / "blobs" / md["digest"].replace(":", "-")).chmod(0o600)
    def target(ref):
        return root / "blobs" / ref.replace(":", "-")
    refs = {"manifest": pin, "config": cd["digest"], "model": md["digest"]}
    for kind, ref in refs.items():
        p = target(ref)
        if variant == "missing_" + kind:
            p.unlink()
        if variant == "corrupt_" + kind:
            write(p, p.read_bytes()[:-1] + b"!")
        if variant == kind + "_link":
            p.unlink()
            p.symlink_to("/definitely-absent-invented-target")
        if variant == kind + "_hardlink":
            os.link(p, root.parent / (root.name + "-" + kind + "-link"))
    if variant == "blobs_link":
        shutil.rmtree(root / "blobs")
        (root / "blobs").symlink_to("/definitely-absent-invented-target")
    if variant == "extra_blob":
        write(root / "blobs" / ("sha256-" + "e" * 64), b"unused")
    if variant == "alias":
        write(root / "manifests" / "invented-alias", raw)
    if variant == "extra_root":
        write(root / "extra", b"unused")
    if variant == "root_mode":
        root.chmod(0o755)
    if variant == "file_mode":
        target(md["digest"]).chmod(0o644)
    if variant in {"model_directory", "model_fifo"}:
        p = target(md["digest"])
        p.unlink()
        p.mkdir(mode=0o700) if variant == "model_directory" else os.mkfifo(p, 0o600)
    if variant == "foreign_digest":
        pin = "sha256:" + "F" * 64
    return {"manifest_digest": pin, "model_digest": md["digest"], "variant": variant}


def prepare(parent):
    parent.mkdir(mode=0o700)
    rows = {}
    for name, _ in CASES:
        if name == "root_link":
            (parent / name).symlink_to("valid", target_is_directory=True)
            rows[name] = {**rows["valid"], "variant": name}
        else:
            rows[name] = snapshot(parent / name, name)
    write(parent / "fixtures.json", a.canonical(rows))
    return rows


def run_cases(readonly_root, writable_root):
    info = json.loads((Path(readonly_root) / "fixtures.json").read_bytes())
    rows = []
    for name, expected in CASES:
        root = Path(writable_root) if name == "writable" else Path(readonly_root) / name
        seconds = 0.000001 if name == "deadline" else POLICY["small_case_seconds"]
        budget = a.Budget(1 if name == "byte_budget" else a.MAX_TOTAL, seconds)
        started = time.monotonic()
        try:
            proof = a.supervised_verify(root, info[name]["manifest_digest"], budget,
                                        cancelled=(lambda: True) if name == "cancelled" else None)
            outcome = "ok"
        except a.StoreRejected as exc:
            outcome, proof = exc.code, None
        rows.append({"id": name, "expected": expected, "observed": outcome,
                     "matches": outcome == expected, "proof": proof,
                     "elapsed_seconds": time.monotonic() - started,
                     "children_reaped": not multiprocessing.active_children()})
    return {"schema": "artifact-store-cases-v1", "cases": rows, "attempts": 1,
            "passed": sum(r["matches"] and r["children_reaped"] for r in rows), "total": len(CASES),
            "provider_requests": 0, "native_inference_calls": 0}


def run_budgets(root, pin):
    def job(ident):
        started, proofs = time.monotonic(), []
        deadline = started + POLICY["shared_pre_post_job_seconds"]
        error = None
        for _ in ("pre", "post"):
            try:
                remaining = min(POLICY["large_verification_seconds"], deadline - time.monotonic())
                if remaining <= 0:
                    raise a.StoreRejected("deadline")
                proofs.append(a.supervised_verify(root, pin, a.Budget(a.MAX_TOTAL, remaining)))
            except a.StoreRejected as exc:
                error = exc.code
                break
        elapsed = time.monotonic() - started
        return {"id": ident, "proofs": proofs, "elapsed_seconds": elapsed, "error": error,
                "within_job_limit": error is None and len(proofs) == 2 and elapsed < POLICY["shared_pre_post_job_seconds"],
                "within_pre_post_target": error is None and len(proofs) == 2 and elapsed <= POLICY["pre_post_target_seconds"],
                "within_rss_target": len(proofs) == 2 and all(p["peak_rss_kib"] <= POLICY["peak_worker_rss_limit_kib"] for p in proofs)}
    single = job("single")
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=POLICY["jobs"]) as pool:
        jobs = list(pool.map(job, range(POLICY["jobs"])))
    elapsed = time.monotonic() - started
    return {"schema": "artifact-store-budgets-v1", "single": single, "jobs": jobs,
            "wave_elapsed_seconds": elapsed, "within_wave_limit": elapsed < POLICY["five_job_wave_seconds"],
            "children_reaped": not multiprocessing.active_children(), "attempts": 1,
            "cache_condition": "warm_creation_and_prior_read_no_cache_eviction",
            "cold_cache_qualified": False, "native_inference_qualified": False, "research_jobs_qualified": False}


def create_large(path):
    """Fully write/fsync 8 GiB; no sparse allocation, truncation or real weights."""
    total, h, count = POLICY["large_model_bytes"], hashlib.sha256(), 0
    generator = random.Random(20261024)
    with path.open("xb", buffering=0) as stream:
        path.chmod(0o600)
        while count < total:
            block = generator.randbytes(a.CHUNK)
            if count == 0:
                block = b"GGUF\x03\0\0\0" + b"\0" * 16 + block[24:]
            pending = memoryview(block)
            while pending:
                written = stream.write(pending)
                if not written:
                    raise OSError("Incomplete synthetic fixture write")
                pending = pending[written:]
            h.update(block)
            count += len(block)
        os.fsync(stream.fileno())
    return {"mediaType": a.MODEL, "digest": "sha256:" + h.hexdigest(), "size": count,
            "path": str(path), "bytes_written": count, "blocks_512": path.stat().st_blocks,
            "real_model_weights": False, "GGUF_tensors": 0}


def grade_cases(report):
    if (set(report) != {"schema", "cases", "attempts", "passed", "total", "provider_requests", "native_inference_calls"}
            or report["schema"] != "artifact-store-cases-v1" or report["attempts"] != 1
            or report["passed"] != report["total"] or report["total"] != len(CASES)
            or report["provider_requests"] != 0 or report["native_inference_calls"] != 0
            or len(report["cases"]) != len(CASES)):
        raise ValueError("Case report rejected")
    for row, (name, expected) in zip(report["cases"], CASES):
        if (row["id"] != name or row["expected"] != expected or row["observed"] != expected
                or row["matches"] is not True or row["children_reaped"] is not True
                or not 0 <= row["elapsed_seconds"] < POLICY["small_case_seconds"] + 3):
            raise ValueError("Case result rejected")
        if name == "valid":
            a.validate_proof(row["proof"], row["proof"]["manifest_digest"], a.Budget(seconds=5))
        elif row["proof"] is not None:
            raise ValueError("Rejected case produced proof")
    return {"passed": len(CASES), "total": len(CASES), "kernel_readonly_qualification": True}


def grade_budgets(report, pin):
    if (report["schema"] != "artifact-store-budgets-v1" or report["attempts"] != 1
            or len(report["jobs"]) != POLICY["jobs"]
            or [r["id"] for r in report["jobs"]] != list(range(POLICY["jobs"]))
            or report["single"]["id"] != "single" or not report["children_reaped"]
            or report["cache_condition"] != "warm_creation_and_prior_read_no_cache_eviction"
            or any(report[k] is not False for k in ("cold_cache_qualified", "native_inference_qualified", "research_jobs_qualified"))):
        raise ValueError("Budget report rejected")
    rows = [report["single"], *report["jobs"]]
    identities, byte_counts = set(), set()
    for row in rows:
        hard = row["error"] is None and len(row["proofs"]) == 2 and row["elapsed_seconds"] < POLICY["shared_pre_post_job_seconds"]
        target = row["error"] is None and len(row["proofs"]) == 2 and row["elapsed_seconds"] <= POLICY["pre_post_target_seconds"]
        memory = len(row["proofs"]) == 2 and all(p["peak_rss_kib"] <= POLICY["peak_worker_rss_limit_kib"] for p in row["proofs"])
        if (row["within_job_limit"] is not hard or row["within_pre_post_target"] is not target
                or row["within_rss_target"] is not memory or not 0 <= row["elapsed_seconds"] < 63):
            raise ValueError("Budget result rejected")
        for proof in row["proofs"]:
            a.validate_proof(proof, pin, a.Budget(seconds=60))
            if (not a.MAX_MODEL < proof["bytes_hashed"] < a.MAX_MODEL + 2 * a.META
                    or sum(v["bytes"] == a.MAX_MODEL for v in proof["artifacts"]) != 1):
                raise ValueError("Full-size artifact proof required")
            identities.add(proof["content_identity_sha256"])
            byte_counts.add(proof["bytes_hashed"])
    if len(identities) > 1 or len(byte_counts) > 1:
        raise ValueError("Mixed artifact identity")
    wave = report["wave_elapsed_seconds"] < POLICY["five_job_wave_seconds"]
    if report["within_wave_limit"] is not wave:
        raise ValueError("Wave budget rejected")
    return {"completed_verifications": sum(len(r["proofs"]) for r in rows),
            "hard_budget_pass": wave and all(r["within_job_limit"] for r in rows),
            "twenty_second_pre_post_target_pass": all(r["within_pre_post_target"] for r in rows),
            "memory_target_pass": all(r["within_rss_target"] for r in rows),
            "native_inference_qualified": False, "research_jobs_qualified": False}
