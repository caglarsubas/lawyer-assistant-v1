"""Trusted operator metadata only: unsigned expectations and read-only reconciliation.

No signer, credential, installation, enrollment or execution authority is accepted.
Paths, API modules, clock and approval hashes are trusted operator inputs, never
HTTP/request fields. Inspect the approved package before importing its API.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path

from controller_stage_manifest import inspect_stage

PACKET_SCHEMA = "operator-enrollment-packet-v1"
OBSERVATION_SCHEMA = "operator-enrollment-observation-v1"
MAX_BYTES, MAX_LIFETIME = 32768, 900
FLAGS = {"trust_enrolled", "runtime_installation_authorized", "native_execution_authorized", "production_activation", "legal_qualification"}
GATES = {"packet", "package", "binding", "public_evidence", "readiness", "stability", "comparison"}
EVIDENCE = {"candidate_sha256", "confirmation_sha256", "binding_context_sha256", "package_manifest_sha256"}
STATUSES = {"blocked", "waiting", "reconciled_for_disposable_mock_validation"}


def reject():
    raise ValueError("Operator evidence rejected")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def decode(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        reject()
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                reject()
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: reject())
    except (ValueError, UnicodeError, RecursionError):
        reject()


def stamp(value):
    if type(value) is not int or not 0 <= value < 2**53:
        reject()
    return value


def token(value, length=64):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{" + str(length) + "}", value):
        reject()
    return value


def label(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value):
        reject()
    return value


def directory(path):
    path = Path(path).absolute()
    info = path.lstat()
    if path != path.resolve() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        reject()
    return path


def read(path):
    path = Path(path)
    directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= MAX_BYTES):
            reject()
        raw = stream.read(MAX_BYTES + 1)
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if len(raw) != before.st_size or identity(before) != identity(os.fstat(stream.fileno())) or identity(before) != identity(path.lstat()):
            reject()
        return raw


def retain(path, raw):
    """Exclusive owner-only write; never replace a packet or historical observation."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        reject()
    path = Path(path)
    directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {"sha256": sha(raw), "unsigned_metadata_only": True, "trust_enrolled": False}


def validate_packet(raw, approved_sha256, now):
    token(approved_sha256)
    if sha(raw) != approved_sha256:
        reject()
    p = decode(raw)
    if (not isinstance(p, dict) or set(p) != {"schema", "version", "packet_id", "created_at", "expires_at", "scope", "package_manifest_sha256", "binding", "enrollment", *FLAGS}
            or p["schema"] != PACKET_SCHEMA or type(p["version"]) is not int or p["version"] != 1
            or p["scope"] != "read_only_disposable_stage" or any(p[k] is not False for k in FLAGS)):
        reject()
    token(p["packet_id"], 32)
    token(p["package_manifest_sha256"])
    if not stamp(p["created_at"]) <= stamp(now) < stamp(p["expires_at"]) or not 0 < p["expires_at"] - p["created_at"] <= MAX_LIFETIME:
        reject()
    b, e = p["binding"], p["enrollment"]
    if (not isinstance(b, dict) or set(b) != {"journal_id", "operation_id", "record_sha256", "volume_binding_sha256", "pin_sha256"}
            or not isinstance(e, dict) or set(e) != {"issuer_key_id", "fingerprint", "candidate_sha256", "confirmation_sha256", "reviewer", "provisioned_by"}):
        reject()
    for key, value in b.items():
        token(value, 32 if key in {"journal_id", "operation_id"} else 64)
    for key in ("fingerprint", "candidate_sha256"):
        token(e[key])
    if e["confirmation_sha256"] is not None:
        token(e["confirmation_sha256"])
    for key in ("issuer_key_id", "reviewer", "provisioned_by"):
        label(e[key])
    if e["reviewer"] == e["provisioned_by"]:
        reject()
    return p


def packet(expectations, *, packet_id, now, lifetime=MAX_LIFETIME):
    """Create unsigned bytes from independent inputs, never observed-state autofill."""
    if not isinstance(expectations, dict) or set(expectations) != {"package_manifest_sha256", "binding", "enrollment"} or type(lifetime) is not int:
        reject()
    p = {"schema": PACKET_SCHEMA, "version": 1, "packet_id": packet_id, "created_at": stamp(now),
         "expires_at": now + lifetime, "scope": "read_only_disposable_stage", **expectations, **dict.fromkeys(FLAGS, False)}
    raw = encode(p)
    validate_packet(raw, sha(raw), now)  # Structural validation is not independent approval.
    return raw


