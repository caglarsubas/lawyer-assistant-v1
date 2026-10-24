"""Bounded read-only single-model store verification; no startup or live-store access."""

import hashlib
import json
import mmap
import multiprocessing
import os
import re
import resource
import stat
import struct
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from metadata_phase_probe import strict_json

GIB = 1024**3
CHUNK = 1024 * 1024
WINDOW = 16 * CHUNK
META = 65536
MAX_MODEL = 8 * GIB
MAX_TOTAL = 9 * GIB
MODEL = "application/vnd.ollama.image.model"
CONFIG = "application/vnd.docker.container.image.v1+json"
MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
TEXT = {"application/vnd.ollama.image." + v for v in ("template", "system", "params", "license")}
SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")


class StoreRejected(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("Artifact store rejected: " + code)


@dataclass(frozen=True)
class Budget:
    max_bytes: int = MAX_TOTAL
    seconds: float = 20.0

    def validate(self):
        if (type(self.max_bytes) is not int or not 0 < self.max_bytes <= MAX_TOTAL
                or type(self.seconds) not in {int, float} or not 0 < self.seconds <= 60):
            raise StoreRejected("budget")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def readonly(fd):
    return bool(os.fstatvfs(fd).f_flag & os.ST_RDONLY)


def names(fd, limit):
    result = set()
    with os.scandir(fd) as entries:
        for entry in entries:
            result.add(entry.name)
            if len(result) > limit:
                raise StoreRejected("inventory")
    return result


def validate_strategy(strategy):
    if type(strategy) is not str or strategy not in {"stream", "windowed", "windowed-pinned"}:
        raise StoreRejected("strategy")


def blocks(stream, size, strategy, *, check=None):
    """A mapped block stays live only until its consumer advances or closes."""
    validate_strategy(strategy)
    if strategy in {"windowed", "windowed-pinned"}:
        for offset in range(0, size, WINDOW):
            if check is not None:
                check()
            with mmap.mmap(stream.fileno(), min(WINDOW, size - offset),
                           access=mmap.ACCESS_READ, offset=offset) as block:
                yield block
    else:
        while True:
            if check is not None:
                check()
            block = stream.read(CHUNK)
            if not block:
                break
            yield block


def config_valid(config, layer_digests):
    allowed = {"model_format", "model_family", "model_families", "model_type", "file_type",
               "architecture", "os", "rootfs", "remote_host", "remote_model"}
    if not isinstance(config, dict) or set(config) - allowed or config.get("model_format") != "gguf":
        raise StoreRejected("config")
    if config.get("remote_host", "") != "" or config.get("remote_model", "") != "":
        raise StoreRejected("remote")
    for key in allowed - {"rootfs", "model_families"}:
        if key in config and (not isinstance(config[key], str) or len(config[key]) > 128):
            raise StoreRejected("config")
    if "model_families" in config:
        v = config["model_families"]
        if (not isinstance(v, list) or not 1 <= len(v) <= 8
                or any(not isinstance(s, str) or not 0 < len(s) <= 64 for s in v)
                or len(set(v)) != len(v)):
            raise StoreRejected("config")
    if "rootfs" in config and config["rootfs"] != {"type": "layers", "diff_ids": layer_digests}:
        raise StoreRejected("config")


def verify_core(root, manifest_digest, budget, deadline, *, clock=time.monotonic, strategy="stream"):
    """Observe one closed read-only snapshot; a proof is not indefinite trust."""
    budget.validate()
    validate_strategy(strategy)
    if not isinstance(manifest_digest, str) or not SHA.fullmatch(manifest_digest):
        raise StoreRejected("manifest_identity")
    root = Path(root).absolute()
    if len(str(root)) > 1024 or root != root.resolve():
        raise StoreRejected("root")
    opened, directories, file_states, artifacts = [], {}, {}, []
    consumed = 0
    mapped = {"windows": 0, "bytes": 0, "digest": None}
    started = clock()

    def check():
        if clock() >= deadline:
            raise StoreRejected("deadline")

    def directory(path, *, parent=None):
        check()
        try:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=parent)
        except OSError:
            raise StoreRejected("root") from None
        opened.append(fd)
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise StoreRejected("permissions")
        if not readonly(fd):
            raise StoreRejected("readonly")
        directories[fd] = identity(info)
        return fd

    def blob(reference, size=None, *, collect=False, model=False):
        nonlocal consumed
        check()
        if not isinstance(reference, str) or not SHA.fullmatch(reference):
            raise StoreRejected("descriptor")
        name = reference.replace(":", "-")
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                         dir_fd=blobs_fd)
        except FileNotFoundError:
            raise StoreRejected("missing") from None
        except OSError:
            raise StoreRejected("links") from None
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            os.close(fd)
            raise StoreRejected("links")
        pin = strategy == "windowed-pinned"
        if pin:
            opened.append(fd)
        stream_fd = os.dup(fd) if pin else fd
        with os.fdopen(stream_fd, "rb", buffering=0) as stream:
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                    or before.st_dev != os.fstat(blobs_fd).st_dev):
                raise StoreRejected("links")
            if not readonly(fd):
                raise StoreRejected("readonly")
            maximum = META if collect else MAX_MODEL if model else CHUNK
            if not 0 < before.st_size <= maximum or (size is not None and before.st_size != size):
                raise StoreRejected("size")
            if consumed + before.st_size > budget.max_bytes:
                raise StoreRejected("byte_budget")
            count, h, parts, head = 0, hashlib.sha256(), [], b""
            reader = "windowed" if model and strategy != "stream" else "stream"
            with closing(blocks(stream, before.st_size, reader, check=check)) as chunks:
                for block in chunks:
                    check()
                    count += len(block)
                    consumed += len(block)
                    if consumed > budget.max_bytes or count > before.st_size:
                        raise StoreRejected("byte_budget")
                    h.update(block)
                    if len(head) < 24:
                        head += block[:24 - len(head)]
                    if collect:
                        parts.append(block)
                    if reader == "windowed":
                        mapped["windows"] += 1
                        mapped["bytes"] += len(block)
                        mapped["digest"] = reference
            check()
            after = os.fstat(fd)
            entry = os.stat(name, dir_fd=blobs_fd, follow_symlinks=False)
            if identity(before) != identity(after) or identity(after) != identity(entry):
                raise StoreRejected("changed")
            if count != before.st_size or h.hexdigest() != reference[7:]:
                raise StoreRejected("digest")
            if model and (len(head) != 24 or head[:4] != b"GGUF" or struct.unpack("<I", head[4:8])[0] not in {2, 3}):
                raise StoreRejected("gguf_header")
            file_states[name] = (identity(after), fd if pin else None)
            artifacts.append({"digest": reference, "bytes": count})
            return b"".join(parts)

    try:
        root_fd = directory(root)
        root_start = identity(os.stat(root, follow_symlinks=False))
        if root_start != directories[root_fd] or names(root_fd, 3) != {"blobs", "manifests", "manifests-v2"}:
            raise StoreRejected("inventory")
        blobs_fd = directory("blobs", parent=root_fd)
        child_directories = {"blobs": blobs_fd}
        for name in ("manifests", "manifests-v2"):
            fd = directory(name, parent=root_fd)
            child_directories[name] = fd
            if names(fd, 0):
                raise StoreRejected("aliases")
        initial_names = names(blobs_fd, 18)
        raw = blob(manifest_digest, collect=True)
        manifest = strict_json(raw)
        if (not isinstance(manifest, dict) or set(manifest) != {"schemaVersion", "mediaType", "config", "layers"}
                or type(manifest["schemaVersion"]) is not int or manifest["schemaVersion"] != 2
                or manifest["mediaType"] != MANIFEST or not isinstance(manifest["layers"], list)
                or not 1 <= len(manifest["layers"]) <= 16):
            raise StoreRejected("manifest")
        descriptors = [manifest["config"], *manifest["layers"]]
        for desc in descriptors:
            if (not isinstance(desc, dict) or set(desc) != {"mediaType", "digest", "size"}
                    or not isinstance(desc["digest"], str) or not SHA.fullmatch(desc["digest"])
                    or type(desc["size"]) is not int or desc["size"] <= 0):
                raise StoreRejected("descriptor")
        layer_digests = [v["digest"] for v in manifest["layers"]]
        refs = [v["digest"] for v in descriptors]
        if len(set(refs)) != len(refs) or manifest_digest in refs:
            raise StoreRejected("duplicates")
        expected_names = {v.replace(":", "-") for v in [manifest_digest, *refs]}
        if initial_names != expected_names:
            if expected_names - initial_names:
                raise StoreRejected("missing")
            raise StoreRejected("inventory")
        if sum(v["size"] for v in descriptors) + len(raw) > budget.max_bytes:
            raise StoreRejected("byte_budget")
        if manifest["config"]["mediaType"] != CONFIG:
            raise StoreRejected("config")
        if sum(v["mediaType"] == MODEL for v in manifest["layers"]) != 1:
            raise StoreRejected("model_type")
        if any(v["mediaType"] not in TEXT | {MODEL} for v in manifest["layers"]):
            raise StoreRejected("model_type")
        config = strict_json(blob(manifest["config"]["digest"], manifest["config"]["size"], collect=True))
        config_valid(config, layer_digests)
        for desc in manifest["layers"]:
            blob(desc["digest"], desc["size"], model=desc["mediaType"] == MODEL)
        check()
        for name, (saved, pinned_fd) in file_states.items():
            if (identity(os.stat(name, dir_fd=blobs_fd, follow_symlinks=False)) != saved
                    or (pinned_fd is not None and (identity(os.fstat(pinned_fd)) != saved or not readonly(pinned_fd)))):
                raise StoreRejected("changed")
        for fd, saved in directories.items():
            if identity(os.fstat(fd)) != saved or not readonly(fd):
                raise StoreRejected("changed")
        for name, fd in child_directories.items():
            if identity(os.stat(name, dir_fd=root_fd, follow_symlinks=False)) != directories[fd]:
                raise StoreRejected("changed")
        if (identity(os.stat(root, follow_symlinks=False)) != root_start
                or names(blobs_fd, 18) != expected_names or names(root_fd, 3) != {"blobs", "manifests", "manifests-v2"}):
            raise StoreRejected("changed")
        result = {"schema": "readonly-artifact-proof-v1", "manifest_digest": manifest_digest,
                  "artifacts": artifacts, "bytes_hashed": consumed, "kernel_readonly": True,
                  "stable_observation_window": True, "elapsed_seconds": clock() - started,
                  "GGUF_header_only": True, "tensor_layout_or_weights_qualified": False,
                  "executed_weights_qualified": False, "production_activation": False}
        result["content_identity_sha256"] = digest(canonical({"manifest": manifest_digest, "artifacts": artifacts}))
        if strategy in {"windowed", "windowed-pinned"}:
            result.update(schema="readonly-artifact-proof-v2", read_strategy="windowed-v1",
                          mapped_windows=mapped["windows"], mapped_bytes=mapped["bytes"],
                          mapped_model_digest=mapped["digest"])
        if strategy == "windowed-pinned":
            result.update(schema="readonly-artifact-proof-v3", read_strategy="windowed-pinned-v1",
                          retained_blob_descriptors=len(file_states), retained_descriptors_rechecked=True)
        return result
    except StoreRejected:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise StoreRejected("invalid") from None
    finally:
        for fd in reversed(opened):
            os.close(fd)


