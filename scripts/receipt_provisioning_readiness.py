"""Read-only comparison with independent fixture pins; never provision authority."""

from dataclasses import dataclass
from pathlib import Path

import operator_enrollment_evidence as e
import private_inventory_receipts as receipts
from receipt_stage_manifest import inspect_stage


def fingerprint(key):
    if not isinstance(key, bytes) or len(key) != 32:
        e.reject()
    return e.sha(b"private-receipt-key-fingerprint-v1\0" + key)


@dataclass(frozen=True, kw_only=True)
class Pins:
    context_id: str
    scope_sha256: str
    key_fingerprint: str
    store_identity: tuple
    profile_id: str
    profile_sha256: str

    def __post_init__(self):
        for value in (self.context_id, self.profile_id):
            e.token(value, 32)
        for value in (self.scope_sha256, self.key_fingerprint, self.profile_sha256):
            e.token(value)
        if (not isinstance(self.store_identity, tuple) or len(self.store_identity) != 2
                or any(type(n) is not int or n < 0 for n in self.store_identity)):
            e.reject()


def assess(stage, approved_manifest_sha256, store, profile_path, pins, *, require_readonly=True):
    """Consistency of independently provided fixture pins is not custody/appointment approval."""
    checks = dict.fromkeys(("package", "store_binding", "key_binding", "disposable_profile"), "not_checked")
    result = {"schema": "receipt-provisioning-readiness-v1", "state": "blocked", "checks": checks,
              "read_only": True, "key_custody": "unassessed", "operator_appointments": "unassessed",
              "kernel_readonly_required": require_readonly, **dict.fromkeys(e.FLAGS, False)}
    gate = "package"
    try:
        if not isinstance(pins, Pins) or not isinstance(store, receipts.ReceiptStore):
            e.reject()
        inspect_stage(stage, approved_manifest_sha256, require_readonly=require_readonly)
        checks[gate] = "verified"
        gate = "store_binding"
        receipts._root(store)
        if (store.context_id != pins.context_id or store.scope_sha256 != pins.scope_sha256
                or store.identity != pins.store_identity):
            e.reject()
        checks[gate] = "verified"
        gate = "key_binding"
        if fingerprint(store.key) != pins.key_fingerprint:
            e.reject()
        checks[gate] = "verified"
        gate = "disposable_profile"
        raw = e.read(Path(profile_path))
        marker = e.decode(raw)
        if (e.sha(raw) != pins.profile_sha256 or not isinstance(marker, dict)
                or set(marker) != {"schema", "profile_id", "production_activation"}
                or marker["schema"] != "disposable-operator-review-v1" or marker["profile_id"] != pins.profile_id
                or marker["production_activation"] is not False):
            e.reject()
        checks[gate] = "verified"
        result["state"] = "ready_for_disposable_validation"
    except Exception:
        checks[gate] = "blocked"  # Only gate codes; never paths, key material or private metadata.
    return result
