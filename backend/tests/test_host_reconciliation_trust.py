"""Invented signed metadata and local host identities; no production trust."""

import hashlib
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from test_host_reconciliation_authority import host  # noqa: F401 (small SQLite host fixture)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import host_reconciliation_trust as trust  # noqa: E402


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def signers():
    # Invented test-only authorities, never provisioned or persisted.
    return {role: Ed25519PrivateKey.generate() for role in trust.ROLES}


def make(signers, *, now=None):
    f = SimpleNamespace(now=[int(time.time()) if now is None else now], head_calls=[], evidence_calls=0,
                        head_changes={}, head_hook=None, evidence_hook=None)
    f.selection = trust.SelectedContext(record_id="2" * 32, firm_id="invented-firm", principal_id="1" * 32,
        profile_id="3" * 32, authority_context_sha256="0" * 64, scope_sha256="a" * 64,
        source_sha256="b" * 64, permission_sha256="c" * 64)
    f.pins = {}
    for index, role in enumerate(trust.ROLES, 4):
        public = signers[role].public_key().public_bytes_raw()
        f.pins[role] = trust.AuthorityPin(role=role, key_id=str(index) * 32, principal_id=str(index + 3) * 32,
            profile_id=hex(index + 6)[2:] * 32, authority_context_sha256=f.selection.authority_context_sha256,
            public_key=public, fingerprint=sha(public), not_before=f.now[0] - 10, expires_at=f.now[0] + 1000)
    f.window = {"issued_at": f.now[0] - 1, "expires_at": f.now[0] + 50}

    def signed(role, claims, *, key=None, **envelope):
        schema = trust.SCHEMAS[role]
        raw_signature = (signers[role] if key is None else key).sign(schema.encode() + b"\0" + encode(claims))
        return encode({"schema": schema, "key_id": f.pins[role].key_id, "claims": claims,
                       "signature": raw_signature.hex(), **envelope})
    f.signed = signed

    def build(sequence=1):
        selection = asdict(f.selection)
        f.enrollment_claims = {**selection, **f.window, "epoch": 1, "sequence": sequence,
                               "action": "reconcile", "status": "active"}
        f.enrollment = signed("enrollment", f.enrollment_claims)
        f.registry_claims = {**selection, **f.window, "epoch": 1, "sequence": sequence,
            "enrollment_sha256": sha(f.enrollment), "enrollment_status": "active",
            "signer_key_ids": {role: pin.key_id for role, pin in f.pins.items()},
            "signer_status": dict.fromkeys(trust.ROLES, "active")}
        f.registry = signed("registry", f.registry_claims)
        f.current_registry = f.registry
    f.build = build
    build()

    def evidence(selection):
        assert selection is f.selection
        f.evidence_calls += 1
        if f.evidence_hook:
            f.evidence_hook()
        return trust.SignedEvidence(registry=f.registry, enrollment=f.enrollment)

    def head(challenge, selection):
        assert selection is f.selection and type(challenge) is str and len(challenge) == 32
        f.head_calls.append(challenge)
        if f.head_hook:
            f.head_hook()
        registry = json.loads(f.current_registry)["claims"]
        claims = {name: registry[name] for name in trust.SELECTION_FIELDS | trust.STATE_FIELDS}
        claims.update(challenge=challenge, registry_sha256=sha(f.current_registry), observed_at=f.now[0],
                      expires_at=f.window["expires_at"])
        claims.update(f.head_changes)
        return signed("checkpoint", claims)

    f.evidence, f.head = evidence, head

    def resolver():
        return trust.CurrentTrustResolver(f.selection, *(f.pins[role] for role in trust.ROLES),
            trust.MinimumHead(epoch=1, sequence=1, registry_sha256=sha(f.registry)), evidence=evidence,
            current_head=head, clock=lambda: f.now[0])
    f.resolver = resolver
    f.call = lambda r: r(f.selection.record_id, f.selection.firm_id, f.selection.principal_id)
    return f


@pytest.fixture
def frame(signers):
    return make(signers)