def public_snapshot(root):
    root = directory(root)
    names = {p.name for p in root.iterdir()}
    if names - {"candidate.json", "key-confirmation.json", "revoked.json"} or "revoked.json" in names:
        reject()  # Never open unexpected private material or a revocation marker.
    result = {key: sha(read(root / filename)) if filename in names else None for key, filename in
              (("candidate_sha256", "candidate.json"), ("confirmation_sha256", "key-confirmation.json"))}
    if result["candidate_sha256"] is None and result["confirmation_sha256"] is not None:
        reject()
    return result


def validate_observation(raw, approved_sha256, packet_sha256):
    if sha(raw) != token(approved_sha256):
        reject()
    o = decode(raw)
    if (not isinstance(o, dict) or set(o) != {"schema", "version", "packet_sha256", "observed_at", "valid_until", "status", "checks", "evidence", "comparison", "read_only", *FLAGS}
            or o["schema"] != OBSERVATION_SCHEMA or type(o["version"]) is not int or o["version"] != 1
            or o["packet_sha256"] != packet_sha256 or o["status"] not in STATUSES or o["read_only"] is not True
            or any(o[k] is not False for k in FLAGS) or not stamp(o["observed_at"]) <= stamp(o["valid_until"])
            or set(o["checks"]) != GATES or any(v not in {"verified", "waiting", "blocked", "not_checked"} for v in o["checks"].values())
            or set(o["evidence"]) != EVIDENCE):
        reject()
    for value in o["evidence"].values():
        if value is not None:
            token(value)
    c = o["comparison"]
    if (not isinstance(c, dict) or set(c) != {"previous_observation_sha256", "outcome", "changed_fields"}
            or c["outcome"] not in {"not_requested", "unchanged", "changed", "not_comparable"}
            or not isinstance(c["changed_fields"], list) or len(c["changed_fields"]) > 5
            or len(set(c["changed_fields"])) != len(c["changed_fields"]) or set(c["changed_fields"]) - (EVIDENCE | {"status"})):
        reject()
    if c["previous_observation_sha256"] is not None:
        token(c["previous_observation_sha256"])
    if o["status"] == "reconciled_for_disposable_mock_validation" and set(o["checks"].values()) != {"verified"}:
        reject()
    return o


def utc():
    return int(time.time())


