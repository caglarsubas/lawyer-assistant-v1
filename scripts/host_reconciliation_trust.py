"""Isolated signed-evidence resolver; no IO, signing, provisioning or activation.

All three public authorities and the selected context are constructor-owned.
The independently administered current-head callback must answer fresh challenges
with its authoritative latest selected state, including root revocation. Signature
verification cannot establish fingerprint provenance or truth of those statements.
Genuine independent provisioning, clock assurance and checkpoint-root currentness
remain external prerequisites. The optional continuity fence here is process-local:
it provides no restart, joint-rollback or clock-rollback guarantee.
"""

import hashlib
import json
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from host_reconciliation_authority import HostBinding

ROLES = ("registry", "enrollment", "checkpoint")
SCHEMAS = {role: "isolated-host-reconciliation-" + role + "-v1" for role in ROLES}
MAX_BYTES, MAX_WINDOW, BUDGET_SECONDS, ADMISSION_SECONDS = 16384, 60, 10, 2
SELECTION_FIELDS = {"record_id", "firm_id", "principal_id", "profile_id", "authority_context_sha256",
                    "scope_sha256", "source_sha256", "permission_sha256"}
WINDOW_FIELDS = {"issued_at", "expires_at"}
STATE_FIELDS = {"epoch", "sequence", "enrollment_sha256", "enrollment_status", "signer_key_ids", "signer_status"}


def _reject():
    raise ValueError("Host trust evidence withheld") from None


def _token(value, size=64):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(size) + "}", value) is None:
        _reject()
    return value


def _number(value, minimum=0):
    if type(value) is not int or not minimum <= value < 2**53:
        _reject()
    return value


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, kw_only=True)
class SelectedContext:
    record_id: str
    firm_id: str
    principal_id: str
    profile_id: str
    authority_context_sha256: str
    scope_sha256: str
    source_sha256: str
    permission_sha256: str

    def __post_init__(self):
        for name in ("record_id", "principal_id", "profile_id"):
            _token(getattr(self, name), 32)
        for name in SELECTION_FIELDS - {"record_id", "principal_id", "profile_id", "firm_id"}:
            _token(getattr(self, name))
        if type(self.firm_id) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", self.firm_id) is None:
            _reject()


@dataclass(frozen=True, kw_only=True)
class AuthorityPin:
    role: str
    key_id: str
    principal_id: str
    profile_id: str
    authority_context_sha256: str
    public_key: bytes = field(repr=False)
    fingerprint: str
    not_before: int
    expires_at: int
    revoked: bool = False

    def __post_init__(self):
        if type(self.role) is not str or self.role not in ROLES:
            _reject()
        for name in ("key_id", "principal_id", "profile_id"):
            _token(getattr(self, name), 32)
        _token(self.authority_context_sha256)
        _token(self.fingerprint)
        if (type(self.public_key) is not bytes or len(self.public_key) != 32
                or _sha(self.public_key) != self.fingerprint or type(self.revoked) is not bool
                or _number(self.not_before) >= _number(self.expires_at)):
            _reject()


@dataclass(frozen=True, kw_only=True)
class MinimumHead:
    epoch: int
    sequence: int
    registry_sha256: str

    def __post_init__(self):
        _number(self.epoch, 1)
        _number(self.sequence, 1)
        _token(self.registry_sha256)


@dataclass(frozen=True, kw_only=True)
class SignedEvidence:
    registry: bytes = field(repr=False)
    enrollment: bytes = field(repr=False)