def withheld(call):
    with pytest.raises(ValueError) as held:
        call()
    assert str(held.value) == "Host trust evidence withheld"
    assert held.value.__suppress_context__


def test_valid_repeated_resolution_is_exact_and_nonrenewing(frame):
    f, resolver = frame, frame.resolver()
    first = f.call(resolver)
    f.now[0] += 1
    f.head_changes["expires_at"] = f.window["expires_at"] + 5
    second = f.call(resolver)
    assert first == second and encode(asdict(first)) == encode(asdict(second))
    assert first.trust_registry_sha256 == sha(f.registry)
    assert first.enrollment_sha256 == sha(f.enrollment)
    assert first.issued_at == f.window["issued_at"] and first.expires_at == f.window["expires_at"]
    assert len(set(f.head_calls)) == 4 and f.evidence_calls == 2
    assert "signature" not in asdict(first) and "public_key" not in asdict(first)


@pytest.mark.parametrize("field", sorted(trust.SELECTION_FIELDS))
@pytest.mark.parametrize("artifact", ["registry", "enrollment", "checkpoint"])
def test_signed_selection_or_digest_substitution_is_withheld(frame, field, artifact):
    f = frame
    value = "foreign" if field == "firm_id" else "f" * len(asdict(f.selection)[field])
    if artifact == "checkpoint":
        f.head_changes[field] = value
    elif artifact == "registry":
        f.registry_claims[field] = value
        f.registry = f.current_registry = f.signed("registry", f.registry_claims)
    else:
        f.enrollment_claims[field] = value
        f.enrollment = f.signed("enrollment", f.enrollment_claims)
        f.registry_claims["enrollment_sha256"] = sha(f.enrollment)
        f.registry = f.current_registry = f.signed("registry", f.registry_claims)
    withheld(lambda: f.call(f.resolver()))


@pytest.mark.parametrize("role", trust.ROLES)
@pytest.mark.parametrize("change", ["signature", "key_id", "schema", "unknown", "wrong_signer"])
def test_envelope_and_authority_substitution(frame, role, change):
    f = frame
    def corrupted(raw):
        value = json.loads(raw)
        if change == "wrong_signer":
            return f.signed(role, value["claims"], key=Ed25519PrivateKey.generate())
        value[{"signature": "signature", "key_id": "key_id", "schema": "schema", "unknown": "extra"}[change]] = (
            "0" * 128 if change == "signature" else "wrong")
        return encode(value)

    resolver = f.resolver()
    if role == "checkpoint":
        resolver._current_head = lambda *args: corrupted(f.head(*args))
    else:
        def altered(selection):
            evidence = f.evidence(selection)
            return replace(evidence, **{role: corrupted(getattr(evidence, role))})
        resolver._evidence = altered
    withheld(lambda: f.call(resolver))


@pytest.mark.parametrize("role", trust.ROLES)
@pytest.mark.parametrize("field,value", [("revoked", True), ("role", "other"), ("fingerprint", "f" * 64),
                                          ("authority_context_sha256", "f" * 64)])
def test_invalid_constructor_roots_fail_closed(frame, role, field, value):
    def invalid():
        frame.pins[role] = replace(frame.pins[role], **{field: value})
        frame.resolver()
    withheld(invalid)


@pytest.mark.parametrize("field", ["key_id", "principal_id", "profile_id", "public_key"])
def test_roots_are_distinct_and_independent_of_recipient(frame, field):
    source = frame.pins["registry"]
    changes = {field: getattr(source, field)}
    if field == "public_key":
        changes["fingerprint"] = source.fingerprint
    frame.pins["checkpoint"] = replace(frame.pins["checkpoint"], **changes)
    withheld(frame.resolver)


@pytest.mark.parametrize("role", trust.ROLES)
def test_signed_revocation_of_each_authority_is_withheld(frame, role):
    frame.registry_claims["signer_status"][role] = "revoked"
    frame.registry = frame.current_registry = frame.signed("registry", frame.registry_claims)
    withheld(lambda: frame.call(frame.resolver()))


