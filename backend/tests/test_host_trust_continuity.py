"""Restart and concurrent access with invented trust evidence and private files."""

import fcntl
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_host_reconciliation_trust import frame, sha, signers, withheld  # noqa: F401

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import host_reconciliation_trust as trust  # noqa: E402
from host_trust_continuity import HeadFence, TrustContinuityStore  # noqa: E402
from operator_enrollment_evidence import encode  # noqa: E402


@pytest.fixture
def retained(frame, tmp_path):  # noqa: F811 - reuse the signed-evidence fixture
    minimum = trust.MinimumHead(epoch=1, sequence=1, registry_sha256=sha(frame.registry))
    root = tmp_path.resolve() / "trust"
    root.mkdir(mode=0o700)
    path = root / "continuity.json"
    pins = tuple(frame.pins[role] for role in trust.ROLES)

    def resolver(store=None, selection=frame.selection):
        return trust.CurrentTrustResolver(selection, *pins, minimum, evidence=frame.evidence,
            current_head=frame.head, clock=lambda: frame.now[0], continuity=store)

    expected = {"store_id": "d" * 32, "binding_sha256": resolver().continuity_binding_sha256}
    store = TrustContinuityStore.create(path, **expected)

    def reopen():
        return resolver(TrustContinuityStore(path, **expected))

    return SimpleNamespace(frame=frame, resolver=resolver, store=store, reopen=reopen, path=path,
                           expected=expected, minimum=minimum)


def test_restart_keeps_exact_binding_and_rejects_the_previous_head(retained):
    f = retained.frame
    old = f.registry, f.enrollment
    f.build(2)
    binding = f.call(retained.reopen())
    # A new process reads the same committed observation using the configured pins.
    child = subprocess.run([sys.executable, "-c", """
import sys
import time
from host_trust_continuity import HeadFence, TrustContinuityStore
path, store_id, binding, registry = sys.argv[1:]
store = TrustContinuityStore(path, store_id=store_id, binding_sha256=binding)
minimum = HeadFence(sequence=1, registry_sha256=registry)
assert store.read(minimum, minimum, time.monotonic() + 2).sequence == 2
""", str(retained.path), retained.expected["store_id"], retained.expected["binding_sha256"],
        retained.minimum.registry_sha256], env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
        capture_output=True, timeout=5, check=False)
    assert child.returncode == 0, child.stderr.decode()
    before = retained.path.stat().st_ino
    assert f.call(retained.reopen()) == binding
    assert retained.path.stat().st_ino == before
    f.registry, f.enrollment = old
    f.current_registry = f.registry
    evidence_calls = f.evidence_calls
    withheld(lambda: f.call(retained.reopen()))
    assert f.evidence_calls == evidence_calls


@pytest.mark.parametrize("change", [{"enrollment_status": "revoked"}, {"source_sha256": "f" * 64}])
def test_higher_head_is_retained_when_authorization_fails(retained, change):
    f = retained.frame
    old = f.registry, f.enrollment
    f.build(2)
    f.head_changes = change
    withheld(lambda: f.call(retained.reopen()))
    f.head_changes = {}
    f.registry, f.enrollment = old
    f.current_registry = f.registry
    evidence_calls = f.evidence_calls
    withheld(lambda: f.call(retained.reopen()))
    assert f.evidence_calls == evidence_calls


@pytest.mark.parametrize("change", [{"epoch": 2}, {"enrollment_status": "revoked"}])
def test_retirement_survives_restart(retained, change):
    f = retained.frame
    f.call(retained.reopen())
    f.head_changes = change
    withheld(lambda: f.call(retained.reopen()))
    f.head_changes = {}
    before = len(f.head_calls), f.evidence_calls
    withheld(lambda: f.call(retained.reopen()))
    assert (len(f.head_calls), f.evidence_calls) == before


def test_competing_resolver_advance_withholds_a_resolution_in_progress(retained):
    f = retained.frame
    first = retained.reopen()

    def advance():
        f.evidence_hook = None
        old = f.registry, f.enrollment
        f.build(2)
        assert f.call(retained.reopen()).revision == 2
        f.registry, f.enrollment = old
        f.current_registry = f.registry

    f.evidence_hook = advance
    withheld(lambda: f.call(first))
    withheld(lambda: f.call(retained.reopen()))


def test_live_resolver_rejects_a_restored_older_copy(retained):
    f = retained.frame
    resolver = retained.reopen()
    f.call(resolver)
    before = retained.path.read_bytes()
    f.build(2)
    assert f.call(resolver).revision == 2
    retained.path.write_bytes(before)
    callbacks = len(f.head_calls), f.evidence_calls
    withheld(lambda: f.call(resolver))
    assert (len(f.head_calls), f.evidence_calls) == callbacks


def test_wrong_nonce_cannot_advance_the_durable_head(retained):
    f = retained.frame
    before = retained.path.read_bytes()
    f.head_changes = {"sequence": 2, "challenge": "f" * 32}
    withheld(lambda: f.call(retained.reopen()))
    assert retained.path.read_bytes() == before
    f.head_changes = {}
    assert f.call(retained.reopen()).revision == 1


@pytest.mark.parametrize("damage", ["missing", "corrupt", "unsafe_mode", "other_store", "incomplete_head", "symlink"])
def test_unavailable_continuity_withholds_before_fetching_evidence(retained, damage):
    f, path = retained.frame, retained.path
    f.call(retained.reopen())
    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        path.write_bytes(b"broken")
    elif damage == "unsafe_mode":
        path.chmod(0o644)
    elif damage == "symlink":
        other = path.with_name("other.json")
        path.rename(other)
        path.symlink_to(other)
    else:
        record = json.loads(path.read_bytes())
        if damage == "other_store":
            record["store_id"] = "e" * 32
        else:
            del record["head"]["retired"]
        path.write_bytes(encode(record))
    before = len(f.head_calls), f.evidence_calls
    withheld(lambda: f.call(retained.reopen()))
    assert (len(f.head_calls), f.evidence_calls) == before
    if damage == "missing":
        assert not path.exists()


def test_wiring_and_exclusive_bootstrap(retained):
    withheld(lambda: retained.resolver(retained.store, replace(retained.frame.selection, source_sha256="e" * 64)))
    before = retained.path.read_bytes()
    with pytest.raises(FileExistsError):
        TrustContinuityStore.create(retained.path, **retained.expected)
    assert retained.path.read_bytes() == before


def test_failed_replacement_withholds_and_retires_the_live_resolver(retained, monkeypatch):
    f = retained.frame
    resolver = retained.reopen()
    binding = f.call(resolver)
    before = retained.path.read_bytes()
    f.build(2)

    def fail(*args, **kwargs):
        raise OSError("invented replacement failure")

    with monkeypatch.context() as changes:
        changes.setattr(os, "replace", fail)
        withheld(lambda: f.call(resolver))
    assert retained.path.read_bytes() == before
    assert list(retained.path.parent.iterdir()) == [retained.path]
    assert resolver._retired and binding.revision == 1
    withheld(lambda: f.call(resolver))


def test_lock_wait_respects_the_supplied_deadline(retained):
    minimum = HeadFence(sequence=1, registry_sha256=retained.minimum.registry_sha256)
    fd = os.open(retained.path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        start = time.monotonic()
        with pytest.raises(ValueError, match="continuity unavailable"):
            retained.store.read(minimum, minimum, start + 0.02)
        assert time.monotonic() - start < 1
    finally:
        os.close(fd)
