"""Staged HTTP admission with real disposable sessions; never a live case store."""

import asyncio
import json
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import disposition_receipt_reobservation as reobserve  # noqa: E402
import operator_checksum_handoff as h  # noqa: E402
import operator_enrollment_evidence as e  # noqa: E402
from test_disposition_journal_reconciliation import body, proposed, protected, reviewed  # noqa: E402
from test_disposition_journal_reconciliation import f as f  # noqa: E402
from test_disposition_receipt_reobservation import retained  # noqa: E402

SOURCE = "9" * 32


def record(receipt="a" * 64, binding="b" * 64, profile="c" * 32, recorded_at=2):
    return {"schema": "independent-receipt-checksum-provenance-v1", "source_id": SOURCE,
            "reference_id": "d" * 32, "receipt_sha256": receipt, "binding_sha256": binding,
            "profile_id": profile, "recorded_at": recorded_at,
            "basis": "separately_retained_operator_checksum_record", "sender_authenticated": False,
            "external_channel_verified": False}


def prepared(f, request=None):
    observer, raw = retained(f, body(f) if request is None else request)
    p = observer.service.reconciler.disposition.planner
    provenance = e.encode(record(observer.expected_receipt_sha256, observer.service.reconciler.validate(),
                                 p.authority.profile_id, f.now))
    target = h.prepare_handoff(observer.service, f.scope(), source_id=SOURCE, receipt_bytes=raw,
        expected_receipt_sha256=observer.expected_receipt_sha256, provenance_bytes=provenance,
        expected_provenance_sha256=e.sha(provenance))
    return h.OperatorChecksumAdapter(service=observer.service, sources={SOURCE: target}), target


def payload(target):
    return {"source_id": SOURCE, "expected_handoff_sha256": target.sha256,
            "independent_receipt_sha256": target.receipt_sha256}


def request(f, adapter, data, *, role="reviewer", method="POST", path=h.PATH, headers=None, raw=None):
    async def run():
        selected = [(k.decode(), v.decode()) for k, v in f.scope(role)["headers"]]
        selected.append(("content-type", "application/json"))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=adapter), base_url="http://stage.invalid") as client:
            return await client.request(method, path, content=e.encode(data) if raw is None else raw,
                                        headers=selected if headers is None else headers)
    return asyncio.run(run())


def safe(response, status):
    assert response.status_code == status and response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Cookie"
    value = response.json()
    assert all(value[k] is v for k, v in h.LIMITS.items())
    if status != 200:
        assert value["observation"] is value["observation_sha256"] is None
    else:
        observed = value["observation"]
        assert len(response.content) <= h.MAX_OUTPUT
        assert value["observation_sha256"] == e.sha(e.encode(observed))
        assert all(observed[k] is v for k, v in h.LIMITS.items())
        assert observed["checksum_comparison"] == "matches_independent_operator_entry"
    return value


@pytest.mark.parametrize("decision", [None, "accept", "reject"])
def test_assigned_independent_reviewer_reobserves_exact_receipt_without_any_history_write(f, decision):
    if decision is None:
        adapter, target = prepared(f)
    else:
        p = proposed(f)
        d = reviewed(f, p, decision)
        adapter, target = prepared(f, body(f, p, d))
    before = protected(f)
    value = safe(request(f, adapter, payload(target)), 200)
    view = value["observation"]
    assert view["handoff_sha256"] == target.sha256 and view["provenance_sha256"] == target.provenance_sha256
    assert view["prepared_actor_sha256"] != view["reviewer_actor_sha256"]
    current = view["reobservation"]["current_receipt"]
    assert current["decision"] == decision
    assert current["references"] == e.decode(target.receipt_bytes)["references"]
    assert "prepared_by" not in view and "provenance_bytes" not in view and "receipt_bytes" not in view
    assert str(f.root) not in response_text(value) and protected(f) == before


def response_text(value):
    return json.dumps(value)


@pytest.mark.parametrize("role", ["preparer", "other"])
def test_self_review_or_unassigned_reviewer_cannot_inspect_body_or_private_source(f, role):
    adapter, target = prepared(f)
    before = protected(f)
    with patch.object(h, "body", side_effect=AssertionError("SYNTHETIC private body")) as read:
        safe(request(f, adapter, payload(target), role=role), 403)
        read.assert_not_called()
    assert protected(f) == before


@pytest.mark.parametrize("kind", ["revoked", "csrf", "origin", "duplicate_cookie"])
def test_current_session_and_host_admission_precede_provenance_reads(f, kind):
    adapter, target = prepared(f)
    headers = [(k.decode(), v.decode()) for k, v in f.scope("reviewer")["headers"]]
    headers.append(("content-type", "application/json"))
    if kind == "revoked":
        f.revoke("reviewer")
    elif kind in {"csrf", "origin"}:
        key = "origin" if kind == "origin" else "x-csrf-token"
        headers = [(k, "invalid" if k == key else v) for k, v in headers]
    else:
        headers.append(("cookie", "la_session=invalid"))
    before = protected(f)
    with patch.object(h, "body", side_effect=AssertionError("SYNTHETIC private body")) as read:
        safe(request(f, adapter, payload(target), headers=headers), 403)
        read.assert_not_called()
    assert protected(f) == before


