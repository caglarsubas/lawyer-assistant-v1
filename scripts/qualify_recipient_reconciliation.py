"""Qualify staged receipt reconciliation using disposable profiles and a fresh store."""

import argparse
import json
import multiprocessing
import os
import secrets
import sys
import tempfile
import traceback
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import operator_enrollment_evidence as e  # noqa: E402
import private_inventory_receipts as storage  # noqa: E402
import recipient_receipt_retention as retention  # noqa: E402
from metadata_handoff_fixture import make as make_metadata  # noqa: E402
from operator_recovery_inputs import FLAGS  # noqa: E402
from recipient_observation_fixture import make, make_independent_pair  # noqa: E402
from retention_authorization_readiness import KeyPin  # noqa: E402

PRIOR = ROOT / "docs/evidence/recipient-observation-2026-11-05.json"
REPORT = ROOT / "docs/evidence/staged-recipient-reconciliation-2026-11-06.json"
ADDITIONAL_PINS = (
    "scripts/recipient_receipt_retention.py",
    "scripts/qualify_recipient_reconciliation.py",
    "backend/tests/test_recipient_receipt_retention.py",
)
CASES = {
    "absent_with_unrelated_entry": "absent",
    "writer_exit_before_link": "staged_only",
    "writer_exit_after_link": "linked",
    "completed_writer": "final_only",
    "wrong_reviewer_role": "denied",
    "missing_custody_pin": "unverifiable",
    "signed_wrong_state": "unverifiable",
    "signed_expired_pin": "unverifiable",
    "ciphertext_from_another_store": "unverifiable",
    "selected_pair_changed_during_reobservation": "unverifiable",
}
NO_AUTHORITY = FLAGS | {
    "atomic_snapshot", "retention_authorized", "genuine_acknowledgement_verified", "durability_qualified",
    "recipient_observation_receipt_ready", "recipient_retention_plan_ready", "independent_recipient_review_checked",
}
CRASH_EXIT = 78


def source_pins():
    raw = PRIOR.read_bytes()
    pins = dict(json.loads(raw)["source_sha256"])
    assert len(pins) == 790 and not pins.keys() & set(ADDITIONAL_PINS)
    assert all(e.sha((ROOT / name).read_bytes()) == digest for name, digest in pins.items())
    pins.update((name, e.sha((ROOT / name).read_bytes())) for name in ADDITIONAL_PINS)
    return e.sha(raw), pins


def report(prior_digest, pins, outcomes):
    return {"schema": "staged-recipient-reconciliation-qualification-v1", "status": "qualified",
            "prior_report_sha256": prior_digest, "source_sha256": pins,
            "case_plan_sha256": e.sha(e.encode(CASES)), "outcomes": outcomes,
            "writer_process_interruptions": 2, "reconciliation_writes": 0,
            "original_versions_and_review_history_exact": True, "private_case_inputs": False,
            "production_activation": False, "legal_qualification": False, "durability_qualified": False}


def verify_frozen_report():
    prior_digest, pins = source_pins()
    assert REPORT.read_bytes() == e.encode(report(prior_digest, pins, CASES))


def _crash_writer(store, record_id, stage_id, raw, *, after_link):
    link = os.link

    def interrupt(*args, **kwargs):
        if after_link:
            link(*args, **kwargs)
        os._exit(CRASH_EXIT)

    try:
        with patch.object(storage.secrets, "token_hex", return_value=stage_id), patch.object(os, "link", interrupt):
            storage._publish(store, record_id, raw)
    except Exception:  # noqa: BLE001 - child reports only an exit code
        os._exit(1)
    os._exit(2)


def interrupt_publication(store, record_id, stage_id, raw, *, after_link):
    # The low-level writer receives ciphertext and has no need for the encryption key.
    child = multiprocessing.get_context("spawn").Process(target=_crash_writer,
        args=(replace(store, key=bytes(32)), record_id, stage_id, raw), kwargs={"after_link": after_link})
    child.start()
    try:
        child.join(10)
        assert child.exitcode == CRASH_EXIT
    finally:
        if child.is_alive():
            child.kill()
            child.join()
        child.close()