@pytest.mark.parametrize("artifact,field,value", [
    ("registry", "enrollment_status", "revoked"), ("enrollment", "status", "revoked"),
    ("enrollment", "action", "retain"), ("registry", "enrollment_sha256", "f" * 64),
    ("checkpoint", "enrollment_sha256", "f" * 64), ("checkpoint", "registry_sha256", "f" * 64),
    ("checkpoint", "enrollment_status", "revoked"), ("checkpoint", "epoch", True),
    ("checkpoint", "sequence", True), ("checkpoint", "observed_at", True),
    ("checkpoint", "expires_at", True), ("enrollment", "issued_at", True),
    ("registry", "sequence", 1.0), ("enrollment", "sequence", 1.0),
])
def test_status_hash_action_and_strict_type_rejections(frame, artifact, field, value):
    if artifact == "checkpoint":
        frame.head_changes[field] = value
    else:
        claims = getattr(frame, artifact + "_claims")
        claims[field] = value
        setattr(frame, artifact, frame.signed(artifact, claims))
        if artifact == "enrollment":
            frame.registry_claims["enrollment_sha256"] = sha(frame.enrollment)
            frame.registry = frame.signed("registry", frame.registry_claims)
        frame.current_registry = frame.registry
    withheld(lambda: frame.call(frame.resolver()))


def test_still_valid_old_evidence_rejected_after_independent_head_advances(frame):
    resolver = frame.resolver()
    old = frame.registry, frame.enrollment
    frame.build(sequence=2)
    frame.registry, frame.enrollment = old
    assert frame.now[0] < frame.window["expires_at"]
    withheld(lambda: frame.call(resolver))


def test_in_process_fence_rejects_rollback_and_same_sequence_equivocation(frame):
    resolver = frame.resolver()
    old = frame.registry, frame.enrollment
    frame.build(sequence=2)
    assert frame.call(resolver).revision == 2
    frame.registry, frame.enrollment = old
    frame.current_registry = frame.registry
    before = frame.evidence_calls
    withheld(lambda: frame.call(resolver))
    assert frame.evidence_calls == before
    frame.build(sequence=2)
    frame.registry_claims["expires_at"] -= 1
    frame.registry = frame.current_registry = frame.signed("registry", frame.registry_claims)
    withheld(lambda: frame.call(resolver))
    assert frame.evidence_calls == before


def test_changed_head_between_checkpoints_is_withheld(frame):
    def change():
        if len(frame.head_calls) == 2:
            old = frame.registry, frame.enrollment
            frame.build(sequence=2)
            frame.registry, frame.enrollment = old
    frame.head_hook = change
    withheld(lambda: frame.call(frame.resolver()))


@pytest.mark.parametrize("failure", ["evidence_error", "second_head_change", "revoked_head",
                                     "revoked_registry", "revoked_enrollment", "revoked_checkpoint"])
def test_fresh_higher_head_is_retained_after_failed_resolution(frame, failure):
    resolver = frame.resolver()
    old = frame.registry, frame.enrollment
    if failure == "second_head_change":
        def change():
            if len(frame.head_calls) == 2:
                frame.build(sequence=2)
        frame.head_hook = change
    else:
        frame.build(sequence=2)
        if failure == "revoked_head":
            frame.head_changes["enrollment_status"] = "revoked"
        elif failure.startswith("revoked_"):
            frame.head_changes["signer_status"] = {role: "revoked" if role == failure.removeprefix("revoked_")
                                                   else "active" for role in trust.ROLES}
        else:
            def fail():
                raise RuntimeError("invented failed evidence acquisition")
            frame.evidence_hook = fail
    withheld(lambda: frame.call(resolver))
    assert resolver._fence[0] == 2
    frame.head_hook = frame.evidence_hook = None
    frame.head_changes = {}
    frame.registry, frame.enrollment = old
    frame.current_registry = frame.registry
    before = frame.evidence_calls
    withheld(lambda: frame.call(resolver))
    assert frame.evidence_calls == before


def test_nonce_replay_cannot_supply_current_head(frame):
    resolver = frame.resolver()
    old = frame.head("f" * 32, frame.selection)
    resolver._current_head = lambda *_: old
    withheld(lambda: frame.call(resolver))