def _worker(connection, root, manifest_digest, budget, deadline, strategy):
    try:
        proof = verify_core(root, manifest_digest, budget, deadline, strategy=strategy)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        proof["peak_rss_kib"] = int(rss / 1024 if sys.platform == "darwin" else rss)
        result = {"ok": True, "proof": proof}
    except StoreRejected as exc:
        result = {"ok": False, "code": exc.code}
    except Exception:
        result = {"ok": False, "code": "worker"}
    try:
        connection.send_bytes(canonical(result))
    finally:
        connection.close()


def supervised_verify(root, manifest_digest, budget=Budget(), *, cancelled=None, strategy="stream"):
    """One worker/attempt; a late, partial or cancelled result never becomes proof."""
    budget.validate()
    validate_strategy(strategy)
    deadline = time.monotonic() + budget.seconds
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(child, str(root), manifest_digest, budget, deadline, strategy))
    started = False
    try:
        if cancelled is not None and cancelled():
            raise StoreRejected("cancelled")
        process.start()
        started = True
        child.close()
        while True:
            if cancelled is not None and cancelled():
                raise StoreRejected("cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StoreRejected("deadline")
            if parent.poll(min(0.02, remaining)):
                raw = parent.recv_bytes(16384)
                if time.monotonic() >= deadline:
                    raise StoreRejected("deadline")
                result = strict_json(raw)
                process.join(timeout=0.5)
                if process.is_alive() or process.exitcode != 0:
                    raise StoreRejected("worker")
                if not isinstance(result, dict):
                    raise StoreRejected("worker")
                if result.get("ok") is not True:
                    code = result.get("code", "worker")
                    if not isinstance(code, str) or not re.fullmatch("[a-z_]{1,32}", code):
                        code = "worker"
                    raise StoreRejected(code)
                proof = result.get("proof")
                validate_proof(proof, manifest_digest, budget, strategy=strategy)
                if cancelled is not None and cancelled():
                    raise StoreRejected("cancelled")
                if time.monotonic() >= deadline:
                    raise StoreRejected("deadline")
                return proof
            if not process.is_alive():
                raise StoreRejected("worker")
    except (OSError, EOFError, ValueError) as exc:
        if isinstance(exc, StoreRejected):
            raise
        raise StoreRejected("worker") from None
    finally:
        parent.close()
        child.close()
        if started:
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)
            process.close()


