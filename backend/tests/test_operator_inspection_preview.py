"""Private disposable preview and independent-entry workflow; no live account store."""

import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import operator_checksum_handoff as h  # noqa: E402
import operator_inspection_preview as ui  # noqa: E402
from test_disposition_journal_reconciliation import protected  # noqa: E402
from test_operator_checksum_handoff import SOURCE, payload, prepared  # noqa: E402
from test_operator_checksum_handoff import f as f  # noqa: E402


def preview(f):
    adapter, target = prepared(f)
    return ui.OperatorInspectionPreview(adapter=adapter, source_id=SOURCE,
        expected_handoff_sha256=target.sha256), target


def request(f, app, path=ui.PREVIEW, *, role="reviewer", method="POST", data=None, extra=None, replace=None):
    async def run():
        rows = [(k.decode(), v.decode()) for k, v in f.scope(role)["headers"]]
        if method == "POST":
            rows.append(("content-type", "application/json"))
        if path == ui.SESSION:
            rows.append(("x-operator-preview", "1"))
        if replace is not None:
            rows = replace
        rows += extra or []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://operator.invalid") as c:
            return await c.request(method, path, headers=rows, content=None if method == "GET" else h.e.encode({} if data is None else data))
    return asyncio.run(run())


def withheld(response, status):
    assert response.status_code == status and response.headers["cache-control"] == "no-store"
    value = response.json()
    assert value["preview"] is value["preview_sha256"] is None
    assert value["receipt_checksum_disclosed"] is value["independent_entry_prefilled"] is False
    return value


def test_complete_preview_then_independent_entry_uses_unchanged_reobserver(f):
    app, target = preview(f)
    before = protected(f)
    session = request(f, app, ui.SESSION, method="GET")
    assert session.status_code == 200 and session.json()["csrf_token"] == f.csrf["reviewer"]
    assert session.headers["cache-control"] == "no-store" and "access-control-allow-origin" not in session.headers
    response = request(f, app)
    value = response.json()
    assert response.status_code == 200 and value["state"] == "prepared_handoff_inspected"
    assert value["preview_sha256"] == h.e.sha(h.e.encode(value["preview"]))
    assert value["preview"] == {"source_id": SOURCE, "handoff_sha256": target.sha256,
        "provenance_sha256": target.provenance_sha256, "prepared_at": target.created_at,
        "expires_at": target.created_at + 300}
    assert target.receipt_sha256 not in response.text and f.csrf["reviewer"] not in response.text
    assert str(f.root) not in response.text and len(response.content) <= ui.MAX_OUTPUT
    # A copied preview cannot supply the independent checksum; it deliberately omits it.
    withheld(request(f, app, data={"independent_receipt_sha256": target.receipt_sha256}), 400)
    compared = request(f, app, h.PATH, data=payload(target))
    assert compared.status_code == 200 and compared.json()["state"] == "staged_handoff_reobserved"
    assert compared.json()["observation"]["provenance_sender_authenticated"] is False
    assert protected(f) == before


def test_generic_shell_contains_no_private_pins_and_only_hash_authorized_assets(f):
    app, target = preview(f)
    with patch.object(h, "validate", side_effect=AssertionError("no private inspection on GET")):
        response = request(f, app, ui.PAGE, method="GET", replace=[])
    assert response.status_code == 200 and response.content == ui.HTML
    for secret in [target.receipt_sha256, target.sha256, target.provenance_sha256, f.cookies["reviewer"], f.csrf["reviewer"]]:
        assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "unsafe-inline" not in ui.CSP and "frame-ancestors 'none'" in ui.CSP
    import re
    for kind in ["style", "script"]:
        for source in re.findall(rb"<" + kind.encode() + rb">(.*?)</" + kind.encode() + rb">", ui.HTML, re.S):
            assert "'sha256-" + base64.b64encode(hashlib.sha256(source).digest()).decode() + "'" in ui.CSP
    assert not re.search(r'<input\b[^>]*\bvalue=', response.text) and 'localStorage' not in response.text


@pytest.mark.parametrize("role", ["preparer", "other"])
def test_unassigned_or_self_review_cannot_bootstrap_or_read_private_body(f, role):
    app, target = preview(f)
    before = protected(f)
    with patch.object(h, "body", side_effect=AssertionError("must not read private body")):
        withheld(request(f, app, role=role), 403)
    withheld(request(f, app, ui.SESSION, method="GET", role=role), 403)
    assert protected(f) == before


