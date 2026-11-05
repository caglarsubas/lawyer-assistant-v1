"""Frozen, opt-in metadata-handoff campaign using invented local identities."""

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import metadata_handoff_readiness as access  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from destination_snapshot_fixture import make_pair  # noqa: E402
from metadata_handoff_fixture import make  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402

CASES = ("H01_distinct_recipient_identities", "H02_metadata_only_package_ready", "H03_closed_hash_only_fields",
    "H04_exact_canonical_transport_pin", "H05_read_only_recipient_acceptance", "H06_fresh_reopen_same_expiry",
    "H07_sender_authentication_required", "H08_recipient_authentication_required", "H09_missing_host_pin_withheld",
    "H10_changed_reference_request_withheld", "H11_foreign_recipient_pin_rejected", "H12_authority_claim_rejected",
    "H13_duplicate_json_fields_rejected", "H14_negative_review_withheld", "H15_revoked_source_session_withheld",
    "H16_revoked_recipient_session_denied", "H17_corrupt_exact_proof_retained", "H18_staged_namespace_retained",
    "H19_manifest_race_withheld", "H20_expired_specification_withheld", "H21_checked_budget_withheld",
    "H22_missing_transport_not_created", "H23_original_versions_and_histories_exact", "H24_no_genuine_authority_grant")
NEW = ("scripts/metadata_handoff_readiness.py", "scripts/metadata_handoff_fixture.py",
       "scripts/qualify_metadata_handoff.py", "backend/tests/test_metadata_handoff_readiness.py")


