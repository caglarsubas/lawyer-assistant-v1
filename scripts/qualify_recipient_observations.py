"""Frozen opt-in recipient-receipt campaign with invented identities only."""

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import traceback
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import operator_enrollment_evidence as e  # noqa: E402
import recipient_observation_readiness as access  # noqa: E402
from metadata_handoff_fixture import make as make_metadata  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from recipient_observation_fixture import make, make_independent_pair  # noqa: E402

CASES = ("O01_independent_recipient_review_profiles", "O02_read_only_observation_receipt", "O03_closed_hash_metadata",
    "O04_exact_host_bound_receipt", "O05_independent_signed_review", "O06_fresh_exact_version_plan",
    "O07_original_expiry_not_extended", "O08_observer_authentication_first", "O09_review_authentication_first",
    "O10_recipient_authority_required", "O11_missing_review_not_inferred", "O12_wrong_request_hash_withheld",
    "O13_rejection_withheld", "O14_changes_required_withheld", "O15_changed_receipt_retained",
    "O16_invalid_signature_despite_host_hash_rejected", "O17_duplicate_json_fields_rejected",
    "O18_interrupted_namespace_retained", "O19_linked_receipt_retained", "O20_receipt_race_withheld",
    "O21_revoked_independent_reviewer_denied", "O22_revoked_recipient_withheld", "O23_expired_window_withheld",
    "O24_checked_budget_withheld", "O25_original_versions_and_histories_exact", "O26_no_genuine_authority_grant")
NEW = ("scripts/recipient_observation_readiness.py", "scripts/recipient_observation_fixture.py",
       "scripts/qualify_recipient_observations.py", "backend/tests/test_recipient_observation_readiness.py",
       "backend/tests/test_recipient_observation_qualification.py")