class CurrentTrustResolver:
    """One selected context, three fixed roots, fresh before/after head checks.

    Callbacks receive no request-selected trust head. ``evidence(selection)`` returns
    SignedEvidence; ``current_head(challenge, selection)`` returns signed bytes.
    Neither callback may provision or infer independent authority. Fixed signed
    windows prevent nonce-dependent binding renewal. Unsupported rotation/epochs
    require new independently reviewed wiring. No retained receipt is accessed.
    Fresh observed heads retain their full stable state in this instance even
    after failed resolution. Same-version conflicts or an authenticated epoch
    transition retire this instance; restarting it is not an approved recovery.
    The 10-second operation budget is checked, with two-second lock admission;
    callbacks still require external transport cancellation/deadlines. These
    checks cannot interrupt a blocked callback or establish a hard timeout.
    """

    def __init__(self, selection, registry, enrollment, checkpoint, minimum_head, *, evidence, current_head, clock=None):
        if (type(selection) is not SelectedContext or type(minimum_head) is not MinimumHead
                or not callable(evidence) or not callable(current_head) or (clock is not None and not callable(clock))):
            _reject()
        selection.__post_init__()
        minimum_head.__post_init__()
        pins = (registry, enrollment, checkpoint)
        for role, pin in zip(ROLES, pins, strict=True):
            if type(pin) is not AuthorityPin:
                _reject()
            pin.__post_init__()
            if pin.role != role or pin.revoked or pin.authority_context_sha256 != selection.authority_context_sha256:
                _reject()
        for name in ("key_id", "principal_id", "profile_id", "public_key"):
            if len({getattr(pin, name) for pin in pins}) != 3:
                _reject()
        if (selection.principal_id in {pin.principal_id for pin in pins}
                or selection.profile_id in {pin.profile_id for pin in pins}):
            _reject()
        self._selection, self._minimum = selection, minimum_head
        self._pins = dict(zip(ROLES, pins, strict=True))
        self._evidence, self._current_head = evidence, current_head
        self._clock = clock if clock is not None else lambda: int(time.time())
        self._admission = threading.Lock()
        self._fence = (minimum_head.sequence, minimum_head.registry_sha256)
        self._fence_state = None
        self._retired = False

    def _now(self):
        return _number(self._clock())

    @staticmethod
    def _budget(deadline):
        if time.monotonic() >= deadline:
            _reject()

    def _checked(self, deadline, callback, *args):
        self._budget(deadline)
        result = callback(*args)
        self._budget(deadline)
        return result

    @staticmethod
    def _decode(raw):
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
            _reject()

        def unique(pairs):
            value = {}
            for name, item in pairs:
                if name in value:
                    _reject()
                value[name] = item
            return value

        value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: _reject())
        if _encode(value) != raw:
            _reject()
        return value

    def _verified(self, raw, role):
        value, pin = self._decode(raw), self._pins[role]
        if (type(value) is not dict or set(value) != {"schema", "key_id", "claims", "signature"}
                or type(value["schema"]) is not str or value["schema"] != SCHEMAS[role]
                or value["key_id"] != pin.key_id or type(value["claims"]) is not dict
                or pin.revoked or not pin.not_before <= self._now() < pin.expires_at):
            _reject()
        signature = bytes.fromhex(_token(value["signature"], 128))
        Ed25519PublicKey.from_public_bytes(pin.public_key).verify(
            signature, SCHEMAS[role].encode() + b"\0" + _encode(value["claims"]))
        return value["claims"]

    def _selection_matches(self, claims):
        for name, expected in asdict(self._selection).items():
            if type(claims[name]) is not str or claims[name] != expected:
                _reject()

    def _window(self, claims):
        issued, expiry = _number(claims["issued_at"]), _number(claims["expires_at"])
        if not 0 < expiry - issued <= MAX_WINDOW or not issued <= self._now() < expiry:
            _reject()
        if any(not pin.not_before <= issued < expiry <= pin.expires_at for pin in self._pins.values()):
            _reject()
        return issued, expiry

    def _state(self, claims, *, structure_only=False):
        _number(claims["epoch"], 1)
        _number(claims["sequence"], 1)
        if (type(claims["enrollment_status"]) is not str
                or claims["enrollment_status"] not in {"active", "revoked"}
                or type(claims["signer_key_ids"]) is not dict or set(claims["signer_key_ids"]) != set(ROLES)
                or type(claims["signer_status"]) is not dict or set(claims["signer_status"]) != set(ROLES)
                or any(type(value) is not str or value not in {"active", "revoked"}
                       for value in claims["signer_status"].values())):
            _reject()
        _token(claims["enrollment_sha256"])
        for key_id in claims["signer_key_ids"].values():
            _token(key_id, 32)
        if not structure_only and (claims["epoch"] != self._minimum.epoch
                or claims["sequence"] < self._minimum.sequence
                or claims["signer_key_ids"] != {role: pin.key_id for role, pin in self._pins.items()}
                or claims["enrollment_status"] != "active"
                or any(value != "active" for value in claims["signer_status"].values())):
            _reject()

    def _observe_head(self, claims):
        if self._retired:
            _reject()
        if claims["epoch"] != self._minimum.epoch:
            self._retired = True  # Authenticated epoch transitions require new wiring.
            _reject()
        fence = (claims["sequence"], claims["registry_sha256"])
        state = _encode({name: claims[name] for name in SELECTION_FIELDS | STATE_FIELDS | {"registry_sha256"}})
        if fence[0] < self._fence[0]:
            _reject()
        if fence[0] == self._fence[0]:
            if fence[1] != self._fence[1] or (self._fence_state is not None and state != self._fence_state):
                self._retired = True  # Same-version authority equivocation cannot be retried away.
                _reject()
        self._fence, self._fence_state = fence, state

    def _head(self, challenge, deadline):
        raw = self._checked(deadline, self._current_head, challenge, self._selection)
        claims = self._checked(deadline, self._verified, raw, "checkpoint")
        if set(claims) != SELECTION_FIELDS | STATE_FIELDS | {"challenge", "registry_sha256", "observed_at", "expires_at"}:
            _reject()
        SelectedContext(**{name: claims[name] for name in SELECTION_FIELDS})
        for name in ("record_id", "firm_id", "principal_id", "authority_context_sha256"):
            if claims[name] != getattr(self._selection, name):
                _reject()  # Another selection must not poison this instance.
        self._state(claims, structure_only=True)
        if _token(claims["challenge"], 32) != challenge:
            _reject()
        _token(claims["registry_sha256"])
        observed, expiry = _number(claims["observed_at"]), _number(claims["expires_at"])
        pin = self._pins["checkpoint"]
        if (not pin.not_before <= observed <= self._now() < expiry <= pin.expires_at
                or not 0 < expiry - observed <= MAX_WINDOW):
            _reject()
        # A fully verified fresh authority head is observed even when subsequent
        # evidence, active-state or second-head checks fail. Never forget it and
        # fall back to an older still-signed authorization in this process.
        self._observe_head(claims)
        self._selection_matches(claims)
        self._state(claims)
        return claims

    def __call__(self, record_id, firm_id, principal_id):
        acquired = False
        try:
            deadline = time.monotonic() + BUDGET_SECONDS
            if (self._retired or (record_id, firm_id, principal_id) != (self._selection.record_id, self._selection.firm_id,
                                                       self._selection.principal_id)
                    or any(type(value) is not str for value in (record_id, firm_id, principal_id))):
                _reject()
            acquired = self._admission.acquire(timeout=ADMISSION_SECONDS)
            if not acquired or self._retired:
                _reject()
            first_challenge = secrets.token_hex(16)
            first = self._head(first_challenge, deadline)
            evidence = self._checked(deadline, self._evidence, self._selection)
            if type(evidence) is not SignedEvidence:
                _reject()
            enrollment = self._checked(deadline, self._verified, evidence.enrollment, "enrollment")
            registry = self._checked(deadline, self._verified, evidence.registry, "registry")
            if (set(enrollment) != SELECTION_FIELDS | WINDOW_FIELDS | {"epoch", "sequence", "action", "status"}
                    or set(registry) != SELECTION_FIELDS | WINDOW_FIELDS | STATE_FIELDS):
                _reject()
            self._selection_matches(enrollment)
            self._selection_matches(registry)
            self._state(registry)
            issued, expiry = self._window(enrollment)
            if (self._window(registry) != (issued, expiry) or type(enrollment["action"]) is not str
                    or enrollment["action"] != "reconcile" or type(enrollment["status"]) is not str
                    or enrollment["status"] != "active" or _number(enrollment["epoch"], 1) != registry["epoch"]
                    or _number(enrollment["sequence"], 1) != registry["sequence"]
                    or registry["enrollment_sha256"] != _sha(evidence.enrollment)):
                _reject()
            registry_sha = _sha(evidence.registry)
            fence = (registry["sequence"], registry_sha)
            if fence[0] < self._fence[0] or (fence[0] == self._fence[0] and fence[1] != self._fence[1]):
                _reject()
            second_challenge = secrets.token_hex(16)
            if second_challenge == first_challenge:
                _reject()
            second = self._head(second_challenge, deadline)
            expected = {name: registry[name] for name in SELECTION_FIELDS | STATE_FIELDS}
            expected["registry_sha256"] = registry_sha
            for head in (first, second):
                if (any(head[name] != value for name, value in expected.items())
                        or head["expires_at"] < expiry or head["observed_at"] < issued):
                    _reject()
            self._window(registry)
            final_now = self._now()
            if (not issued <= final_now < expiry
                    or any(not head["observed_at"] <= final_now < head["expires_at"] for head in (first, second))):
                _reject()
            self._budget(deadline)
            return HostBinding(record_id=record_id, firm_id=firm_id, principal_id=principal_id,
                scope_sha256=self._selection.scope_sha256, source_sha256=self._selection.source_sha256,
                permission_sha256=self._selection.permission_sha256, enrollment_sha256=_sha(evidence.enrollment),
                trust_registry_sha256=registry_sha, issued_at=issued, expires_at=expiry, revision=registry["sequence"])
        except Exception:  # noqa: BLE001 - never expose callback, proof or crypto diagnostics
            _reject()
        finally:
            if acquired:
                self._admission.release()
