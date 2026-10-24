"""Owned disposable VM-volume profile; never mounted into the application."""

import hashlib
import os
import random
from pathlib import Path

import artifact_store as a
import pinned_store_qualification as q

POLICY = {"schema": "vm-volume-store-acceptance-v1", "fresh_seed": 20261028,
          "filesystem": "ext4", "model_bytes": 8 * a.GIB, "window_bytes": 16 * 1024**2,
          "pre_post_target_seconds": 20, "shared_job_seconds": 60, "wave_seconds": 75,
          "rss_kib": 128 * 1024, "cpu_limit": 2, "memory_limit_mib": 768, "jobs": 5,
          "order": ["candidate", "baseline"], "attempts_per_profile": 1,
          "storage": "new_owned_VM_local_volume_readonly_after_preparer_exit",
          "preparation_flush_bytes": 64 * 1024**2, "preparation_model_copies": 0,
          "marker": "lawyer-disposable-windowed-volume-v1",
          "native_inference_qualified": False, "cold_cache_qualified": False}


def require_marker():
    marker = Path("/run/qualification/owned-disposable")
    if not marker.is_file() or marker.read_bytes() != POLICY["marker"].encode():
        raise ValueError("Disposable volume marker required")


def filesystem(mountpoint):
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        if left.split()[4] == mountpoint:
            return right.split()[0]
    raise ValueError("Expected qualification mount absent")


def prepare_volume(uid, gid):
    require_marker()
    if type(uid) is not int or uid <= 0 or type(gid) is not int or gid < 0:
        raise ValueError("Nonroot qualification owner required")
    root = Path("/store")
    if os.getuid() != 0 or filesystem("/store") != "ext4" or list(root.iterdir()):
        raise ValueError("New empty owned ext4 test volume required")
    source = root / "invented-staging.bin"
    h, generator, total = hashlib.sha256(), random.Random(POLICY["fresh_seed"]), 0
    with source.open("xb", buffering=0) as stream:
        source.chmod(0o600)
        while total < POLICY["model_bytes"]:
            block = generator.randbytes(a.CHUNK)
            if total == 0:
                block = b"GGUF\x03\0\0\0" + b"\0" * 16 + block[24:]
            pending = memoryview(block)
            while pending:
                count = stream.write(pending)
                if not count:
                    raise OSError("Incomplete VM fixture write")
                pending = pending[count:]
            h.update(block)
            total += len(block)
            if total % POLICY["preparation_flush_bytes"] == 0:
                os.fsync(stream.fileno())
                os.posix_fadvise(stream.fileno(), total - POLICY["preparation_flush_bytes"],
                                 POLICY["preparation_flush_bytes"], os.POSIX_FADV_DONTNEED)
        os.fsync(stream.fileno())
    snapshot = root / "large"
    snapshot.mkdir(mode=0o700)
    for name in ("blobs", "manifests", "manifests-v2"):
        (snapshot / name).mkdir(mode=0o700)
    md = {"mediaType": a.MODEL, "digest": "sha256:" + h.hexdigest(), "size": total}
    texts = [b"Invented VM volume packet seed 20261028; " + str(n).encode() for n in range(3)]
    layers = [md, *[q.descriptor("application/vnd.ollama.image." + kind, raw)
                    for kind, raw in zip(("template", "system", "license"), texts)]]
    cr = a.canonical({"model_format": "gguf", "model_family": "llama", "model_families": ["llama"],
                      "rootfs": {"type": "layers", "diff_ids": [v["digest"] for v in layers]}})
    cd = q.descriptor(a.CONFIG, cr)
    mr = a.canonical({"schemaVersion": 2, "mediaType": a.MANIFEST, "config": cd, "layers": layers})
    pin = "sha256:" + a.digest(mr)
    for ref, raw in [(pin, mr), (cd["digest"], cr), *[(v["digest"], raw) for v, raw in zip(layers[1:], texts)]]:
        q.write(snapshot / "blobs" / ref.replace(":", "-"), raw)
    model = snapshot / "blobs" / md["digest"].replace(":", "-")
    source.rename(model)
    info = {"manifest_digest": pin, "model_digest": md["digest"], "model_bytes": total, "artifact_count": 6}
    with model.open("rb") as stream:
        if "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest() != info["model_digest"]:
            raise ValueError("VM fixture copy identity mismatch")
    blocks = model.stat().st_blocks
    if total != 8 * a.GIB or blocks * 512 < total:
        raise ValueError("Fully allocated VM fixture required")
    q.write(root / "large-info.json", a.canonical(info))
    nodes = sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True)
    for path in [*nodes, root]:
        if path.is_symlink():
            raise ValueError("No qualification links permitted")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        path.chmod(0o700 if path.is_dir() else 0o600)
        os.chown(path, uid, gid)
    return {"info": info, "fresh_seed": POLICY["fresh_seed"], "bytes_written": total,
            "model_blocks_512": blocks, "stored_digest_verified": True, "fsynced": True, "model_copies": 0,
            "filesystem": "ext4", "owner_uid": uid, "owner_gid": gid,
            "real_model_weights": False, "GGUF_tensors": 0}


def grade(report, info):
    if (report["schema"] != "vm-volume-profiles-v1" or report["filesystem"] != "ext4"
            or report["kernel_readonly"] is not True or report["order"] != POLICY["order"]):
        raise ValueError("VM volume envelope rejected")
    result = {name: q.grade_profile(report[name], info) for name in POLICY["order"]}
    identities = {p["content_identity_sha256"] for name in POLICY["order"]
                  for row in [report[name]["single"], *report[name]["jobs"]] for p in row["proofs"]}
    if len(identities) != 1:
        raise ValueError("VM profiles did not share one exact snapshot")
    return result