def campaign(root):
    prior_path = ROOT / "docs/evidence/metadata-handoff-2026-11-05.json"
    prior = json.loads(prior_path.read_bytes())
    pins = dict(prior["source_sha256"])
    assert len(pins) == 785 and all(e.sha((ROOT / n).read_bytes()) == digest for n, digest in pins.items())
    for name in NEW:
        assert name not in pins
        pins[name] = e.sha((ROOT / name).read_bytes())
    pairs, frames, forks, proofs, packages, results = [], [], [], [], [], {}
    calls = 0

    def row(ident, condition):
        assert ident in CASES and ident not in results and condition
        results[ident] = {"id": ident, "state": "verified"}

    def histories(f):
        return f.metadata.protected(), f.review.protected()

    def create(name):
        pair = make_independent_pair(root / (name + "-pair"))
        pairs.append(pair)
        metadata = make_metadata(pair, root / (name + "-metadata"))
        digest, _ = metadata.publish()
        frame = make(metadata, digest, root / (name + "-recipient"))
        frames.append(frame)
        return frame

    def checked(value):
        assert value["read_only"] and all(value[k] is False for k in FLAGS)
        assert not any(value[k] for k in ("retention_authorized", "genuine_acknowledgement_verified", "durability_qualified",
            "snapshot_verified", "destination_attestation_verified", "atomic_snapshot", "joint_rollback_qualified"))
        assert value["evidence"] is value["review"] is value["decision"] is value["retention_plan"] is None
        if value["state"] not in {"recipient_observation_receipt_ready", "ready_for_disposable_recipient_retention_planning"}:
            assert value["recipient_receipt"] is value["recipient_retention_plan"] is None
            assert not value["recipient_observation_receipt_ready"] and not value["recipient_retention_plan_ready"]

    def call(f, operation, **options):
        nonlocal calls
        before = f.protected()
        value = f.call(operation, **options)
        assert f.protected() == before
        checked(value)
        calls += 1
        return value

    def publish(f, raw, **options):
        proof = f.publish(raw, **options)
        proofs.append((f, proof))
        return proof

    def fork(f, name, raw):
        other, content = f.fork(root / name, raw)
        forks.append(other)
        return other, content

    def tables(account):
        with sqlite3.connect("file:" + str(account.authority.database) + "?mode=ro", uri=True) as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            rows = {name: {e.sha(repr(row).encode()) for row in db.execute('SELECT * FROM "' + name.replace('"', '""') + '"')}
                    for name in names}
            session = db.execute("SELECT * FROM sessions WHERE token_hash = ?", (account.sessions["reviewer"],)).fetchone()
        return rows, e.sha(repr(session).encode())

    try:
        f, g = create("accepted"), create("revoked-recipient")
        accounts = [a for frame in frames for a in (frame.metadata.pair.source.account, frame.metadata.pair.target.account,
                                                     frame.metadata.target.account, frame.review.account)]
        before = [histories(frame) for frame in frames]
        rows_before = [tables(a) for a in accounts]
        bytes_before = [e.sha(a.authority.database.read_bytes()) for a in accounts]
        markers = [{p.name: e.sha(p.read_bytes()) for p in a.profile.iterdir() if p.name != a.authority.database.name}
                   for a in accounts]
        row(CASES[0], len({a.authority.file_identity for a in accounts}) == 8
            and all(len({a.authority.profile_id for a in (x.metadata.pair.source.account, x.metadata.pair.target.account,
                                                        x.metadata.target.account, x.review.account)}) == 4 for x in frames))
        observed = call(f, "observe")
        raw = e.encode(observed["recipient_receipt"]["manifest"])
        other = call(g, "observe")
        other_raw = e.encode(other["recipient_receipt"]["manifest"])
        packages += [(f, raw), (g, other_raw)]
        row(CASES[1], observed["state"] == "recipient_observation_receipt_ready")
        value = e.decode(raw)
        row(CASES[2], set(value) == access.RECEIPT and set(value["acceptance"]) == access.ACCEPTANCE
            and not any(n in json.dumps(value) for n in ("cookie", "session_sha256", "private_key", "public_key", "path", "plaintext")))
        row(CASES[3], e.sha(raw) == observed["recipient_receipt"]["sha256"]
            and value["context_sha256"] == f.service().context() and value["receipt_specification_sha256"] == f.specification.sha256)
        proof, other_proof = publish(f, raw), publish(g, other_raw)
        planned = call(f, "plan", proof=proof)
        row(CASES[4], planned["independent_recipient_review_checked"] and len({k.principal_id for k in f.keys.values()}) == 2)
        row(CASES[5], planned["state"] == "ready_for_disposable_recipient_retention_planning"
            and planned["recipient_retention_plan"]["review_set_sha256"] == proof.sha256
            and planned["recipient_retention_plan"]["acceptance_sha256"] == e.sha(e.encode(value["acceptance"])))
        row(CASES[6], planned["recipient_retention_plan"]["expires_at"] <= value["expires_at"]
            <= min(f.metadata.recipient_input_expires_at, f.metadata.specification.expires_at))
        row(CASES[7], call(f, "observe", scope=f.metadata.target.account.scope("preparer"), entry_id="invalid")["state"] == "denied")
        row(CASES[8], call(f, "plan", proof=proof, scope=f.review.account.scope("preparer"), entry_id="invalid")["state"] == "denied")
        row(CASES[9], call(f, "plan", proof=proof, service=f.service(proof,
            recipient_scope=f.metadata.target.account.scope("preparer")))["state"] == "source_unavailable")
        row(CASES[10], call(f, "plan")["state"] == "unverifiable")
        row(CASES[11], call(f, "plan", proof=proof, review_set_sha256="0" * 64)["state"] == "unverifiable")
        for ident, decision in ((CASES[12], "reject"), (CASES[13], "changes_required")):
            bad, content = fork(f, decision, raw)
            denied = call(bad, "plan", proof=publish(bad, content, decision=decision))
            row(ident, denied["state"] == "review_" + decision)
        bad, content = fork(f, "changed-receipt", raw)
        selected = publish(bad, content)
        path = bad.root / (bad.specification.receipt_id + ".receipt.json")
        changed = content + b" "
        path.write_bytes(changed)
        row(CASES[14], call(bad, "plan", proof=selected)["state"] == "unverifiable" and path.read_bytes() == changed)
        bad, content = fork(f, "invalid-signature", raw)
        selected = publish(bad, content)
        path = bad.root / (bad.specification.receipt_id + ".decision.json")
        changed = e.decode(path.read_bytes())
        changed["signature"] = "0" * 128
        changed = e.encode(changed)
        path.write_bytes(changed)
        selected = replace(selected, decision_sha256=e.sha(changed))
        row(CASES[15], call(bad, "plan", proof=selected)["state"] == "unverifiable" and path.read_bytes() == changed)
        bad, content = fork(f, "duplicate-fields", raw)
        duplicate = b'{"schema":"duplicate",' + content[1:]
        selected = publish(bad, content)
        (bad.root / (bad.specification.receipt_id + ".receipt.json")).write_bytes(duplicate)
        selected = replace(selected, receipt_sha256=e.sha(duplicate))
        row(CASES[16], call(bad, "plan", proof=selected)["state"] == "unverifiable")
        bad, content = fork(f, "staged-namespace", raw)
        selected = publish(bad, content)
        stage = bad.root / "interrupted.part"
        e.retain(stage, b"INVENTED interrupted recipient receipt")
        row(CASES[17], call(bad, "plan", proof=selected)["state"] == "unverifiable" and stage.exists())
        bad, content = fork(f, "linked-receipt", raw)
        selected = publish(bad, content)
        path = bad.root / (bad.specification.receipt_id + ".receipt.json")
        target = root / "invented-linked-receipt.json"
        e.retain(target, content)
        path.unlink()
        path.symlink_to(target)
        row(CASES[18], call(bad, "plan", proof=selected)["state"] == "unverifiable" and path.is_symlink())
        bad, content = fork(f, "receipt-race", raw)
        selected = publish(bad, content)
        path = bad.root / (bad.specification.receipt_id + ".receipt.json")
        changed, original = content + b" ", histories(bad)
        def race(_):
            path.write_bytes(changed)
        raced = bad.call("plan", proof=selected, service=bad.service(selected, checkpoint=race))
        calls += 1
        checked(raced)
        row(CASES[19], raced["state"] == "observation_conflict" and path.read_bytes() == changed and histories(bad) == original)
        now = f.review.account.now
        try:
            f.review.account.now = f.specification.expires_at
            expired = call(f, "plan", proof=proof)
        finally:
            f.review.account.now = now
        row(CASES[22], expired["state"] == "unverifiable")
        limit = access.BUDGET_SECONDS
        try:
            access.BUDGET_SECONDS = 0
            exhausted = call(f, "plan", proof=proof)
        finally:
            access.BUDGET_SECONDS = limit
        row(CASES[23], exhausted["state"] == "budget_exhausted")
        f.review.account.revoke("reviewer")
        row(CASES[20], call(f, "plan", proof=proof)["state"] == "denied")
        g.metadata.target.account.revoke("reviewer")
        row(CASES[21], call(g, "plan", proof=other_proof)["state"] == "source_unavailable")
        for i, (old, removed) in enumerate(rows_before):
            expected = {name: rows - {removed} if name == "sessions" and i in (3, 6) else rows for name, rows in old.items()}
            assert tables(accounts[i])[0] == expected
        assert markers == [{p.name: e.sha(p.read_bytes()) for p in a.profile.iterdir() if p.name != a.authority.database.name}
                           for a in accounts]
        row(CASES[24], before == [histories(frame) for frame in frames]
            and [i for i, a in enumerate(accounts) if bytes_before[i] != e.sha(a.authority.database.read_bytes())] == [3, 6]
            and all((x.root / (x.specification.receipt_id + ".receipt.json")).read_bytes() == content for x, content in packages))
        row(CASES[25], planned["recipient_retention_plan_ready"] and all(planned[k] is False for k in FLAGS)
            and not planned["retention_authorized"] and not planned["genuine_acknowledgement_verified"])
        assert set(results) == set(CASES) and all(e.sha((ROOT / n).read_bytes()) == digest for n, digest in pins.items())
        return {"schema": "recipient-observation-qualification-v1", "status": "qualified",
            "case_plan_sha256": e.sha(e.encode(CASES)), "prior_metadata_report_sha256": e.sha(prior_path.read_bytes()),
            "source_sha256": pins, "evidence": {"cases": [results[k] for k in CASES], "isolated_account_contexts": len(accounts),
                "original_input_reviews_retained": sum(len(tuple(x.metadata.pair.source.sidecar.root.iterdir())) for x in frames),
                "original_metadata_packages": len(packages), "fixture_signed_review_sets": len(proofs),
                "disposable_review_keys": sum(len(x.keys) for x in [*frames, *forks]), "service_reads": calls, "service_writes": 0,
                "declared_fixture_session_deletions": 2, "original_versions_and_histories_exact": True,
                "account_changes_only_declared_session_deletions": True, "profile_markers_exact": True,
                "retention_authorized": False, "genuine_acknowledgement_verified": False, "durability_qualified": False},
            "production_activation": False, "legal_qualification": False}
    finally:
        for pair in pairs:
            pair.close()
        for frame in frames:
            frame.metadata.target.account.store.engine.dispose()
            frame.review.account.store.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    output = args.output.absolute()
    e.directory(output.parent)
    if output.exists():
        parser.error("Output must not already exist")
    try:
        with tempfile.TemporaryDirectory(prefix="recipient-observation-") as root:
            value = campaign(Path(root).resolve())
    except Exception as exc:
        locations = [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                     for f in traceback.extract_tb(exc.__traceback__)[-4:]]
        e.retain(output, e.encode({"schema": "recipient-observation-qualification-v1", "status": "incomplete",
                                 "error_type": type(exc).__name__, "failure_locations": locations}))
        return 1
    raw = e.encode(value)
    if len(raw) > 1024 * 1024:
        raise ValueError("Qualification report exceeds its bound")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"status": "qualified", "outcomes": len(CASES), "source_pins": len(value["source_sha256"]),
                      "service_writes": 0, "production_activation": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
