"""Disposable external retention and invented acknowledgement issuer, never enrollment."""

import os
import stat
from dataclasses import asdict, dataclass

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from journal_backup_fixture import pins
from operator_recovery_inputs import FLAGS
from verification_reference_readiness import (
    RECORD_SCHEMA,
    AcknowledgementPin,
    Reference,
    VerificationReferences,
)

ENTRY, RECORD = "e" * 32, "6" * 32


@dataclass
class Frame:
    pair: object
    store: object
    pins: object

    def service(self, *, references=None, acknowledgements=None, checkpoint=None, verifier=None):
        return VerificationReferences(verifier or self.pair.verifier(), self.store, self.pins,
            references or {}, acknowledgements or {}, checkpoint=checkpoint)

    def preview(self, service=None, scope=None):
        return (service or self.service()).dispatch(scope or self.pair.target.account.scope("reviewer"),
            "retention_preview", snapshot=self.pair.snapshot, source_reference=asdict(self.pair.reference))

    def reobserve(self, reference, acknowledgement=None, *, entry_id=ENTRY, scope=None, checkpoint=None, verifier=None):
        service = self.service(references={entry_id: reference},
            acknowledgements={acknowledgement.sha256: acknowledgement} if acknowledgement else {},
            checkpoint=checkpoint, verifier=verifier)
        return service.dispatch(scope or self.pair.target.account.scope("reviewer"), "reobserve",
                                entry_id=entry_id, reference=asdict(reference))

    def protected(self):
        rows = {}
        for path in self.store.root.iterdir():
            info = path.lstat()
            rows[path.name] = (info.st_ino, info.st_mode, info.st_nlink, info.st_size,
                os.readlink(path) if stat.S_ISLNK(info.st_mode) else path.read_bytes())
        return self.pair.protected(), rows


def make_frame(pair, root):
    root.mkdir(mode=0o700)
    store = receipts.ReceiptStore(root=root, context_id=pair.target.sidecar.context_id,
        scope_sha256=pair.target.sidecar.scope_sha256, key=os.urandom(32))
    return Frame(pair, store, pins(pair.target.account, store))


def retain_external(frame, *, record_id=RECORD, acknowledged=True):
    """Fixture-owned publication only; the application service has no write operation."""
    service = frame.service()
    preview = frame.preview(service)
    assert preview["state"] == "private_retention_plan_ready"
    plan = preview["retention_plan"]
    record = {"schema": RECORD_SCHEMA, "record_id": record_id, "store_context_sha256": service.binding(),
        "plan": plan["plan"], "plan_sha256": plan["plan_sha256"], **dict.fromkeys(FLAGS, False)}
    plain, nonce = e.encode(record), os.urandom(12)
    raw = receipts.MAGIC + nonce + AESGCM(frame.store.key).encrypt(nonce, plain, service.aad(record_id))
    receipts._publish(frame.store, record_id, raw)
    ack = AcknowledgementPin(record_id=record_id, ciphertext_sha256=e.sha(raw), plaintext_sha256=e.sha(plain),
        store_context_sha256=service.binding(), plan_sha256=plan["plan_sha256"],
        issuer_context_sha256=e.sha(b"INVENTED separately retained acknowledgement issuer"))
    ref = Reference(record_id=record_id, ciphertext_sha256=e.sha(raw), plaintext_sha256=e.sha(plain),
                    acknowledgement_sha256=ack.sha256 if acknowledged else None)
    return ref, ack
