"""External fixture writer; invented independent reviewers and keys only."""

import os
from dataclasses import dataclass, field
from unittest.mock import patch

import operator_enrollment_evidence as e
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from metadata_handoff_fixture import RecipientAccount, make_recipient
from operator_recovery_inputs import FLAGS
from recipient_observation_readiness import (
    DECISIONS,
    PURPOSE,
    SCHEMAS,
    ReceiptPins,
    ReceiptSpecification,
    RecipientObservation,
    ReviewSet,
    context,
)
from retention_authorization_readiness import KeyPin


def make_independent_pair(root):
    """Keep predecessor code exact while giving each fixture a fresh profile."""
    from destination_snapshot_fixture import make_pair
    with patch("journal_backup_fixture.Fixture", RecipientAccount):
        return make_pair(root)


@dataclass
class Fixture:
    metadata: object
    digest: str
    review: object
    root: object
    pins: ReceiptPins
    specification: ReceiptSpecification
    keys: dict
    private_keys: dict = field(repr=False)

    def service(self, proof=None, *, keys=None, checkpoint=None, specifications=None, recipient_scope=None):
        source = self.metadata.service(packages={self.metadata.specification.handoff_id: self.digest})
        return RecipientObservation(source, self.review.service(), self.root, self.pins,
            self.keys if keys is None else keys,
            {self.specification.receipt_id: self.specification} if specifications is None else specifications,
            {self.specification.receipt_id: proof} if proof else {},
            recipient_scope=recipient_scope or self.metadata.target.account.scope("reviewer"), checkpoint=checkpoint)

    def call(self, operation, *, proof=None, service=None, scope=None, **changes):
        account = self.metadata.target.account if operation == "observe" else self.review.account
        request = {"entry_id": self.specification.receipt_id, "specification_sha256": self.specification.sha256}
        if operation == "plan":
            request["review_set_sha256"] = proof.sha256 if proof else None
        request.update(changes)
        return (service or self.service(proof)).dispatch(scope or account.scope("reviewer"), operation, **request)

    def protected(self):
        import stat
        paths = []
        for path in sorted(self.root.iterdir()):
            info = path.lstat()
            paths.append((path.name, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
                          os.readlink(path) if stat.S_ISLNK(info.st_mode) else path.read_bytes()))
        accounts = (self.metadata.pair.source.account, self.metadata.pair.target.account,
                    self.metadata.target.account, self.review.account)
        return self.metadata.protected(), self.review.protected(), tuple(e.sha(a.authority.database.read_bytes()) for a in accounts), paths

    def observe(self):
        before = self.protected()
        value = self.call("observe")
        assert self.protected() == before and value["state"] == "recipient_observation_receipt_ready"
        raw = e.encode(value["recipient_receipt"]["manifest"])
        assert value["recipient_receipt"]["sha256"] == e.sha(raw)
        return raw

    def sign(self, kind, claims):
        return e.encode({"schema": "recipient-retention-signed-envelope-v1", "key_id": self.keys[kind].key_id,
            "claims": claims, "signature": self.private_keys[kind].sign(SCHEMAS[kind].encode() + b"\0" + e.encode(claims)).hex()})

    def publish(self, raw, *, decision="accept", mutate=None):
        """Fixture-only exclusive retention and review; the service never writes."""
        value, p = e.decode(raw), self.review.service().planner
        prepared = p.actor(self.review.account.scope("preparer"), "preparer")
        reviewer = p.actor(self.review.account.scope("reviewer"), "reviewer")
        now = p.clock()
        expires = min(value["expires_at"], prepared["expires_at"], reviewer["expires_at"], *(k.expires_at for k in self.keys.values()))
        common = {"purpose": PURPOSE, "receipt_id": self.specification.receipt_id,
            "receipt_sha256": e.sha(raw), "context_sha256": self.service().context(), **dict.fromkeys(FLAGS, False)}
        proposal = {**common, "schema": SCHEMAS["preparer"], "prepared_by": prepared,
            "assigned_reviewer": p.authority.eligible(p.reviewer, "reviewer"), "created_at": now, "expires_at": expires}
        if mutate:
            mutate("preparer", proposal)
        raw_proposal = self.sign("preparer", proposal)
        reviewed = {**common, "schema": SCHEMAS["reviewer"], "proposal_sha256": e.sha(raw_proposal),
            "reviewed_by": reviewer, "reviewed_at": now, "expires_at": expires,
            "decision": decision, "reason_code": DECISIONS[decision]}
        if mutate:
            mutate("reviewer", reviewed)
        raw_decision = self.sign("reviewer", reviewed)
        for suffix, content in (("receipt", raw), ("proposal", raw_proposal), ("decision", raw_decision)):
            e.retain(self.root / (self.specification.receipt_id + "." + suffix + ".json"), content)
        return ReviewSet(receipt_id=self.specification.receipt_id, receipt_sha256=e.sha(raw),
                         proposal_sha256=e.sha(raw_proposal), decision_sha256=e.sha(raw_decision))

    def fork(self, root, seed):
        root.mkdir(mode=0o700)
        fixture = wrap(self.metadata, self.digest, self.review, root)
        value = e.decode(seed)
        value.update(receipt_id=fixture.specification.receipt_id,
                     receipt_specification_sha256=fixture.specification.sha256, context_sha256=fixture.service().context())
        return fixture, e.encode(value)


def wrap(metadata, digest, review, root):
    source, target = metadata.service(packages={metadata.specification.handoff_id: digest}), review.service()
    info = root.lstat()
    pins = ReceiptPins(root_identity=(info.st_dev, info.st_ino, info.st_uid, info.st_mode),
                       handoff_binding_sha256=source.binding(), review_context_sha256=target.context())
    now = metadata.target.account.now
    spec = ReceiptSpecification(receipt_id=os.urandom(16).hex(), metadata_entry_id=metadata.specification.handoff_id,
        metadata_specification_sha256=metadata.specification.sha256, metadata_package_sha256=digest,
        created_at=now, expires_at=metadata.specification.expires_at)
    private = {kind: Ed25519PrivateKey.generate() for kind in SCHEMAS}
    ctx = context(source, target, pins)
    keys = {kind: KeyPin(key_id=os.urandom(16).hex(), kind=kind,
        principal_id=target.planner.preparer if kind == "preparer" else target.planner.reviewer,
        profile_id=target.planner.authority.profile_id, store_context_sha256=ctx,
        issuer_context_sha256=source.binding(),
        public_key=private[kind].public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),
        not_before=now - 60, expires_at=spec.expires_at) for kind in SCHEMAS}
    return Fixture(metadata, digest, review, root, pins, spec, keys, private)


def make(metadata, digest, root, *, review=None):
    root.mkdir(mode=0o700)
    review = review or make_recipient(root / "independent-review")
    now = max(metadata.target.account.now, review.account.now)
    metadata.pair.source.account.now = metadata.pair.target.account.now = metadata.target.account.now = review.account.now = now
    notes = root / "recipient-receipts"
    notes.mkdir(mode=0o700)
    return wrap(metadata, digest, review, notes)
