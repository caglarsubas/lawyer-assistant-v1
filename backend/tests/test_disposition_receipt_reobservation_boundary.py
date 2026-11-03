"""Fresh authorized reads of pinned metadata using disposable encrypted histories."""

import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import disposition_receipt_reobservation as r  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from test_disposition_journal_reconciliation import body, protected  # noqa: E402
from test_disposition_journal_reconciliation import f as f  # noqa: E402
from test_disposition_receipt_reobservation import call, retained, safe  # noqa: E402


@pytest.mark.parametrize("kind", ["other", "revoked", "csrf", "origin", "cookie", "method"])
def test_fresh_authentication_precedes_inspection_of_retained_private_bytes(f, kind):
    service, raw = retained(f, body(f))
    scope = f.scope("other" if kind == "other" else "preparer")
    if kind == "revoked":
        f.revoke("preparer")
    elif kind in {"csrf", "origin"}:
        key = b"origin" if kind == "origin" else b"x-csrf-token"
        scope["headers"] = [(k, b"invalid" if k == key else v) for k, v in scope["headers"]]
    elif kind == "cookie":
        scope["headers"].append((b"cookie", b"la_session=invalid"))
    elif kind == "method":
        scope["method"] = "GET"
    before = protected(f)
    with patch.object(r, "retained", side_effect=AssertionError("Private bytes must remain unread")) as check:
        safe(call(f, service, raw, scope), "denied")
        check.assert_not_called()
    assert protected(f) == before


@pytest.mark.parametrize("kind", ["digest", "noncanonical", "duplicate", "extra", "binding", "future", "flag", "decision", "type", "size"])
def test_checksum_and_closed_canonical_schema_are_required_but_never_authority(f, kind):
    service, raw = retained(f, body(f))
    value = e.decode(raw)
    if kind == "noncanonical":
        raw += b"\n"
    elif kind == "duplicate":
        raw = raw[:-1] + b',"schema":"disposition-reconciliation-receipt-v1"}'
    elif kind == "type":
        raw = raw.decode()
    elif kind == "size":
        raw = b"x" * 8193
    elif kind != "digest":
        if kind == "extra":
            value["root"] = "/SYNTHETIC-private-path"
        elif kind == "binding":
            value["binding_sha256"] = "f" * 64
        elif kind == "future":
            value["issued_at"] = f.now + 1
        elif kind == "flag":
            value["read_only"] = 1  # Equality with True must not grant structural validity.
        else:
            value["decision_authenticated"] = True
        raw = e.encode(value)
    service = replace(service, expected_receipt_sha256="f" * 64 if kind == "digest" else e.sha(raw if isinstance(raw, bytes) else raw.encode()))
    before = protected(f)
    safe(call(f, service, raw), "unverifiable")
    assert protected(f) == before


def test_closed_operation_and_trusted_digest_cannot_be_overridden_in_a_request(f):
    service, raw = retained(f, body(f))
    before = protected(f)
    for operation, extra in [("execute", {}), ("import", {}), ("reobserve", {"expected_receipt_sha256": e.sha(raw)}),
                             ("reobserve", {"root": "/SYNTHETIC-private-path"})]:
        safe(call(f, service, raw, operation=operation, **extra), "unverifiable")
    assert protected(f) == before