@pytest.mark.parametrize("kind", ["digest", "canonical", "duplicate", "extra", "receipt", "binding", "profile",
                                   "future", "before_receipt", "sender", "external", "basis", "bool_time", "size"])
def test_independent_provenance_schema_and_both_pins_are_closed_metadata_only(kind):
    v = record()
    raw, digest = None, None
    if kind == "canonical":
        raw = e.encode(v) + b"\n"
    elif kind == "duplicate":
        raw = e.encode(v)[:-1] + b',"schema":"independent-receipt-checksum-provenance-v1"}'
    elif kind == "size":
        raw = b"x" * 2049
    elif kind == "extra":
        v["path"] = "/SYNTHETIC-private-path"
    elif kind in {"receipt", "binding", "profile"}:
        v[{"receipt": "receipt_sha256", "binding": "binding_sha256", "profile": "profile_id"}[kind]] = "0" * (32 if kind == "profile" else 64)
    elif kind in {"future", "before_receipt", "bool_time"}:
        v["recorded_at"] = {"future": 4, "before_receipt": 0, "bool_time": True}[kind]
    elif kind == "sender":
        v["sender_authenticated"] = True
    elif kind == "external":
        v["external_channel_verified"] = True
    elif kind == "basis":
        v["basis"] = "calculated_from_incoming_receipt"
    raw = e.encode(v) if raw is None else raw
    digest = "f" * 64 if kind == "digest" else e.sha(raw)
    with pytest.raises(ValueError):
        h.provenance(raw, digest, SOURCE, "a" * 64, "b" * 64, "c" * 32, 3, 1)


def test_valid_provenance_never_claims_authenticated_sender_or_external_independence():
    value = record()
    raw = e.encode(value)
    assert h.provenance(raw, e.sha(raw), SOURCE, "a" * 64, "b" * 64, "c" * 32, 3, 1) == value
    assert value["sender_authenticated"] is value["external_channel_verified"] is False


def test_closed_http_inputs_cannot_replace_receipts_pins_context_or_reviewer(f):
    adapter, target = prepared(f)
    before = protected(f)
    cases = [(payload(target), {"method": "GET"}, 405), (payload(target), {"path": h.PATH + "?context=other"}, 400),
             (payload(target), {"path": h.PATH + "/execute"}, 404),
             ({**payload(target), "receipt_bytes": "SYNTHETIC-private"}, {}, 400),
             ({**payload(target), "expected_receipt_sha256": target.receipt_sha256}, {}, 400),
             ({**payload(target), "provenance_sha256": target.provenance_sha256}, {}, 400),
             ({**payload(target), "reviewer": "other"}, {}, 400),
             ({**payload(target), "source_id": "0" * 32}, {}, 404),
             ({**payload(target), "expected_handoff_sha256": "0" * 64}, {}, 409),
             ({**payload(target), "independent_receipt_sha256": "0" * 64}, {}, 409),
             (payload(target), {"raw": b'{"source_id":0,"source_id":1}'}, 400),
             (payload(target), {"raw": b"x" * 2049}, 413)]
    for data, options, status in cases:
        value = safe(request(f, adapter, data, **options), status)
        assert "SYNTHETIC" not in response_text(value)
    base = [(k.decode(), v.decode()) for k, v in f.scope("reviewer")["headers"]]
    for extra, status in [([("content-type", "text/plain")], 400),
                          ([("content-type", "application/json"), ("authorization", "Bearer SYNTHETIC")], 400),
                          ([("content-type", "application/json"), ("content-encoding", "gzip")], 400),
                          ([("content-type", "application/json"), ("transfer-encoding", "chunked")], 400),
                          ([("content-type", "application/json"), ("content-type", "application/json")], 400),
                          ([("content-type", "application/json"), ("content-length", "not-a-length")], 400),
                          ([("content-type", "application/json"), ("content-length", "1")], 400),
                          ([("content-type", "application/json"), ("content-length", "2049")], 413)]:
        safe(request(f, adapter, payload(target), headers=base + extra), status)
    assert protected(f) == before