def campaign(root):
    frames, pairs, initial, calls, results, packages, proof_sets = [], [], [], 0, {}, [], []
    prior_path = ROOT / "docs/evidence/retention-authorization-2026-11-05.json"
    prior = json.loads(prior_path.read_bytes())
    pins = dict(prior["source_sha256"])
    assert len(pins) == 781 and all(e.sha((ROOT / n).read_bytes()) == sha for n, sha in pins.items())
    for n in NEW:
        assert n not in pins
        pins[n] = e.sha((ROOT / n).read_bytes())

    def histories(f):
        return (tuple(side[:2] for side in f.pair.protected()), f.source.notes.protected()[1],
                f.source.protected()[1], f.target.protected())

    def account_tables(account):
        with sqlite3.connect("file:" + str(account.authority.database) + "?mode=ro", uri=True) as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            tables = {name: {e.sha(repr(row).encode()) for row in db.execute('SELECT * FROM "' + name.replace('"', '""') + '"')}
                      for name in names}
            revoked = db.execute("SELECT * FROM sessions WHERE token_hash = ?", (account.sessions["reviewer"],)).fetchone()
        return tables, e.sha(repr(revoked).encode())

    def row(ident, condition):
        assert ident in CASES and ident not in results and condition
        results[ident] = {"id": ident, "state": "verified"}

    def create(name):
        pair = make_pair(root / (name + "-pair"))
        pairs.append(pair)
        f = make(pair, root / (name + "-frame"))
        frames.append(f)
        initial.append(histories(f))
        proof_sets.append((f.source, f.proof))
        return f

    def call(f, operation, *, service=None, digest=None, scope=None, specification=None):
        nonlocal calls
        before = f.protected()
        value = f.call(operation, service=service, package_sha256=digest, scope=scope, specification=specification)
        assert f.protected() == before
        assert value["read_only"] and all(value[k] is False for k in FLAGS)
        assert not any(value[k] for k in ("retention_authorized", "genuine_acknowledgement_verified", "durability_qualified",
            "snapshot_verified", "destination_attestation_verified", "atomic_snapshot", "joint_rollback_qualified"))
        if value["state"] not in {"metadata_package_ready", "read_only_destination_acceptance"}:
            assert value["handoff"] is value["acceptance"] is None
            assert not value["metadata_package_ready"] and not value["read_only_destination_acceptance"]
        calls += 1
        return value

    def publish(f):
        value = call(f, "package")
        assert value["state"] == "metadata_package_ready"
        raw = e.encode(value["handoff"]["manifest"])
        e.retain(f.root / (f.specification.handoff_id + ".metadata.json"), raw)
        digest = e.sha(raw)
        packages.append((f, digest, raw))
        return value, digest, raw

    def receiver(f, digest, **options):
        return f.service(packages={f.specification.handoff_id: digest}, **options)

    def copy(f, name, raw):
        g = f.fork(root / name, specification=f.specification)
        e.retain(g.root / (g.specification.handoff_id + ".metadata.json"), raw)
        return g

    try:
        f, g = create("accepted"), create("source-revoked")
        accounts = [f.pair.source.account, f.pair.target.account, f.target.account,
                    g.pair.source.account, g.pair.target.account, g.target.account]
        account_before = [e.sha(a.authority.database.read_bytes()) for a in accounts]
        tables_before = [account_tables(a) for a in accounts]
        markers_before = [{p.name: e.sha(p.read_bytes()) for p in a.profile.iterdir() if p.name != a.authority.database.name}
                          for a in accounts]
        row("H01_distinct_recipient_identities", all(
            x.target.account.authority.profile_id != x.pair.target.account.authority.profile_id
            and not set(x.target.account.ids.values()) & set(x.pair.target.account.ids.values()) for x in frames))
        packaged, digest, raw = publish(f)
        _, other_digest, _ = publish(g)
        row("H02_metadata_only_package_ready", packaged["metadata_package_ready"])
        manifest = packaged["handoff"]["manifest"]
        row("H03_closed_hash_only_fields", set(manifest) == access.FIELDS and set(manifest["evidence"]) == access.EVIDENCE
            and not any(x in json.dumps(manifest) for x in ("session_sha256", "cookie", "plaintext", "private_key", "path")))
        row("H04_exact_canonical_transport_pin", digest == packaged["handoff"]["package_sha256"]
            and e.encode(e.decode(raw)) == raw)
        accepted = call(f, "accept", service=receiver(f, digest), digest=digest)
        row("H05_read_only_recipient_acceptance", accepted["state"] == "read_only_destination_acceptance")
        row("H06_fresh_reopen_same_expiry", accepted == call(f, "accept", service=receiver(f, digest), digest=digest)
            and accepted["acceptance"]["expires_at"] <= manifest["expires_at"] <= f.pair.snapshot["expires_at"])
        held = call(f, "package", scope=f.pair.target.account.scope("other"))
        row("H07_sender_authentication_required", held["state"] == "denied")
        held = call(f, "accept", service=receiver(f, digest), digest=digest, scope=f.target.account.scope("preparer"))
        row("H08_recipient_authentication_required", held["state"] == "denied")
        row("H09_missing_host_pin_withheld", call(f, "accept", digest=digest)["state"] == "unverifiable")
        row("H10_changed_reference_request_withheld", call(f, "accept", service=receiver(f, digest), digest="0" * 64)["state"] == "unverifiable")
        rejected = False
        try:
            f.service(pins=replace(f.pins, destination_context_sha256="0" * 64))
        except ValueError:
            rejected = True
        row("H11_foreign_recipient_pin_rejected", rejected)
        changed = e.decode(raw)
        changed["production_activation"] = True
        malicious = e.encode(changed)
        bad = copy(f, "authority-claim", malicious)
        row("H12_authority_claim_rejected", call(bad, "accept", service=receiver(bad, e.sha(malicious)),
            digest=e.sha(malicious))["state"] == "unverifiable")
        duplicate = b'{"schema":"duplicate",' + raw[1:]
        bad = copy(f, "duplicate-fields", duplicate)
        row("H13_duplicate_json_fields_rejected", call(bad, "accept", service=receiver(bad, e.sha(duplicate)),
            digest=e.sha(duplicate))["state"] == "unverifiable")
        negative_source = f.source.fork(root / "negative-proof")
        negative = negative_source.publish(decision="reject")
        proof_sets.append((negative_source, negative))
        bad = f.fork(root / "negative-transport", source=negative_source, proof=negative)
        row("H14_negative_review_withheld", call(bad, "package")["state"] == "source_unavailable")
        damaged_source = f.source.fork(root / "damaged-proof")
        damaged = damaged_source.publish()
        proof_sets.append((damaged_source, damaged))
        path = damaged_source.root / (damaged.proof_id + ".decision.json")
        injected_proof = path.read_bytes() + b" "
        path.write_bytes(injected_proof)  # Explicit test-owned exact-version fault.
        bad = f.fork(root / "damaged-transport", source=damaged_source, proof=damaged)
        row("H17_corrupt_exact_proof_retained", call(bad, "package")["state"] == "source_unavailable"
            and path.read_bytes() == injected_proof)
        bad = copy(f, "staged-transport", raw)
        staged = bad.root / "interrupted.part"
        e.retain(staged, b"INVENTED staged metadata")
        row("H18_staged_namespace_retained", call(bad, "accept", service=receiver(bad, digest), digest=digest)["state"]
            == "unverifiable" and staged.read_bytes() == b"INVENTED staged metadata")
        bad = copy(f, "race-transport", raw)
        path = bad.root / (bad.specification.handoff_id + ".metadata.json")
        raced = raw + b" "
        def inject(_):
            path.write_bytes(raced)
        before = bad.source.protected(), bad.target.protected()
        held = bad.call("accept", service=receiver(bad, digest, checkpoint=inject), package_sha256=digest)
        calls += 1
        row("H19_manifest_race_withheld", held["state"] == "observation_conflict" and held["acceptance"] is None
            and path.read_bytes() == raced and (bad.source.protected(), bad.target.protected()) == before)
        expired = replace(f.specification, created_at=f.target.account.now - 2, expires_at=f.target.account.now)
        row("H20_expired_specification_withheld", call(f, "package", specification=expired,
            service=f.service(specifications={expired.handoff_id: expired}))["state"] == "unverifiable")
        old = access.BUDGET_SECONDS
        try:
            access.BUDGET_SECONDS = 0
            held = call(f, "accept", service=receiver(f, digest), digest=digest)
        finally:
            access.BUDGET_SECONDS = old
        row("H21_checked_budget_withheld", held["state"] == "budget_exhausted")
        missing = f.fork(root / "missing-transport", specification=f.specification)
        row("H22_missing_transport_not_created", call(missing, "accept", service=receiver(missing, digest), digest=digest)["state"]
            == "unverifiable" and not list(missing.root.iterdir()))
        g.pair.target.account.revoke("reviewer")  # Declared fixture-only mutation before this read baseline.
        row("H15_revoked_source_session_withheld", call(g, "accept", service=receiver(g, other_digest),
            digest=other_digest)["state"] == "source_unavailable")
        f.target.account.revoke("reviewer")
        row("H16_revoked_recipient_session_denied", call(f, "accept", service=receiver(f, digest), digest=digest)["state"] == "denied")
        account_after = [e.sha(a.authority.database.read_bytes()) for a in accounts]
        tables_after = [account_tables(a)[0] for a in accounts]
        for i, (before, removed) in enumerate(tables_before):
            expected = {name: rows - {removed} if name == "sessions" and i in (2, 4) else rows
                        for name, rows in before.items()}
            assert tables_after[i] == expected
        assert markers_before == [{p.name: e.sha(p.read_bytes()) for p in a.profile.iterdir() if p.name != a.authority.database.name}
                                  for a in accounts]
        row("H23_original_versions_and_histories_exact", all(histories(x) == initial[i]
            for i, x in enumerate(frames)) and [i for i, (a, b) in enumerate(zip(account_before, account_after, strict=True)) if a != b] == [2, 4]
            and all((x.root / (x.specification.handoff_id + ".metadata.json")).read_bytes() == package for x, _, package in packages))
        row("H24_no_genuine_authority_grant", accepted["read_only_destination_acceptance"]
            and not any(accepted[k] for k in FLAGS) and not accepted["retention_authorized"]
            and not accepted["genuine_acknowledgement_verified"] and not accepted["durability_qualified"])
        assert all(e.sha((ROOT / n).read_bytes()) == sha for n, sha in pins.items())
        assert set(results) == set(CASES)
        retained_reviews = sum(len(tuple(x.pair.source.sidecar.root.iterdir())) for x in frames)
        assert retained_reviews == 4 and len({a.authority.file_identity for a in accounts}) == 6
        return {"schema": "metadata-handoff-qualification-v1", "status": "qualified", "case_plan_sha256": e.sha(e.encode(CASES)),
            "prior_retention_report_sha256": e.sha(prior_path.read_bytes()), "source_sha256": pins,
            "evidence": {"cases": [results[k] for k in CASES], "isolated_account_contexts": len(accounts),
                "fixture_metadata_packages": len(packages), "fixture_signed_proof_sets": len(proof_sets),
                "disposable_signing_keys": sum(len(x.keys) for x, _ in proof_sets), "retained_original_input_reviews": retained_reviews,
                "service_reads": calls, "service_writes": 0, "declared_fixture_session_revocations": 2,
                "declared_corrupt_proof_copies": 1, "declared_staged_namespaces": 1, "declared_transport_races": 1,
                "original_versions_and_histories_exact": True, "transport_contains_only_closed_hash_metadata": True,
                "account_changes_only_declared_session_deletions": True, "profile_markers_exact": True,
                "retention_authorized": False, "genuine_acknowledgement_verified": False, "durability_qualified": False},
            "production_activation": False, "legal_qualification": False}
    finally:
        for pair in pairs:
            pair.close()
        for f in frames:
            f.target.account.store.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    output = args.output.absolute()
    e.directory(output.parent)
    if output.exists():
        parser.error("Output must not already exist")
    try:
        with tempfile.TemporaryDirectory(prefix="metadata-handoff-") as directory:
            value = campaign(Path(directory).resolve())
    except Exception as exc:
        e.retain(output, e.encode({"schema": "metadata-handoff-qualification-v1", "status": "incomplete", "error_type": type(exc).__name__}))
        return 1
    # Qualification reports include hundreds of source pins; transport stays 4 KiB.
    raw = e.encode(value)
    if len(raw) > 1024 * 1024:
        raise ValueError("Qualification report exceeds its separate bound")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"status": "qualified", "frozen_outcomes": len(CASES), "source_pins": len(value["source_sha256"]),
                      "service_writes": 0, "production_activation": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