def test_final_time_sample_must_cover_both_head_observations(frame):
    def retreat():
        if len(frame.head_calls) == 2:
            frame.now[0] -= 1
    frame.head_hook = retreat
    withheld(lambda: frame.call(frame.resolver()))


@pytest.mark.parametrize("role", ["subject", *trust.ROLES])
@pytest.mark.parametrize("initial_active", [True, False])
def test_same_version_revocation_then_active_replay_retires_instance(frame, role, initial_active):
    resolver = frame.resolver()
    if initial_active:
        frame.call(resolver)
    if role == "subject":
        frame.head_changes["enrollment_status"] = "revoked"
    else:
        frame.head_changes["signer_status"] = {name: "revoked" if name == role else "active" for name in trust.ROLES}
    withheld(lambda: frame.call(resolver))
    assert resolver._retired is initial_active
    before = len(frame.head_calls), frame.evidence_calls
    frame.head_changes = {}
    withheld(lambda: frame.call(resolver))
    assert resolver._retired and frame.evidence_calls == before[1]
    if initial_active:
        assert len(frame.head_calls) == before[0]


@pytest.mark.parametrize("field", ["source_sha256", "scope_sha256", "permission_sha256", "profile_id",
                                 "enrollment_sha256", "registry_sha256", "signer_key_ids"])
def test_same_version_material_or_key_conflict_retires_instance(frame, field):
    resolver = frame.resolver()
    frame.call(resolver)
    if field == "signer_key_ids":
        frame.head_changes[field] = {**frame.registry_claims[field], "enrollment": "f" * 32}
    else:
        expected = asdict(frame.selection).get(field, "0" * 64)
        frame.head_changes[field] = "f" * len(expected)
    before = frame.evidence_calls
    withheld(lambda: frame.call(resolver))
    assert resolver._retired and frame.evidence_calls == before
    frame.head_changes = {}
    withheld(lambda: frame.call(resolver))


@pytest.mark.parametrize("field", ["source_sha256", "scope_sha256", "permission_sha256", "profile_id"])
def test_higher_material_context_head_is_retained_before_context_rejection(frame, field):
    resolver = frame.resolver()
    frame.call(resolver)
    frame.head_changes.update(sequence=2, **{field: "f" * len(asdict(frame.selection)[field])})
    before = frame.evidence_calls
    withheld(lambda: frame.call(resolver))
    assert resolver._fence[0] == 2 and frame.evidence_calls == before
    frame.head_changes = {}
    withheld(lambda: frame.call(resolver))
    assert frame.evidence_calls == before


@pytest.mark.parametrize("field", ["record_id", "firm_id", "principal_id", "authority_context_sha256"])
def test_unrelated_identity_head_does_not_poison_selected_context(frame, field):
    resolver = frame.resolver()
    value = "foreign" if field == "firm_id" else "f" * len(asdict(frame.selection)[field])
    frame.head_changes.update(sequence=2, **{field: value})
    withheld(lambda: frame.call(resolver))
    assert resolver._fence[0] == 1 and not resolver._retired
    frame.head_changes = {}
    assert frame.call(resolver).record_id == frame.selection.record_id


def test_authenticated_unsupported_epoch_retires_instance(frame):
    resolver = frame.resolver()
    frame.head_changes["epoch"] = 2
    withheld(lambda: frame.call(resolver))
    assert resolver._retired
    frame.head_changes = {}
    withheld(lambda: frame.call(resolver))


@pytest.mark.parametrize("change", ["short_lease", "late", "future", "oversized_window", "mismatched_window", "expired_pin"])
def test_expiry_and_fixed_window_checks(frame, change):
    if change == "short_lease":
        frame.head_changes["expires_at"] = frame.window["expires_at"] - 1
    elif change == "late":
        frame.evidence_hook = lambda: frame.now.__setitem__(0, frame.window["expires_at"])
    elif change == "future":
        frame.head_changes["observed_at"] = frame.now[0] + 1
    elif change == "expired_pin":
        frame.pins["registry"] = replace(frame.pins["registry"], expires_at=frame.now[0])
    else:
        if change == "oversized_window":
            frame.window["expires_at"] = frame.now[0] + 61
            frame.build()
        else:
            frame.registry_claims["expires_at"] -= 1
            frame.registry = frame.current_registry = frame.signed("registry", frame.registry_claims)
    withheld(lambda: frame.call(frame.resolver()))


