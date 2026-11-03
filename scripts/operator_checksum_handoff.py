"""Unregistered read-only ASGI handoff: independent operator entry, never new trust.

Trusted wiring supplies both independently retained pins. SHA-256 provenance is
unsigned metadata, not proof of its sender or the independence of an external
channel. Real disposable sessions provide current preparer/reviewer separation.
"""

import asyncio
from dataclasses import dataclass, field
from types import MappingProxyType

import disposition_receipt_reobservation as observations
import disposition_reconciliation_receipt as receipts
import operator_enrollment_evidence as e
import operator_recovery_inventory as inventory
from fastapi import HTTPException

PATH = "/api/v1/firm-admin/disposition-receipt-stage/reobserve"
MAX_BODY, MAX_PROVENANCE, MAX_OUTPUT, LIFETIME = 2048, 2048, 8192, 300
LIMITS = {**observations.LIMITS, "handoff_persisted": False,
          "provenance_sender_authenticated": False, "external_checksum_channel_verified": False}
PROVENANCE = {"schema", "source_id", "reference_id", "receipt_sha256", "binding_sha256", "profile_id",
              "recorded_at", "basis", "sender_authenticated", "external_channel_verified"}
REQUEST = {"source_id", "expected_handoff_sha256", "independent_receipt_sha256"}


def result(state="unavailable", **values):
    return {"schema": "operator-checksum-handoff-access-v1", "state": state, **LIMITS,
            "observation": None, "observation_sha256": None, **values}


def provenance(raw, expected, source_id, receipt_sha256, binding, profile, now, issued_at):
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_PROVENANCE
            or e.sha(raw) != e.token(expected)):
        e.reject()
    value = e.decode(raw)
    if (not isinstance(value, dict) or set(value) != PROVENANCE or e.encode(value) != raw
            or value["schema"] != "independent-receipt-checksum-provenance-v1"
            or value["source_id"] != e.token(source_id, 32)
            or value["receipt_sha256"] != e.token(receipt_sha256)
            or value["binding_sha256"] != binding or value["profile_id"] != profile
            or value["basis"] != "separately_retained_operator_checksum_record"
            or value["sender_authenticated"] is not False or value["external_channel_verified"] is not False
            or not issued_at <= e.stamp(value["recorded_at"]) <= e.stamp(now)):
        e.reject()
    e.token(value["reference_id"], 32)
    return value