def validate_proof(proof, manifest_digest, budget, *, strategy="stream"):
    validate_strategy(strategy)
    keys = {"schema", "manifest_digest", "artifacts", "bytes_hashed", "kernel_readonly",
            "stable_observation_window", "elapsed_seconds", "GGUF_header_only",
            "tensor_layout_or_weights_qualified", "executed_weights_qualified",
            "production_activation", "content_identity_sha256", "peak_rss_kib"}
    version = "readonly-artifact-proof-v1"
    if strategy in {"windowed", "windowed-pinned"}:
        version = "readonly-artifact-proof-v2"
        keys |= {"read_strategy", "mapped_windows", "mapped_bytes", "mapped_model_digest"}
    if strategy == "windowed-pinned":
        version = "readonly-artifact-proof-v3"
        keys |= {"retained_blob_descriptors", "retained_descriptors_rechecked"}
    if (not isinstance(proof, dict) or set(proof) != keys
            or proof["schema"] != version
            or proof["manifest_digest"] != manifest_digest
            or any(proof[k] is not True for k in ("kernel_readonly", "stable_observation_window", "GGUF_header_only"))
            or any(proof[k] is not False for k in ("tensor_layout_or_weights_qualified", "executed_weights_qualified", "production_activation"))
            or type(proof["elapsed_seconds"]) not in {float, int} or not 0 <= proof["elapsed_seconds"] < budget.seconds
            or type(proof["peak_rss_kib"]) is not int or proof["peak_rss_kib"] <= 0
            or not isinstance(proof["artifacts"], list) or not 3 <= len(proof["artifacts"]) <= 18):
        raise StoreRejected("proof")
    refs, total = [], 0
    for item in proof["artifacts"]:
        if (not isinstance(item, dict) or set(item) != {"digest", "bytes"}
                or not isinstance(item["digest"], str) or not SHA.fullmatch(item["digest"])
                or type(item["bytes"]) is not int or not 0 < item["bytes"] <= MAX_MODEL):
            raise StoreRejected("proof")
        refs.append(item["digest"])
        total += item["bytes"]
    if (len(set(refs)) != len(refs) or refs[0] != manifest_digest
            or type(proof["bytes_hashed"]) is not int or proof["bytes_hashed"] != total
            or total > budget.max_bytes
            or proof["content_identity_sha256"] != digest(canonical({"manifest": manifest_digest, "artifacts": proof["artifacts"]}))):
        raise StoreRejected("proof")
    if strategy in {"windowed", "windowed-pinned"}:
        model = next((v for v in proof["artifacts"] if v["digest"] == proof["mapped_model_digest"]), None)
        expected_reader = "windowed-pinned-v1" if strategy == "windowed-pinned" else "windowed-v1"
        if (proof["read_strategy"] != expected_reader or model is None
                or type(proof["mapped_bytes"]) is not int or proof["mapped_bytes"] != model["bytes"]
                or type(proof["mapped_windows"]) is not int
                or proof["mapped_windows"] != (model["bytes"] + WINDOW - 1) // WINDOW):
            raise StoreRejected("proof")
    if strategy == "windowed-pinned" and (type(proof["retained_blob_descriptors"]) is not int
                                           or proof["retained_blob_descriptors"] != len(proof["artifacts"])
                                           or proof["retained_descriptors_rechecked"] is not True):
        raise StoreRejected("proof")
