"""Read-only preflight. Consistent fixture evidence never enrolls real trust."""

from importlib.metadata import version
from pathlib import Path

import artifact_store as artifacts
import sealed_control_journal as control
import sealed_volume as volume
from controller_stage_manifest import hex_digest, inspect_stage
from guarded_controller_route import Binding
from provider_trust_stage import directory, public_record, read, trusted_key
from signed_provider_contract import decode, label, sha, stamp


def dependencies():
    crypto, client = version("cryptography"), version("httpx")
    if not 44 <= int(crypto.split(".")[0]) < 47 or client != "0.28.1":
        raise ValueError("Pinned stage dependencies unavailable")


def enrollment(root, *, fingerprint, issuer, reviewer, provisioner, confirmation_sha, now):
    root = directory(root)
    if {p.name for p in root.iterdir()} - {"candidate.json", "key-confirmation.json", "revoked.json"}:
        raise ValueError("Unexpected enrollment material")
    if (root / "revoked.json").exists() or (root / "revoked.json").is_symlink():
        raise ValueError("Enrollment revoked")
    hex_digest(fingerprint)
    label(issuer)
    if label(reviewer) == label(provisioner) or any((root / n).is_symlink() for n in ("candidate.json", "key-confirmation.json")):
        raise ValueError("Independent enrollment expectations required")
    if not (root / "candidate.json").exists():
        return "waiting"
    record, _ = public_record(read(root / "candidate.json"))
    if record["fingerprint"] != hex_digest(fingerprint) or record["issuer_key_id"] != label(issuer) or record["created_at"] > now:
        raise ValueError("Public candidate differs from independent expectations")
    if not (root / "key-confirmation.json").exists() or confirmation_sha is None:
        return "waiting"
    raw = read(root / "key-confirmation.json")
    decision = decode(raw)
    if (sha(raw) != hex_digest(confirmation_sha) or label(reviewer) == label(provisioner)
            or decision["reviewer"] != reviewer or not record["created_at"] <= stamp(decision["confirmed_at"]) <= now):
        raise ValueError("Independent enrollment evidence differs")
    trusted_key(root, fingerprint, now=now)  # Public-only verification; never load/decrypt a signer.
    return "verified"


def binding_snapshot(journal, binding):
    if not isinstance(journal, control.Journal) or not isinstance(binding, Binding) or journal.journal_id != binding.journal_id:
        raise ValueError("V2 journal and independent binding required")
    runtime = binding.validate()
    with journal.connect(readonly=True) as db:
        control.eligible(db, binding.operation_id, {"sealed"})
        row = db.execute("SELECT record FROM operations WHERE id=?", (binding.operation_id,)).fetchone()
        record = volume.validate_record(decode(row[0].encode()))
        if (sha(row[0].encode()) != binding.record_sha256 or record["volume_binding_sha256"] != binding.volume_binding_sha256
                or record["manifest_digest"] != "sha256:" + runtime["model_digest_sha256"]):
            raise ValueError("Exact binding differs")
        entry = control.inspect(db, journal.journal_id)[-1]
        fence = control.anchor_frame(journal.journal_id, entry)
    return record, fence


def assess(stage, approved_manifest_sha256, model_root, journal, binding, trust_root, *, expected_fingerprint,
           expected_issuer_key_id, expected_reviewer, provisioned_by, approved_confirmation_sha256, now):
    gates = dict.fromkeys(("package", "dependencies", "binding", "model", "enrollment"), "not_checked")
    result = {"schema": "guarded-controller-readiness-v1", "status": "blocked", "gates": gates,
              "read_only": True, "actual_provider_identity_verified": False, "executed_weights_qualified": False,
              "runtime_installation_authorized": False, "native_execution_authorized": False,
              "production_activation": False, "legal_qualification": False}
    current = "package"
    try:
        stamp(now)
        inspect_stage(stage, approved_manifest_sha256)
        gates[current] = "verified"
        current = "dependencies"
        dependencies()
        gates[current] = "verified"
        current = "binding"
        record, before = binding_snapshot(journal, binding)
        gates[current] = "verified"
        current = "model"
        root = volume.owner_dir(Path(model_root), readonly=True)
        proof = artifacts.supervised_verify(root / ("snapshot-" + record["generation_id"]) / "store",
                                             record["manifest_digest"], strategy="windowed-pinned")
        if proof["content_identity_sha256"] != record["content_sha256"]:
            raise ValueError("Model content differs")
        gates[current] = "verified"
        current = "enrollment"
        gates[current] = enrollment(trust_root, fingerprint=expected_fingerprint, issuer=expected_issuer_key_id,
                                     reviewer=expected_reviewer, provisioner=provisioned_by,
                                     confirmation_sha=approved_confirmation_sha256, now=now)
        current = "binding"
        after_record, after = binding_snapshot(journal, binding)
        if after != before or record != after_record:
            raise ValueError("Context changed during preflight")
        result["context_sha256"] = sha(artifacts.canonical({"fence": before, "record": binding.record_sha256,
                                                           "package": approved_manifest_sha256}))
        result["status"] = "ready_for_disposable_mock_validation" if gates["enrollment"] == "verified" else "waiting"
        return result
    except Exception:
        gates[current] = "blocked"
        return result  # Bounded gate codes only, no paths, identifiers, credentials or tracebacks.