@dataclass(frozen=True, kw_only=True)
class PreparedHandoff:
    source_id: str = field(repr=False)
    receipt_bytes: bytes = field(repr=False)
    receipt_sha256: str = field(repr=False)
    provenance_bytes: bytes = field(repr=False)
    provenance_sha256: str = field(repr=False)
    prepared_by: object = field(repr=False)
    assigned_reviewer: object = field(repr=False)
    created_at: int = field(repr=False)
    binding_sha256: str = field(repr=False)
    profile_id: str = field(repr=False)

    def __post_init__(self):
        e.token(self.source_id, 32)
        for name in ("prepared_by", "assigned_reviewer"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    def record(self):
        return {"schema": "prepared-operator-checksum-handoff-v1", **LIMITS, "source_id": self.source_id,
                "receipt_sha256": self.receipt_sha256, "provenance_sha256": self.provenance_sha256,
                "prepared_by": dict(self.prepared_by), "assigned_reviewer": dict(self.assigned_reviewer),
                "created_at": self.created_at, "expires_at": self.created_at + LIFETIME,
                "binding_sha256": self.binding_sha256, "profile_id": self.profile_id}

    @property
    def sha256(self):
        return e.sha(e.encode(self.record()))


def validate(service, source, now):
    if not isinstance(service, receipts.DispositionReceiptService) or not isinstance(source, PreparedHandoff):
        e.reject()
    binding = service.reconciler.validate()
    p = service.reconciler.disposition.planner
    if (source.binding_sha256 != binding or source.profile_id != p.authority.profile_id
            or not e.stamp(source.created_at) <= e.stamp(now) <= source.created_at + LIFETIME):
        raise FileExistsError
    if (source.prepared_by["user_id"] != p.preparer or source.assigned_reviewer["user_id"] != p.reviewer
            or p.preparer == p.reviewer):
        raise PermissionError
    p.authority.recheck(dict(source.prepared_by), now=now)
    if p.authority.eligible(p.reviewer, "reviewer") != dict(source.assigned_reviewer):
        raise PermissionError
    old = observations.retained(source.receipt_bytes, source.receipt_sha256, binding, now)
    provenance(source.provenance_bytes, source.provenance_sha256, source.source_id, source.receipt_sha256,
               binding, source.profile_id, now, old["issued_at"])
    return p


def prepare_handoff(service, scope, *, source_id, receipt_bytes, expected_receipt_sha256,
                    provenance_bytes, expected_provenance_sha256):
    """Trusted host factory only; never an HTTP route or a provenance generator."""
    if not isinstance(service, receipts.DispositionReceiptService):
        e.reject()
    binding = service.reconciler.validate()
    p = service.reconciler.disposition.planner
    actor = p.actor(scope, "preparer")
    source = PreparedHandoff(source_id=source_id, receipt_bytes=receipt_bytes,
        receipt_sha256=expected_receipt_sha256, provenance_bytes=provenance_bytes,
        provenance_sha256=expected_provenance_sha256, prepared_by=actor,
        assigned_reviewer=p.authority.eligible(p.reviewer, "reviewer"), created_at=e.stamp(p.clock()),
        binding_sha256=binding, profile_id=p.authority.profile_id)
    validate(service, source, p.clock())
    if p.actor(scope, "preparer") != actor:
        raise PermissionError
    return source


class BodyTooLarge(ValueError):
    pass


class NoRoute(Exception):
    pass


async def body(receive):
    raw = b""
    async with asyncio.timeout(inventory.READ_SECONDS):
        for _ in range(8):
            frame = await receive()
            if (frame.get("type") != "http.request" or not isinstance(frame.get("body", b""), bytes)
                    or type(frame.get("more_body", False)) is not bool):
                e.reject()
            raw += frame.get("body", b"")
            if len(raw) > MAX_BODY:
                raise BodyTooLarge
            if not frame.get("more_body", False):
                return e.decode(raw), len(raw)
    e.reject()


@dataclass(frozen=True, kw_only=True)
class OperatorChecksumAdapter:
    service: receipts.DispositionReceiptService = field(repr=False)
    sources: object = field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.service, receipts.DispositionReceiptService) or not isinstance(self.sources, dict)
                or not 1 <= len(self.sources) <= inventory.MAX_ITEMS):
            e.reject()
        for ident, source in self.sources.items():
            if not isinstance(source, PreparedHandoff) or e.token(ident, 32) != source.source_id:
                e.reject()
        object.__setattr__(self, "sources", MappingProxyType(dict(self.sources)))

    async def __call__(self, scope, receive, send):
        status, value = 404, result()
        try:
            if scope.get("type") != "http" or scope.get("path") != PATH:
                raise NoRoute
            if scope.get("method") != "POST":
                status = 405
                raise NoRoute
            headers = scope.get("headers", [])
            if (scope.get("query_string", b"") or len(headers) > 64
                    or sum(len(k) + len(v) for k, v in headers) > 16384
                    or any(k.lower() in {b"authorization", b"content-encoding", b"transfer-encoding"} for k, _ in headers)
                    or sum(k.lower() == b"content-type" for k, _ in headers) != 1
                    or next(v for k, v in headers if k.lower() == b"content-type") != b"application/json"):
                e.reject()
            lengths = [v for k, v in headers if k.lower() == b"content-length"]
            if len(lengths) > 1 or lengths and not lengths[0].isdigit():
                e.reject()
            length = int(lengths[0]) if lengths else None
            if length is not None and length > MAX_BODY:
                raise BodyTooLarge
            async with asyncio.timeout(inventory.TOTAL_SECONDS):
                p = self.service.reconciler.disposition.planner
                actor = p.actor({**scope, "state": {}}, "reviewer")  # Admission precedes body/private-source inspection.
                request, size = await body(receive)
                if length is not None and length != size:
                    e.reject()
                if not isinstance(request, dict) or set(request) != REQUEST:
                    e.reject()
                source = self.sources.get(e.token(request["source_id"], 32))
                if source is None:
                    raise NoRoute
                p = validate(self.service, source, p.clock())
                expected = source.sha256
                if (e.token(request["expected_handoff_sha256"]) != expected
                        or e.token(request["independent_receipt_sha256"]) != source.receipt_sha256):
                    raise FileExistsError
                observed = await observations.DispositionReceiptReobserver(service=self.service,
                    expected_receipt_sha256=source.receipt_sha256).dispatch(scope, "reobserve",
                                                                        receipt_bytes=source.receipt_bytes)
                if observed["state"] != "receipt_reobserved":
                    status = {"denied": 403, "budget_exhausted": 504, "unavailable": 503}.get(observed["state"], 409)
                    value = result(observed["state"])
                else:
                    report = {"schema": "operator-checksum-handoff-observation-v1", **LIMITS,
                              "source_id": source.source_id, "handoff_sha256": expected,
                              "provenance_sha256": source.provenance_sha256,
                              "prepared_actor_sha256": e.sha(e.encode(dict(source.prepared_by))),
                              "reviewer_actor_sha256": e.sha(e.encode(actor)),
                              "checksum_comparison": "matches_independent_operator_entry",
                              "provenance_basis": "exact_separately_pinned_unsigned_record",
                              "reobservation": observed["reobservation"],
                              "reobservation_sha256": observed["reobservation_sha256"]}
                    value = result("staged_handoff_reobserved", observation=report,
                                   observation_sha256=e.sha(e.encode(report)))
                    if len(e.encode(value)) > MAX_OUTPUT:
                        raise TimeoutError
                    status = 200
                # No metadata survives expired/replaced provenance or either actor's revocation.
                validate(self.service, source, p.clock())
                if source.sha256 != expected:
                    raise FileExistsError
                if observed["state"] == "receipt_reobserved":
                    current = observed["reobservation"]["current_receipt"]
                    if e.stamp(p.clock()) < current["issued_at"]:
                        raise FileExistsError
                    if current["planning_review_current"]:
                        d, refs = self.service.reconciler.disposition, current["references"]
                        plan = d.plan(refs)
                        p.current_actors(plan)
                        p.current_window(plan)
                        p.authority.recheck(d.review(plan, refs)["reviewed_by"], now=p.clock())
                p.authority.recheck(actor, now=p.clock())
                if p.actor({**scope, "state": {}}, "reviewer") != actor:
                    raise PermissionError
        except (PermissionError, HTTPException):
            status, value = 403, result("denied")
        except BodyTooLarge:
            status, value = 413, result("unverifiable")
        except TimeoutError:
            status, value = 504, result("budget_exhausted")
        except FileExistsError:
            status, value = 409, result("snapshot_or_publication_conflict")
        except (ValueError, TypeError, KeyError, RecursionError):
            status, value = 400, result("unverifiable")
        except NoRoute:
            status, value = (405 if status == 405 else 404), result()
        except Exception:  # noqa: BLE001 - never release private diagnostics or partial observations.
            status, value = 503, result()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                                (b"vary", b"Cookie"), (b"x-content-type-options", b"nosniff")]})
        await send({"type": "http.response.body", "body": e.encode(value)})