@pytest.mark.parametrize("change", ["reviewer", "preparer", "window", "provenance", "exception", "timeout"])
def test_late_changes_withhold_complete_private_report_and_preserve_histories(f, change):
    adapter, target = prepared(f)
    before = protected(f)
    original = reobserve.DispositionReceiptReobserver.dispatch
    async def dispatch(self, *args, **kwargs):
        value = await original(self, *args, **kwargs)
        if change in {"reviewer", "preparer"}:
            f.revoke(change)
        elif change == "window":
            f.now += 301
        elif change == "provenance":
            object.__setattr__(target, "provenance_bytes", target.provenance_bytes + b" ")
        elif change == "exception":
            raise RuntimeError("SYNTHETIC confidential diagnostic")
        else:
            raise TimeoutError
        return value
    with patch.object(reobserve.DispositionReceiptReobserver, "dispatch", dispatch):
        value = safe(request(f, adapter, payload(target)), {"reviewer": 403, "preparer": 403, "window": 409,
            "provenance": 400, "exception": 503, "timeout": 504}[change])
    assert "SYNTHETIC" not in response_text(value) and protected(f) == before


def test_preparation_is_host_only_current_preparer_and_immutable_selection(f):
    adapter, target = prepared(f)
    before = protected(f)
    with pytest.raises(FrozenInstanceError):
        target.receipt_sha256 = "0" * 64
    with pytest.raises(TypeError):
        target.prepared_by["user_id"] = "0" * 32
    with pytest.raises(TypeError):
        adapter.sources[SOURCE] = target
    with pytest.raises(h.HTTPException):
        h.prepare_handoff(adapter.service, f.scope("reviewer"), source_id=SOURCE,
            receipt_bytes=target.receipt_bytes, expected_receipt_sha256=target.receipt_sha256,
            provenance_bytes=target.provenance_bytes, expected_provenance_sha256=target.provenance_sha256)
    altered = replace(target, provenance_sha256="0" * 64)
    rejected = h.OperatorChecksumAdapter(service=adapter.service, sources={SOURCE: altered})
    safe(request(f, rejected, payload(altered)), 400)
    assert protected(f) == before


@pytest.mark.parametrize("frames", [
    [{"type": "http.disconnect"}],
    [{"type": "http.request", "body": "invalid"}],
    [{"type": "http.request", "body": b"", "more_body": 1}],
    [{"type": "http.request", "body": b"", "more_body": True}] * 8,
    [{"type": "http.request", "body": b"x" * 2049}],
])
def test_invalid_or_unbounded_asgi_frames_fail_closed(frames):
    rows = iter(frames)
    async def receive():
        return next(rows)
    with pytest.raises(ValueError):
        asyncio.run(h.body(receive))


def test_bounded_multi_frame_body_preserves_the_exact_decoded_request():
    rows = iter([{"type": "http.request", "body": b"{", "more_body": True},
                 {"type": "http.request", "body": b"}"}])
    async def receive():
        return next(rows)
    assert asyncio.run(h.body(receive)) == ({}, 2)


def test_handoff_window_cannot_extend_underlying_planning_review(f):
    p = proposed(f)
    d = reviewed(f, p, "reject")
    f.now += 290
    adapter, target = prepared(f, body(f, p, d))
    original = reobserve.DispositionReceiptReobserver.dispatch
    async def expire(self, *args, **kwargs):
        value = await original(self, *args, **kwargs)
        assert value["reobservation"]["current_receipt"]["planning_review_current"]
        f.now += 11
        return value
    before = protected(f)
    with patch.object(reobserve.DispositionReceiptReobserver, "dispatch", expire):
        safe(request(f, adapter, payload(target)), 409)
    # A later fresh read can show the original negative decision as stale history.
    value = safe(request(f, adapter, payload(target)), 200)
    current = value["observation"]["reobservation"]["current_receipt"]
    assert current["decision"] == "reject" and not current["planning_review_current"]
    assert protected(f) == before


def test_clock_regression_after_reobservation_withholds_the_whole_handoff(f):
    adapter, target = prepared(f)
    f.now += 2
    original = reobserve.DispositionReceiptReobserver.dispatch
    async def regress(self, *args, **kwargs):
        value = await original(self, *args, **kwargs)
        f.now -= 1
        return value
    before = protected(f)
    with patch.object(reobserve.DispositionReceiptReobserver, "dispatch", regress):
        safe(request(f, adapter, payload(target)), 409)
    assert protected(f) == before


@pytest.mark.parametrize("error", [IndexError, LookupError])
def test_internal_lookup_failures_after_report_assembly_never_reach_the_response(f, error):
    adapter, target = prepared(f)
    original = h.validate
    calls = 0
    def fail_at_exit(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise error("SYNTHETIC private late diagnostic")
        return original(*args)
    before = protected(f)
    with patch.object(h, "validate", fail_at_exit):
        value = safe(request(f, adapter, payload(target)), 503)
    assert "SYNTHETIC" not in response_text(value) and protected(f) == before


def test_cancellation_and_output_budget_do_not_emit_partial_metadata(f):
    adapter, target = prepared(f)
    before = protected(f)
    with patch.object(h, "MAX_OUTPUT", 1):
        safe(request(f, adapter, payload(target)), 504)
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError
    with patch.object(reobserve.DispositionReceiptReobserver, "dispatch", cancelled), pytest.raises(asyncio.CancelledError):
        request(f, adapter, payload(target))
    assert protected(f) == before