@pytest.mark.parametrize("change", ["revoked", "missing_csrf", "foreign_origin", "duplicate_cookie"])
def test_current_admission_precedes_preview_inspection(f, change):
    app, target = preview(f)
    rows = [(k.decode(), v.decode()) for k, v in f.scope("reviewer")["headers"]] + [("content-type", "application/json")]
    if change == "revoked":
        f.revoke("reviewer")
    elif change == "missing_csrf":
        rows = [(k, v) for k, v in rows if k != "x-csrf-token"]
    elif change == "foreign_origin":
        rows = [(k, "https://foreign.invalid" if k == "origin" else v) for k, v in rows]
    else:
        rows.append(("cookie", "la_session=invalid"))
    with patch.object(h, "body", side_effect=AssertionError("must not read body")):
        withheld(request(f, app, replace=rows), 403)


def test_session_bootstrap_cannot_be_embedded_cross_origin_or_supplied_identity(f):
    app, target = preview(f)
    base = [(k.decode(), v.decode()) for k, v in f.scope("reviewer")["headers"]]
    withheld(request(f, app, ui.SESSION, method="GET", replace=base), 403)
    hostile = [(k, "https://foreign.invalid" if k == "origin" else v) for k, v in base] + [("x-operator-preview", "1")]
    withheld(request(f, app, ui.SESSION, method="GET", replace=hostile), 403)
    withheld(request(f, app, ui.SESSION + "?user=other", method="GET"), 400)
    with patch.object(h, "validate", side_effect=AssertionError("session must not inspect private provenance")):
        assert request(f, app, ui.SESSION, method="GET").status_code == 200


@pytest.mark.parametrize("change", ["reviewer", "preparer", "expiry", "pin", "clock", "internal", "lookup"])
def test_late_changes_withhold_whole_preview_and_keep_histories(f, change):
    app, target = preview(f)
    before = protected(f)
    original = h.validate
    calls = 0
    def late(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            if change in {"reviewer", "preparer"}:
                f.revoke(change)
            elif change == "expiry":
                f.now += 301
            elif change == "pin":
                object.__setattr__(target, "provenance_sha256", "0" * 64)
            elif change == "clock":
                f.now -= 1
            else:
                raise (LookupError if change == "lookup" else RuntimeError)("SYNTHETIC private diagnostic")
        return original(*args)
    status = {"reviewer":403,"preparer":403,"expiry":409,"pin":400,"clock":409,"internal":503,"lookup":503}[change]
    with patch.object(h, "validate", late):
        value = withheld(request(f, app), status)
    assert "SYNTHETIC" not in json.dumps(value) and protected(f) == before


def test_bounded_closed_requests_and_wrong_preparation_are_not_silently_replaced(f):
    app, target = preview(f)
    before = protected(f)
    for data in [{"source_id":"0"*32}, {"receipt_sha256": target.receipt_sha256}, [], "{}"]:
        withheld(request(f, app, data=data), 400)
    withheld(request(f, app, ui.PREVIEW + "?source=other"), 400)
    withheld(request(f, app, method="GET"), 405)
    withheld(request(f, app, ui.PREVIEW + "/execute"), 404)
    with pytest.raises(ValueError):
        ui.OperatorInspectionPreview(adapter=app.adapter, source_id=SOURCE, expected_handoff_sha256="0"*64)
    with patch.object(ui, "MAX_OUTPUT", 1):
        withheld(request(f, app), 504)
    assert protected(f) == before


def test_wrapper_does_not_expose_a_second_host_source_through_the_existing_endpoint(f):
    adapter, target = prepared(f)
    from dataclasses import replace
    other = replace(target, source_id="0"*32)
    both = h.OperatorChecksumAdapter(service=adapter.service, sources={SOURCE:target,other.source_id:other})
    app = ui.OperatorInspectionPreview(adapter=both, source_id=SOURCE, expected_handoff_sha256=target.sha256)
    response = request(f, app, h.PATH, data={**payload(other), "source_id":other.source_id})
    assert response.status_code == 404 and response.json()["observation"] is None
    assert set(both.sources)=={SOURCE,other.source_id} and set(app.adapter.sources)=={SOURCE}


def test_cancellation_after_preview_assembly_releases_no_response(f):
    app, target = preview(f)
    original = h.validate
    calls = 0
    def cancel(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise asyncio.CancelledError
        return original(*args)
    with patch.object(h, "validate", cancel), pytest.raises(asyncio.CancelledError):
        request(f, app)


def test_session_revoked_during_bootstrap_does_not_release_csrf(f):
    app, target = preview(f)
    original = ui.OperatorInspectionPreview.session
    calls = 0
    def revoke(self, *args):
        nonlocal calls
        calls += 1
        if calls == 2:
            f.revoke("reviewer")
        return original(self, *args)
    with patch.object(ui.OperatorInspectionPreview, "session", revoke):
        response = request(f, app, ui.SESSION, method="GET")
    withheld(response, 403)
    assert f.csrf["reviewer"] not in response.text
