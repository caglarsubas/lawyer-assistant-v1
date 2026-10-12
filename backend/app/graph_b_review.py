"""Private independently signed Graph B review; no signing keys or graph writes."""
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, StrictInt, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from . import decision_equivalence as eq
from . import source_reviews as reviews
from .config import ROOT
from .db import User, now, uid
from .firm_rbac import permissions_for
from .graph_b_qualification import Qualifications, ReviewerAppointment, day, validate_qualifications
from .graph_b_review_models import GraphBReviewEvent, GraphBReviewHead
from .graph_release import _load_serving
from .release_preparation import canonical, digest

VERSION = "signed-graph-b-review-v1"
MAX_EVENTS = 50
MAX_LEDGER_BYTES = 8 * 1024 * 1024
MAX_CREDENTIAL_BYTES = 256 * 1024


class SignedBody(reviews.StrictInput):
    schema_version: Literal["signed-graph-b-review-v1"]
    context_id: eq.SOURCE_ID
    firm_id: str = Field(min_length=1, max_length=64)
    operator_id: str = Field(min_length=1, max_length=64)
    reviewer_id: str = Field(min_length=1, max_length=64)
    public_reviewer: str = Field(min_length=3, max_length=160)
    expected_review_revision: StrictInt = Field(ge=0, le=MAX_EVENTS)
    equivalence_revision: StrictInt = Field(ge=1, le=eq.MAX_EVENTS)
    pins: eq.Pins
    source_snapshot_sha256: eq.SOURCE_ID
    ontology_sha256: eq.SOURCE_ID
    review_key_sha256: eq.SOURCE_ID
    reviewed_at: str = Field(min_length=20, max_length=80)
    decision: Literal["approve", "reject", "needs_changes"]
    qualifications: Qualifications
    appointment: ReviewerAppointment

    @field_validator("reviewed_at")
    @classmethod
    def review_timestamp(cls, value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Review timestamp requires timezone")
        return value


class ReviewRequest(reviews.StrictInput):
    expected_review_revision: StrictInt = Field(ge=0, le=MAX_EVENTS)
    expected_equivalence_revision: StrictInt = Field(ge=1, le=eq.MAX_EVENTS)
    pins: eq.Pins
    reviewer_id: str = Field(min_length=1, max_length=64)
    public_reviewer: str = Field(min_length=3, max_length=160)
    reviewed_at: str = Field(min_length=20, max_length=80)
    qualifications: Qualifications
    appointment: ReviewerAppointment
    credential_data: str = Field(min_length=4, max_length=350_000)

    @field_validator("reviewed_at")
    @classmethod
    def review_timestamp(cls, value):
        return SignedBody.review_timestamp(value)


class SignedEnvelope(reviews.StrictInput):
    algorithm: Literal["Ed25519"]
    body: SignedBody
    signature: str = Field(min_length=88, max_length=88)


class Acceptance(reviews.StrictInput):
    envelope: SignedEnvelope
    credential_data: str = Field(min_length=4, max_length=350_000)


def invalid():
    return HTTPException(409, "The signed review, complete evidence or current qualifications could not be verified")


def credential(data, expected):
    try:
        raw = base64.b64decode(data, validate=True)
        if not 1 <= len(raw) <= MAX_CREDENTIAL_BYTES or digest(raw) != expected:
            raise invalid()
        return raw
    except (ValueError, TypeError):
        raise invalid() from None


def public_key(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= 16384:
        raise invalid()
    try:
        key = serialization.load_pem_public_key(raw)
        if not isinstance(key, Ed25519PublicKey):
            raise invalid()
        return key, digest(key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    except ValueError:
        raise invalid() from None


def configured_key(request):
    value = request.app.state.settings.graph_b_review_trusted_key
    if not value:
        raise HTTPException(503, "Configure the independently vetted Graph B reviewer public key first")
    from .release_authorization import _packet_tools
    try:
        raw = _packet_tools().read_file(Path(value), 16384)
        key, fingerprint = public_key(raw)
        return raw, key, fingerprint
    except (ValueError, OSError):
        raise HTTPException(503, "The configured independent review public key could not be read safely") from None


def verify_signature(envelope, key_raw):
    envelope = SignedEnvelope.model_validate(envelope)
    key, fingerprint = public_key(key_raw)
    try:
        signature = base64.b64decode(envelope.signature, validate=True)
        if len(signature) != 64 or envelope.body.review_key_sha256 != fingerprint:
            raise invalid()
        key.verify(signature, canonical(envelope.body.model_dump()))
    except (InvalidSignature, ValueError, TypeError):
        raise invalid() from None
    return envelope.body.model_dump()


def head(session, firm, context):
    return session.scalar(select(GraphBReviewHead).where(GraphBReviewHead.firm_id == firm,
        GraphBReviewHead.context_id == context).execution_options(populate_existing=True))


def authorized_member(session, ident, firm):
    actor = session.scalar(select(User).where(User.id == ident).execution_options(populate_existing=True))
    if (actor is None or actor.firm_id != firm or not actor.active or actor.role not in {"admin", "curator"}
            or "source.curate" not in permissions_for(session, actor)):
        raise invalid()
    return actor


def assessed(packages, captured, decisions, eq_events, revision, pins):
    if not 1 <= revision <= len(eq_events):
        raise invalid()
    prior = eq_events[:revision]
    event = prior[-1]
    if (event["decision"] != "accepted" or event["proposal"]["pins"] != pins
            or event["proposal"]["claims"]["relation"] != "same_decision"):
        raise invalid()
    bound = eq.snapshot(packages, captured, decisions, pins)
    if not all(value["export_allowed"] for value in bound["sources"].values()):
        raise invalid()
    return bound, prior


def validate_body(body, packages, captured, decisions, eq_events, context):
    body = SignedBody.model_validate(body).model_dump()
    if body["context_id"] != context:
        raise invalid()
    bound, prior = assessed(packages, captured, decisions, eq_events, body["equivalence_revision"], body["pins"])
    snapshot = {"sources": bound, "equivalence_history": prior}
    if body["source_snapshot_sha256"] != digest(canonical(snapshot)):
        raise invalid()
    contributors = set(bound["contributors"]) | {event["actor"]["id"] for event in prior} | {body["operator_id"]}
    if body["reviewer_id"] in contributors:
        raise HTTPException(403, "The signed reviewer must be separate from all source, identity and equivalence contributors")
    timestamp = datetime.fromisoformat(body["reviewed_at"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
        raise invalid()
    events = [*prior, *(event for source in bound["sources"].values() for event in source["source_history"] + source["mapping_history"]),
              *(event for identity in bound["identities"].values() for event in identity)]
    if any(datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")) > timestamp for event in events):
        raise invalid()
    appointment = ReviewerAppointment.model_validate(body["appointment"])
    review_day = timestamp.astimezone(timezone.utc).date()
    if not day(appointment.valid_from) <= review_day < day(appointment.valid_until):
        raise invalid()
    if body["public_reviewer"] != body["public_reviewer"].strip() or any(ord(c) < 32 for c in body["public_reviewer"]):
        raise invalid()
    register = next(key for key in packages if key not in decisions)
    validate_qualifications(body["qualifications"], packages, bound, decisions, register, prior[-1]["proposal"]["claims"], body["reviewed_at"])
    return body


def ledger(store, session, row, packages, captured, decisions, eq_events, context):
    if row is None:
        return []
    rows = list(session.scalars(select(GraphBReviewEvent).where(GraphBReviewEvent.head_id == row.id,
        GraphBReviewEvent.firm_id == row.firm_id).order_by(GraphBReviewEvent.revision).limit(MAX_EVENTS + 1)))
    if (type(row.revision) is not int or not 1 <= row.revision <= MAX_EVENTS
            or [r.revision for r in rows] != list(range(1, row.revision + 1))
            or sum(len(r.payload) for r in rows) > MAX_LEDGER_BYTES):
        raise invalid()
    result = []
    try:
        for r in rows:
            data = reviews._decode(store, r)
            event = data["event"]
            if (set(data) != {"context", "event"} or data["context"] != {"firm_id": row.firm_id,
                    "context_id": context, "head_id": row.id, "event_id": r.id, "revision": r.revision}
                    or set(event) != {"id", "revision", "created_at", "actor", "envelope", "credential_data", "accepted_key"}
                    or event["id"] != r.id or event["revision"] != r.revision or event["created_at"] != r.created_at
                    or not reviews._valid_reviewer(event["actor"])):
                raise invalid()
            body = verify_signature(event["envelope"], event["accepted_key"].encode("ascii"))
            validate_body(body, packages, captured, decisions, eq_events, context)
            credential(event["credential_data"], body["appointment"]["evidence_sha256"])
            if (body["firm_id"] != row.firm_id or body["expected_review_revision"] != r.revision - 1
                    or body["reviewer_id"] != event["actor"]["id"]
                    or datetime.fromisoformat(body["reviewed_at"].replace("Z", "+00:00")) > datetime.fromisoformat(event["created_at"])):
                raise invalid()
            if result and datetime.fromisoformat(body["reviewed_at"].replace("Z", "+00:00")) < datetime.fromisoformat(result[-1]["created_at"]):
                raise invalid()
            result.append(event)
        if reviews._decode(store, row) != {"context": {"firm_id": row.firm_id, "context_id": context,
                "head_id": row.id, "revision": row.revision}, "event": result[-1]}:
            raise invalid()
    except (KeyError, TypeError, ValueError, ValidationError):
        raise invalid() from None
    return result


def current_check(body, session, packages, captured, decisions, eq_events, context, key_fingerprint, ontology_sha):
    validate_body(body, packages, captured, decisions, eq_events, context)
    if (body["review_key_sha256"] != key_fingerprint or body["ontology_sha256"] != ontology_sha
            or body["equivalence_revision"] != len(eq_events) or body["pins"] != eq.current_pins(captured)):
        raise invalid()
    authorized_member(session, body["reviewer_id"], body["firm_id"])
    authorized_member(session, body["operator_id"], body["firm_id"])
    if any(value["state"]["assigned_to"] is None or value["state"]["assigned_to"]["id"] != body["operator_id"]
           for value in captured["sources"].values()):
        raise invalid()
    if day(body["appointment"]["valid_until"]) <= datetime.now(timezone.utc).date():
        raise invalid()


def view(events, session, packages, captured, decisions, eq_events, context, user, key_fingerprint, ontology_sha):
    latest = events[-1] if events else None
    stale = False
    if latest:
        try:
            current_check(latest["envelope"]["body"], session, packages, captured, decisions, eq_events, context, key_fingerprint, ontology_sha)
        except HTTPException:
            stale = True
    # Credential bytes and historical key PEMs stay encrypted in the server ledger.
    safe = [{k: v for k, v in event.items() if k not in {"credential_data", "accepted_key"}} for event in reversed(events)]
    return {"schema_version": VERSION, "confidentiality": "firm_confidential", "firm_id": user.firm_id,
            "context_id": context, "revision": len(events), "history": safe, "history_complete": True,
            "current": safe[0] if safe else None, "stale": stale, "trust_configured": bool(key_fingerprint),
            "signed_review_current": bool(latest and not stale and latest["envelope"]["body"]["decision"] == "approve"),
            "graph_updated": False, "publication_eligible": False, "legal_truth_verified": False,
            "institutional_competence_verified": False, "finality_verified": False}


def context_data(request, source, peer, register, user, session, *, lock=False):
    packages, decisions, context = eq.context(request, source, peer, register, user)
    store = request.app.state.store
    captured = eq.capture(store, session, packages, decisions, user.firm_id, lock=lock)
    eq_events = eq.ledger(store, session, eq._head(session, user.firm_id, context), packages, decisions, captured)
    events = ledger(store, session, head(session, user.firm_id, context), packages, captured, decisions, eq_events, context)
    return packages, decisions, context, captured, eq_events, events


def graph_b_review_router():
    router = APIRouter(prefix="/api/v1/public-sources", tags=["graph-b-review"])
    def authorize(request: Request):
        return reviews._authorize(request)

    @router.get("/{source_id}/graph-b-review")
    def get(source_id: str, request: Request, peer_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
            register_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        store = request.app.state.store
        with store.session() as session:
            data = context_data(request, source_id, peer_source_id, register_source_id, user, session)
            packages, decisions, context, captured, eq_events, events = data
            key = configured_key(request)[2] if request.app.state.settings.graph_b_review_trusted_key else None
            ontology_sha = _load_serving()._release.ontology_digest(ROOT / "ontology")
            result = view(events, session, packages, captured, decisions, eq_events, context, user, key, ontology_sha)
        with store.session() as session:
            if context_data(request, source_id, peer_source_id, register_source_id, user, session) != data:
                raise invalid()
            if events:
                # Roles and appointments can change without changing source pins.
                refreshed = view(events, session, packages, captured, decisions, eq_events, context, user, key, ontology_sha)
                if refreshed != result:
                    raise invalid()
        eq.verify(request, packages, user)
        if ((configured_key(request)[2] if request.app.state.settings.graph_b_review_trusted_key else None) != key
                or _load_serving()._release.ontology_digest(ROOT / "ontology") != ontology_sha):
            raise invalid()
        return result

    @router.post("/{source_id}/graph-b-review/request")
    def signing_request(source_id: str, body: ReviewRequest, request: Request, peer_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
                        register_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        store = request.app.state.store
        with store.session() as session:
            current = reviews._lock_identity(session, request, user)
            role = current.role
            data = context_data(request, source_id, peer_source_id, register_source_id, current, session, lock=True)
            packages, decisions, context, captured, eq_events, events = data
            key_raw, _, key_sha = configured_key(request)
            ontology_sha = _load_serving()._release.ontology_digest(ROOT / "ontology")
            if (len(events) != body.expected_review_revision or len(events) >= MAX_EVENTS
                    or len(eq_events) != body.expected_equivalence_revision or eq.current_pins(captured) != body.pins.model_dump()):
                raise invalid()
            bound, prior = assessed(packages, captured, decisions, eq_events, len(eq_events), body.pins.model_dump())
            credential(body.credential_data, body.appointment.evidence_sha256)
            signed_body = SignedBody.model_validate({"schema_version": VERSION, "context_id": context, "firm_id": current.firm_id,
                "operator_id": current.id, "reviewer_id": body.reviewer_id, "public_reviewer": body.public_reviewer,
                "expected_review_revision": len(events), "equivalence_revision": len(eq_events), "pins": body.pins.model_dump(),
                "source_snapshot_sha256": digest(canonical({"sources": bound, "equivalence_history": prior})),
                "ontology_sha256": ontology_sha, "review_key_sha256": key_sha, "reviewed_at": body.reviewed_at,
                "decision": "approve", "qualifications": body.qualifications.model_dump(), "appointment": body.appointment.model_dump()}).model_dump()
            current_check(signed_body, session, packages, captured, decisions, eq_events, context, key_sha, ontology_sha)
            if events and datetime.fromisoformat(signed_body["reviewed_at"].replace("Z", "+00:00")) < datetime.fromisoformat(events[-1]["created_at"]):
                raise invalid()
            raw = canonical(signed_body)
            if (context_data(request, source_id, peer_source_id, register_source_id, current, session, lock=True) != data
                    or configured_key(request)[0] != key_raw or _load_serving()._release.ontology_digest(ROOT / "ontology") != ontology_sha
                    or reviews._lock_identity(session, request, current).role != role):
                raise invalid()
            eq.verify(request, packages, current)
            current_check(signed_body, session, packages, captured, decisions, eq_events, context, key_sha, ontology_sha)
            return {"body_json": raw.decode(), "body_sha256": digest(raw), "signed": False, "needs_external_signature": True,
                    "confidentiality": "firm_confidential", "publication_eligible": False}

    @router.post("/{source_id}/graph-b-review/accept")
    def accept(source_id: str, body: Acceptance, request: Request, peer_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
               register_source_id: str = Query(pattern=r"^[a-f0-9]{64}$"), user=Depends(authorize)):
        store = request.app.state.store
        try:
            with store.session() as session:
                current = reviews._lock_identity(session, request, user)
                role = current.role
                data = context_data(request, source_id, peer_source_id, register_source_id, current, session, lock=True)
                packages, decisions, context, captured, eq_events, events = data
                key_raw, _, key_sha = configured_key(request)
                signed_body = verify_signature(body.envelope.model_dump(), key_raw)
                ontology_sha = _load_serving()._release.ontology_digest(ROOT / "ontology")
                current_check(signed_body, session, packages, captured, decisions, eq_events, context, key_sha, ontology_sha)
                credential(body.credential_data, signed_body["appointment"]["evidence_sha256"])
                if (signed_body["firm_id"] != current.firm_id or signed_body["reviewer_id"] != current.id
                        or signed_body["expected_review_revision"] != len(events) or len(events) >= MAX_EVENTS):
                    raise invalid()
                if events and datetime.fromisoformat(signed_body["reviewed_at"].replace("Z", "+00:00")) < datetime.fromisoformat(events[-1]["created_at"]):
                    raise invalid()
                row = head(session, current.firm_id, context)
                revision, row_id = len(events) + 1, row.id if row else uid()
                event = {"id": uid(), "revision": revision, "created_at": now(), "actor": {"id": current.id, "name": current.name},
                         "envelope": body.envelope.model_dump(), "credential_data": body.credential_data, "accepted_key": key_raw.decode("ascii")}
                ctx = {"firm_id": current.firm_id, "context_id": context, "head_id": row_id, "revision": revision}
                payload = store.encode({"context": ctx, "event": event})
                if row is None:
                    session.add(GraphBReviewHead(id=row_id, firm_id=current.firm_id, context_id=context, revision=revision, payload=payload))
                else:
                    changed = session.execute(update(GraphBReviewHead).where(GraphBReviewHead.id == row.id,
                        GraphBReviewHead.firm_id == current.firm_id,
                        GraphBReviewHead.revision == len(events)).values(revision=revision, payload=payload).execution_options(synchronize_session=False))
                    if changed.rowcount != 1:
                        raise invalid()
                session.add(GraphBReviewEvent(id=event["id"], firm_id=current.firm_id, head_id=row_id, revision=revision,
                    created_at=event["created_at"], payload=store.encode({"context": {**ctx, "event_id": event["id"]}, "event": event})))
                if (context_data(request, source_id, peer_source_id, register_source_id, current, session, lock=True)[:5] != data[:5]
                        or configured_key(request)[0] != key_raw or _load_serving()._release.ontology_digest(ROOT / "ontology") != ontology_sha
                        or reviews._lock_identity(session, request, current).role != role):
                    raise invalid()
                eq.verify(request, packages, current)
                current_check(signed_body, session, packages, captured, decisions, eq_events, context, key_sha, ontology_sha)
                session.flush()
                if ledger(store, session, head(session, current.firm_id, context), packages, captured, decisions, eq_events, context) != [*events, event]:
                    raise invalid()
                if configured_key(request)[0] != key_raw or _load_serving()._release.ontology_digest(ROOT / "ontology") != ontology_sha:
                    raise invalid()
                session.commit()
                return view([*events, event], session, packages, captured, decisions, eq_events, context, current, key_sha, ontology_sha)
        except (IntegrityError, OperationalError):
            raise invalid() from None
    return router
