"""Invented pin issuer for disposable tests, never genuine trust provisioning."""

from dataclasses import asdict

import operator_enrollment_evidence as e
from operator_recovery_inputs import DECISIONS
from qualify_recovery_inputs import prepare
from recovery_review_inventory import DestinationPin, Reference, ReviewInventory

ENTRY, OTHER_ENTRY, DESTINATION = "3" * 32, "4" * 32, "5" * 32


def retained_reference(f, *, decision="accept", acknowledged=True):
    prepared, refs = prepare(f)
    cipher = None
    if decision is not None:
        response = f.service().dispatch(f.account.scope("reviewer"), "decide", **refs,
            expected_input_sha256=prepared["input_sha256"], decision=decision, reason_code=DECISIONS[decision])
        assert response["state"] == "independent_review_recorded"
        if acknowledged:
            cipher = response["decision_ciphertext_sha256"]
    return Reference(**refs, decision_ciphertext_sha256=cipher)


def invented_pin(f, ref):
    service = f.service()
    review = service.read_review(asdict(ref))
    return DestinationPin(destination_id=DESTINATION, entry_id=ENTRY,
        destination_context_sha256=e.sha(b"INVENTED externally retained target context"),
        reference_sha256=ref.sha256, review_context_sha256=service.context(),
        selection_sha256=review["selection_sha256"],
        journal_pins_sha256=e.sha(e.encode(asdict(f.journal_pins))), expires_at=f.account.now + 240)


def service(f, ref, *, pin=None, checkpoint=None, references=None):
    return ReviewInventory(f.service(), references or {ENTRY: ref},
        {DESTINATION: pin} if pin is not None else {}, checkpoint=checkpoint)


def handoff(s, f, ref, observed):
    return s.dispatch(f.account.scope("reviewer"), "handoff", entry_id=ENTRY, reference=asdict(ref),
        destination_id=DESTINATION, expected_inventory_sha256=observed["inventory"]["inventory_sha256"])