@pytest.mark.parametrize("kind", ["duplicate", "noncanonical", "oversized", "unknown", "bad_json"])
def test_strict_bounded_wire_format(frame, kind):
    if kind == "duplicate":
        raw = b'{"schema":"x","schema":"x"}'
    elif kind == "noncanonical":
        raw = b" " + frame.enrollment
    elif kind == "oversized":
        raw = b" " * (trust.MAX_BYTES + 1)
    elif kind == "unknown":
        claims = {**frame.enrollment_claims, "extra": 1}
        raw = frame.signed("enrollment", claims)
    else:
        raw = b"{"
    frame.enrollment = raw
    withheld(lambda: frame.call(frame.resolver()))


def test_wrong_call_selection_does_not_invoke_callbacks(frame):
    resolver = frame.resolver()
    withheld(lambda: resolver("f" * 32, frame.selection.firm_id, frame.selection.principal_id))
    assert not frame.head_calls and frame.evidence_calls == 0


def test_callback_failure_is_sanitized_and_lock_is_released(frame):
    resolver = frame.resolver()
    def fail(*_):
        raise RuntimeError("invented-private-diagnostic")
    resolver._current_head = fail
    withheld(lambda: frame.call(resolver))
    resolver._current_head = frame.head
    assert frame.call(resolver).record_id == frame.selection.record_id


def test_admission_is_bounded_and_checked_budget_withholds_late_callback(frame, monkeypatch):
    resolver = frame.resolver()
    class Busy:
        def acquire(self, *, timeout):
            assert timeout == 2
            return False
        def release(self):
            pytest.fail("Unacquired lock released")
    resolver._admission = Busy()
    withheld(lambda: frame.call(resolver))
    assert not frame.head_calls
    resolver = frame.resolver()
    elapsed = [0]
    monkeypatch.setattr(trust.time, "monotonic", lambda: elapsed[0])
    def late(*args):
        result = frame.head(*args)
        elapsed[0] = 10
        return result
    resolver._current_head = late
    withheld(lambda: frame.call(resolver))
    assert frame.evidence_calls == 0


def test_real_host_authentication_precedes_trust_callbacks(host, signers):  # noqa: F811
    frame = make(signers, now=host.now[0])
    host.gate._resolver = frame.resolver()
    scope = {**host.scope, "headers": [(key, b"wrong" if key == b"x-csrf-token" else value)
                                      for key, value in host.scope["headers"]]}
    with pytest.raises(HTTPException) as held:
        host.gate.authorize(scope, host.body)
    assert held.value.status_code == 403 and not frame.head_calls and frame.evidence_calls == 0


def test_real_host_grant_rechecks_exact_binding_and_cannot_renew(host, signers):  # noqa: F811
    frame = make(signers, now=host.now[0])
    host.gate._resolver = frame.resolver()
    grant = host.gate.authorize(host.scope, host.body)
    host.now[0] += 1
    frame.now[0] += 1
    assert host.gate.recheck(grant, host.scope) is grant
    assert grant._expires_at == frame.window["expires_at"]
    frame.build(sequence=2)
    with pytest.raises(HTTPException) as held:
        host.gate.recheck(grant, host.scope)
    assert held.value.status_code == 403 and held.value.detail == "Host admission withheld"


def test_real_host_withholds_revocation_and_sanitizes_callback_failure(host, signers):  # noqa: F811
    frame = make(signers, now=host.now[0])
    resolver = frame.resolver()
    host.gate._resolver = resolver
    grant = host.gate.authorize(host.scope, host.body)
    frame.head_changes["enrollment_status"] = "revoked"
    with pytest.raises(HTTPException) as held:
        host.gate.recheck(grant, host.scope)
    assert held.value.detail == "Host admission withheld"
    assert host.guards.active == 0