def provision(root, frame, proof, plan):
    root.mkdir(mode=0o700)
    observation = frame.service(proof)
    store = storage.ReceiptStore(root=root, context_id=secrets.token_hex(16), scope_sha256=observation.binding(),
                                 key=secrets.token_bytes(32))
    binding, now = retention.store_binding(store), observation.review.planner.clock()
    issuer, custodian = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    pins = [KeyPin(key_id=secrets.token_hex(16), principal_id=secrets.token_hex(16), profile_id=secrets.token_hex(16),
        kind=kind, store_context_sha256=binding, issuer_context_sha256=store.scope_sha256,
        public_key=key.public_key().public_bytes_raw(), not_before=now, expires_at=plan["expires_at"])
        for kind, key in (("reviewer", issuer), ("acknowledger", custodian))]
    permission = retention.Permission(record_id=secrets.token_hex(16), receipt_id=frame.specification.receipt_id,
        plan_sha256=e.sha(e.encode(plan)), store_sha256=binding, issued_at=now, expires_at=plan["expires_at"],
        issuer_signature="", custodian_signature="")
    permission = replace(permission, issuer_signature=issuer.sign(permission.message("issuer", pins[0].key_id)).hex(),
                         custodian_signature=custodian.sign(permission.message("custodian", pins[1].key_id)).hex())
    return retention.RecipientReceiptRetention(observation=observation, store=store, permission=permission,
                                               issuer=pins[0], custodian=pins[1]), custodian


def inventory(root):
    rows = {}
    for path in root.iterdir():
        info = path.stat()
        rows[path.name] = (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink,
                           info.st_size, info.st_mtime_ns, info.st_ctime_ns, path.read_bytes())
    return rows


