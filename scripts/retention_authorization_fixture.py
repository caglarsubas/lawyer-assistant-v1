"""External fixture writer with disposable signers; no real custody or enrollment."""

import os
from dataclasses import dataclass, field

import operator_enrollment_evidence as e
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from operator_recovery_inputs import FLAGS
from retention_authorization_readiness import (
    DECISIONS,
    PURPOSE,
    SCHEMAS,
    KeyPin,
    ProofPins,
    ProofSet,
    RetentionAuthorization,
)
from verification_reference_fixture import ENTRY as REFERENCE_ENTRY
from verification_reference_fixture import make_frame, retain_external

ENTRY = "c" * 32


@dataclass
class Fixture:
    notes: object
    reference: object
    acknowledgement: object
    root: object
    pins: ProofPins
    keys: dict
    private_keys: dict = field(repr=False)

    def service(self, proof_sets=None, *, keys=None, checkpoint=None, references=None):
        refs = references or self.notes.service(references={REFERENCE_ENTRY: self.reference},
            acknowledgements={self.acknowledgement.sha256: self.acknowledgement})
        return RetentionAuthorization(refs, self.root, self.pins, keys if keys is not None else self.keys,
                                      proof_sets or {}, checkpoint=checkpoint)

    def call(self, proof, *, scope=None, service=None, entry_id=ENTRY):
        return (service or self.service({entry_id: proof})).dispatch(
            scope or self.notes.pair.target.account.scope("reviewer"), "inspect",
            entry_id=entry_id, proof_set_sha256=proof.sha256)

    def protected(self):
        # Inventory guards do not follow an injected link.
        import stat
        rows = {}
        for path in self.root.iterdir():
            info = path.lstat()
            rows[path.name] = (info.st_ino, info.st_mode, info.st_nlink, info.st_size,
                os.readlink(path) if stat.S_ISLNK(info.st_mode) else path.read_bytes())
        return self.notes.protected(), rows

    def sign(self, kind, claims):
        return e.encode({"schema": "retention-signed-envelope-v1", "key_id": self.keys[kind].key_id,
            "claims": claims, "signature": self.private_keys[kind].sign(SCHEMAS[kind].encode() + b"\0" + e.encode(claims)).hex()})

    def publish(self, *, decision="accept", mutate=None, proof_id=None):
        """Fixture-owned exclusive publication before the service read-only baseline."""
        proof_id = proof_id or os.urandom(16).hex()
        pair, ack = self.notes.pair, self.acknowledgement
        p = pair.target.service().planner
        prepared, reviewer = p.actor(pair.target.account.scope("preparer"), "preparer"), p.actor(pair.target.account.scope("reviewer"), "reviewer")
        now = p.clock()
        expires = min(pair.snapshot["expires_at"], prepared["expires_at"], reviewer["expires_at"])
        common = {"purpose": PURPOSE, "proof_id": proof_id, "profile_id": self.pins.profile_id,
            "store_context_sha256": self.pins.store_context_sha256, "proof_context_sha256": self.service().proof_context(),
            "reference_sha256": self.reference.sha256, **dict.fromkeys(FLAGS, False)}
        provenance = {**common, "schema": SCHEMAS["acknowledger"], "plan_sha256": ack.plan_sha256,
            "acknowledgement_pin_sha256": ack.sha256, "issuer_context_sha256": ack.issuer_context_sha256,
            "record_id": self.reference.record_id, "ciphertext_sha256": self.reference.ciphertext_sha256,
            "plaintext_sha256": self.reference.plaintext_sha256, "issued_at": now, "expires_at": expires,
            "custody_status": "unqualified", "durability_status": "unqualified"}
        if mutate:
            mutate("acknowledger", provenance)
        raw_provenance = self.sign("acknowledger", provenance)
        proposal = {**common, "schema": SCHEMAS["preparer"], "plan_sha256": ack.plan_sha256,
            "acknowledgement_pin_sha256": ack.sha256, "provenance_sha256": e.sha(raw_provenance),
            "prepared_by": prepared, "assigned_reviewer": p.authority.eligible(p.reviewer, "reviewer"),
            "created_at": now, "expires_at": expires}
        if mutate:
            mutate("preparer", proposal)
        raw_proposal = self.sign("preparer", proposal)
        reviewed = {**common, "schema": SCHEMAS["reviewer"], "proposal_sha256": e.sha(raw_proposal),
            "reviewed_by": reviewer, "decision": decision, "reason_code": DECISIONS[decision],
            "reviewed_at": now, "expires_at": expires}
        if mutate:
            mutate("reviewer", reviewed)
        raw_decision = self.sign("reviewer", reviewed)
        for suffix, raw in (("provenance", raw_provenance), ("proposal", raw_proposal), ("decision", raw_decision)):
            e.retain(self.root / (proof_id + "." + suffix + ".json"), raw)
        return ProofSet(proof_id=proof_id, reference_entry_id=REFERENCE_ENTRY, reference_sha256=self.reference.sha256,
            proposal_sha256=e.sha(raw_proposal), decision_sha256=e.sha(raw_decision), provenance_sha256=e.sha(raw_provenance))

    def fork(self, root):
        return wrap(self.notes, self.reference, self.acknowledgement, root)


def wrap(notes, reference, acknowledgement, root):
    root.mkdir(mode=0o700)
    info = root.lstat()
    p = notes.pair.target.service().planner
    context = notes.service().binding()
    pins = ProofPins(root_identity=(info.st_dev, info.st_ino, info.st_uid, info.st_mode),
                     profile_id=p.authority.profile_id, store_context_sha256=context)
    private = {kind: Ed25519PrivateKey.generate() for kind in SCHEMAS}
    principals = {"preparer": p.preparer, "reviewer": p.reviewer, "acknowledger": e.sha(b"INVENTED storage issuer")[:32]}
    keys = {kind: KeyPin(key_id=os.urandom(16).hex(), kind=kind, principal_id=principals[kind],
        profile_id=pins.profile_id, store_context_sha256=context, issuer_context_sha256=acknowledgement.issuer_context_sha256,
        public_key=private[kind].public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),
        not_before=p.clock() - 60, expires_at=notes.pair.snapshot["expires_at"]) for kind in SCHEMAS}
    return Fixture(notes, reference, acknowledgement, root, pins, keys, private)


def make(pair, root):
    root.mkdir(mode=0o700)
    notes = make_frame(pair, root / "verification-records")
    reference, acknowledgement = retain_external(notes)
    return wrap(notes, reference, acknowledgement, root / "review-proofs")