def reconcile(packet_path, approved_packet_sha256, stage, model_root, journal, binding, trust_root, *, api,
              clock=utc, previous_path=None, approved_previous_sha256=None, checkpoint=None):
    """No writes. Recheck exact files, current anchor, expiry and public trust at exit."""
    result = {"schema": OBSERVATION_SCHEMA, "version": 1, "packet_sha256": None, "observed_at": 0, "valid_until": 0,
              "status": "blocked", "checks": dict.fromkeys(GATES, "not_checked"), "evidence": dict.fromkeys(EVIDENCE),
              "comparison": {"previous_observation_sha256": None, "outcome": "not_requested", "changed_fields": []},
              "read_only": True, **dict.fromkeys(FLAGS, False)}
    gate = "packet"
    try:
        now = stamp(clock())
        result.update(observed_at=now, valid_until=now)
        raw = read(packet_path)
        p = validate_packet(raw, approved_packet_sha256, now)
        result.update(packet_sha256=approved_packet_sha256, valid_until=p["expires_at"])
        result["checks"][gate] = "verified"
        gate = "comparison"
        previous_raw = read(previous_path) if previous_path is not None else None
        if (previous_path is None) != (approved_previous_sha256 is None):
            reject()
        previous = validate_observation(previous_raw, approved_previous_sha256, approved_packet_sha256) if previous_raw is not None else None
        if previous and previous["observed_at"] > now:
            reject()
        result["checks"][gate] = "verified"
        gate = "package"
        inspect_stage(stage, p["package_manifest_sha256"])
        for module in (api.readiness, api.controller, api.control):
            if Path(module.__file__).parent.resolve() != Path(stage).resolve() / "lawyer_provider_stage":
                reject()
        result["evidence"]["package_manifest_sha256"] = p["package_manifest_sha256"]
        result["checks"][gate] = "verified"
        gate = "binding"
        actual = {"journal_id": binding.journal_id, "operation_id": binding.operation_id, "record_sha256": binding.record_sha256,
                  "volume_binding_sha256": binding.volume_binding_sha256, "pin_sha256": sha(binding.pin_bytes)}
        if actual != p["binding"]:
            reject()
        record, before = api.readiness.binding_snapshot(journal, binding)
        result["evidence"]["binding_context_sha256"] = sha(encode({"fence": before, "binding": actual}))
        result["checks"][gate] = "verified"
        gate = "public_evidence"
        public = public_snapshot(trust_root)
        result["evidence"].update(public)
        e = p["enrollment"]
        if ((public["candidate_sha256"] is not None and public["candidate_sha256"] != e["candidate_sha256"])
                or (e["confirmation_sha256"] is not None and public["confirmation_sha256"] is not None and public["confirmation_sha256"] != e["confirmation_sha256"])):
            reject()
        result["checks"][gate] = "verified"
        kwargs = dict(expected_fingerprint=e["fingerprint"], expected_issuer_key_id=e["issuer_key_id"], expected_reviewer=e["reviewer"],
                      provisioned_by=e["provisioned_by"], approved_confirmation_sha256=e["confirmation_sha256"])
        gate = "readiness"
        assessed = api.readiness.assess(stage, p["package_manifest_sha256"], model_root, journal, binding, trust_root, now=now, **kwargs)
        if assessed["status"] not in {"waiting", "ready_for_disposable_mock_validation"}:
            reject()
        result["checks"][gate] = "waiting" if assessed["status"] == "waiting" else "verified"
        gate = "stability"
        if checkpoint is not None:
            checkpoint("before_final_recheck")  # Trusted test/operator hook, never request controlled.
        final_now = stamp(clock())
        if final_now < now:
            reject()
        validate_packet(read(packet_path), approved_packet_sha256, final_now)
        if read(packet_path) != raw or public_snapshot(trust_root) != public:
            reject()
        after_record, after = api.readiness.binding_snapshot(journal, binding)
        if before != after or record != after_record:
            reject()
        enrolled = api.readiness.enrollment(trust_root, fingerprint=e["fingerprint"], issuer=e["issuer_key_id"], reviewer=e["reviewer"],
                                            provisioner=e["provisioned_by"], confirmation_sha=e["confirmation_sha256"], now=final_now)
        if (enrolled == "verified") != (assessed["status"] == "ready_for_disposable_mock_validation"):
            reject()
        if previous_raw is not None and read(previous_path) != previous_raw:
            reject()
        result["checks"][gate] = "verified"
        result["observed_at"] = final_now
        if enrolled == "verified":
            result["valid_until"] = min(p["expires_at"], decode(read(Path(trust_root) / "key-confirmation.json"))["expires_at"])
        final_record, final_fence = api.readiness.binding_snapshot(journal, binding)
        if (record != final_record or before != final_fence or public_snapshot(trust_root) != public or read(packet_path) != raw
                or (previous_raw is not None and read(previous_path) != previous_raw)):
            reject()
        last_now = stamp(clock())
        if not final_now <= last_now < result["valid_until"]:
            reject()
        result["observed_at"] = last_now
        result["status"] = "reconciled_for_disposable_mock_validation" if enrolled == "verified" else "waiting"
        if previous is not None:
            changed = sorted(k for k in EVIDENCE if previous["evidence"][k] != result["evidence"][k])
            if previous["status"] != result["status"]:
                changed.append("status")
            result["comparison"] = {"previous_observation_sha256": approved_previous_sha256,
                                    "outcome": "not_comparable" if previous["status"] == "blocked" else "changed" if changed else "unchanged", "changed_fields": changed}
        return result
    except Exception:
        result["checks"][gate] = "blocked"
        return result  # No identifiers, paths, source bytes, secrets or raw exception messages.


def main():
    parser = argparse.ArgumentParser(description="Create unsigned operator metadata; no enrollment or runtime effects")
    parser.add_argument("expectations_file")
    parser.add_argument("destination")
    parser.add_argument("--packet-id", required=True)
    args = parser.parse_args()
    try:
        raw = packet(decode(read(args.expectations_file)), packet_id=args.packet_id, now=utc())
        print(json.dumps(retain(args.destination, raw)))
    except Exception:
        raise SystemExit("Operator packet creation rejected; inspect protected inputs locally") from None


if __name__ == "__main__":
    main()