def qualify(frame, proof, raw, root):
    plan = frame.call("plan", proof=proof)
    assert plan["state"] == retention.PLAN_READY
    plan = plan["recipient_retention_plan"]
    account = frame.review.account
    scope = account.scope("reviewer")
    protected = frame.protected()
    outcomes = {}
    stores = {}

    def check(ident, adapter, *, requested_scope=scope, added=None):
        assert ident not in outcomes
        before = inventory(adapter.store.root)
        value = adapter.dispatch(requested_scope, "reconcile", record_id=adapter.permission.record_id)
        after = inventory(adapter.store.root)
        if added is not None:
            assert after.pop(added.name)[-1] == b"disposable concurrent entry"
        assert after == before and frame.protected() == protected
        assert value["read_only"] and value["metadata_only"] and all(value[k] is False for k in NO_AUTHORITY)
        assert all(value[k] is None for k in ("recipient_receipt", "recipient_retention_plan", "evidence", "review"))
        expected = CASES[ident]
        if expected in ("unverifiable", "denied"):
            assert value["state"] == expected and "record_id" not in value and "ciphertext_sha256" not in value
        else:
            pin = adapter.reconciliation_pin
            assert value["state"] == "recipient_retention_reconciled" and value["reconciliation"] == expected
            assert value["record_id"] == adapter.permission.record_id and value["receipt_sha256"] == e.sha(raw)
            assert value["ciphertext_sha256"] == pin.ciphertext_sha256 and value["expires_at"] == pin.expires_at
            assert pin.stage_id not in repr(value) and str(adapter.store.root) not in repr(value)
        outcomes[ident] = expected

    def signed(adapter, key, stage_id, state, digest, *, expires_at=None):
        issued = account.now
        expiry = min(issued + 60, adapter.permission.expires_at) if expires_at is None else expires_at
        pin = retention.ReconciliationPin(stage_id=stage_id, state=state, ciphertext_sha256=digest,
                                         issued_at=issued, expires_at=expiry, signature="")
        pin = replace(pin, signature=key.sign(pin.message(adapter.permission, adapter.custodian.key_id)).hex())
        return replace(adapter, observation=frame.service(proof), store=replace(adapter.store), reconciliation_pin=pin)

    def interrupted(adapter, stage_id, after_link):
        def write(store, record_id, ciphertext):
            interrupt_publication(store, record_id, stage_id, ciphertext, after_link=after_link)
            if after_link:
                raise storage.RetentionUncertain
            raise OSError
        with patch.object(storage, "_publish", side_effect=write):
            return adapter.dispatch(scope, "retain", record_id=adapter.permission.record_id)

    for ident in tuple(CASES)[:4]:
        state = CASES[ident]
        adapter, key = provision(root / state, frame, proof, plan)
        record_id, stage_id = adapter.permission.record_id, secrets.token_hex(16)
        stage, final = adapter.store.root / (".pending-" + stage_id), adapter.store.root / (record_id + ".receipt")
        digest = None
        if state == "absent":
            e.retain(adapter.store.root / "unrelated", b"unrelated disposable entry")
            assert not stage.exists() and not final.exists()
        elif state == "final_only":
            result = adapter.dispatch(scope, "retain", record_id=record_id)
            assert result["state"] == "recipient_receipt_retained" and not stage.exists()
            digest = e.sha(final.read_bytes())
            assert digest == result["ciphertext_sha256"]
        else:
            linked = state == "linked"
            result = interrupted(adapter, stage_id, linked)
            assert result["state"] == ("retention_uncertain" if linked else "unverifiable")
            assert stage.is_file() and final.exists() == linked and stage.stat().st_nlink == (2 if linked else 1)
            if linked:
                assert stage.samefile(final)
            digest = e.sha(stage.read_bytes())
        reader = signed(adapter, key, stage_id, state, digest)
        check(ident, reader)
        stores[state] = (reader, key, stage, final)

    linked, key, _, _ = stores["linked"]
    pin = linked.reconciliation_pin
    check("wrong_reviewer_role", linked, requested_scope=account.scope("preparer"))
    check("missing_custody_pin", replace(linked, reconciliation_pin=None))
    check("signed_wrong_state", signed(linked, key, pin.stage_id, "staged_only", pin.ciphertext_sha256))
    now = account.now
    expired = signed(linked, key, pin.stage_id, "linked", pin.ciphertext_sha256, expires_at=now + 1)
    try:
        account.now = now + 1
        check("signed_expired_pin", expired)
    finally:
        account.now = now

    final_reader, _, pending, final = stores["final_only"]
    foreign, foreign_key = provision(root / "foreign", frame, proof, plan)
    foreign_stage = secrets.token_hex(16)
    e.retain(foreign.store.root / (".pending-" + foreign_stage), final.read_bytes())
    check("ciphertext_from_another_store",
          signed(foreign, foreign_key, foreign_stage, "staged_only", final_reader.reconciliation_pin.ciphertext_sha256))

    def introduce_entry(checkpoint):
        assert checkpoint == "before_reobservation"
        e.retain(pending, b"disposable concurrent entry")

    raced = replace(final_reader, observation=frame.service(proof, checkpoint=introduce_entry))
    check("selected_pair_changed_during_reobservation", raced, added=pending)
    assert outcomes == CASES and frame.protected() == protected
    return outcomes


def campaign(root):
    prior_digest, pins = source_pins()
    pair = make_independent_pair(root / "pair")
    metadata = frame = None
    try:
        metadata = make_metadata(pair, root / "metadata")
        digest, _ = metadata.publish()
        frame = make(metadata, digest, root / "recipient")
        raw = frame.observe()
        outcomes = qualify(frame, frame.publish(raw), raw, root)
        assert source_pins() == (prior_digest, pins)
        return report(prior_digest, pins, outcomes)
    finally:
        pair.close()
        if metadata:
            metadata.target.account.store.engine.dispose()
        if frame:
            frame.review.account.store.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run with Python assertions enabled")
    os.umask(0o077)
    output = args.output.absolute()
    e.directory(output.parent)
    if output.exists() or output.is_symlink():
        parser.error("Output must be a new file")
    try:
        with tempfile.TemporaryDirectory(prefix="staged-recipient-reconciliation-") as root:
            value = campaign(Path(root).resolve())
        raw = e.encode(value)
        assert len(raw) <= 1024 * 1024
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception as exc:  # noqa: BLE001 - suppress fixture values in failure output
        locations = [[Path(frame.filename).name, frame.lineno] for frame in traceback.extract_tb(exc.__traceback__)[-5:]]
        print(json.dumps({"status": "incomplete", "error_type": type(exc).__name__,
                          "locations": locations}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "qualified", "outcomes": len(CASES), "source_pins": len(value["source_sha256"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
