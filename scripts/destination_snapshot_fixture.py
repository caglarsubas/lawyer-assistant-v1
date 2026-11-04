"""Invented destination pins and isolated account stores; no genuine enrollment."""

from dataclasses import asdict, dataclass, replace

from destination_snapshot_verification import DestinationVerifier, destination_context
from qualify_recovery_review_inventory import snapshot as one_snapshot
from recovery_input_fixture import SELECTION, make
from recovery_inventory_fixture import (
    DESTINATION,
    handoff,
    invented_pin,
    retained_reference,
    service,
)


@dataclass
class Pair:
    source: object
    target: object
    reference: object
    pin: object
    inventory: object
    snapshot: dict | None

    def verifier(self, *, checkpoint=None, source_scope=None):
        return DestinationVerifier(self.inventory, self.target.service(),
            source_scope=source_scope or self.source.account.scope("reviewer"),
            reference=self.reference, pin=self.pin, selection_id=SELECTION, checkpoint=checkpoint)

    def call(self, verifier=None, *, scope=None, snapshot=None, reference=None):
        return (verifier or self.verifier()).dispatch(scope or self.target.account.scope("reviewer"), "verify",
            snapshot=snapshot if snapshot is not None else self.snapshot,
            reference=reference if reference is not None else asdict(self.reference))

    def protected(self):
        return one_snapshot(self.source), one_snapshot(self.target)

    def close(self):
        for f in (self.source, self.target):
            f.account.store.engine.dispose()


def make_pair(root, **options):
    root.mkdir(mode=0o700)
    source = make(root / "source")
    try:
        target = make(root / "destination")
        source.account.now = target.account.now = max(source.account.now, target.account.now)
        ref = retained_reference(source, **options)
        pin = replace(invented_pin(source, ref), destination_context_sha256=
            destination_context(target.service(), DESTINATION, SELECTION))
        s = service(source, ref, pin=pin)
        observed = s.dispatch(source.account.scope("reviewer"), "inventory")
        assert observed["state"] == "acknowledged_review_inventory"
        candidate = handoff(s, source, ref, observed)
        return Pair(source, target, ref, pin, s, candidate["handoff"])
    except BaseException:
        source.account.store.engine.dispose()
        if "target" in locals():
            target.account.store.engine.dispose()
        raise
