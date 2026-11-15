"""Reopen the staged source bound to each new curator review before commit."""

from contextlib import asynccontextmanager

from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from sqlalchemy import event

from .decision_mapping_models import DecisionMappingEvent
from .provision_mapping_models import ProvisionMappingEvent
from .public_sources import SHA256, PublicSourceError, PublicSourceStore
from .source_review_models import SourceRelationshipEvent, SourceReviewEvent
from .source_reviews import _binding

GUARDED_EVENTS = (SourceReviewEvent, ProvisionMappingEvent, DecisionMappingEvent, SourceRelationshipEvent)
PENDING_SOURCES = "curator_review_source_bindings"


def _source_conflict():
    return HTTPException(
        status_code=409,
        detail="İncelemeye bağlı kaynak paketi doğrulanamadı; güncel kaydı açın",
        headers={"Cache-Control": "no-store"},
    )


def _event_bindings(store, row):
    paired = isinstance(row, SourceRelationshipEvent)
    key = "bindings" if paired else "source_binding"
    try:
        payload = store.decode(row)
        if not isinstance(payload, dict) or set(payload) != {"context", "event", key}:
            raise ValueError
        bindings = payload[key] if paired else [payload[key]]
        if not isinstance(bindings, list) or len(bindings) != (2 if paired else 1):
            raise ValueError
        for binding in bindings:
            if (not isinstance(binding, dict) or set(binding) != {"source_id", "artifacts"}
                    or not isinstance(binding["source_id"], str) or not SHA256.fullmatch(binding["source_id"])
                    or not isinstance(binding["artifacts"], dict)):
                raise ValueError
        if paired and bindings[0]["source_id"] == bindings[1]["source_id"]:
            raise ValueError
        return bindings
    except (InvalidToken, ValueError, TypeError):
        raise _source_conflict() from None


def install_curator_review_source_guard(app):
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with previous_lifespan(app) as state:
            store = app.state.store

            def collect(session, *_):
                # The final identity and ledger queries can autoflush an event
                # before commit. Keep its exact binding until this transaction ends.
                for row in session.new:
                    if isinstance(row, GUARDED_EVENTS):
                        session.info.setdefault(PENDING_SOURCES, []).extend(_event_bindings(store, row))

            def verify(session):
                if any(isinstance(row, GUARDED_EVENTS) for row in session.new):
                    session.flush()
                bindings = session.info.get(PENDING_SOURCES)
                if not bindings:
                    return
                try:
                    sources = PublicSourceStore(app.state.settings.public_source_dir)
                    verified = {}
                    for binding in bindings:
                        source_id = binding["source_id"]
                        if source_id not in verified:
                            verified[source_id] = _binding(sources.verified_package(source_id))
                        if verified[source_id] != binding:
                            raise _source_conflict()
                except (PublicSourceError, OSError):
                    raise _source_conflict() from None

            def clear(session, transaction):
                if transaction.parent is None:
                    session.info.pop(PENDING_SOURCES, None)

            listeners = (("before_flush", collect), ("before_commit", verify), ("after_transaction_end", clear))
            for name, handler in listeners:
                event.listen(store.session, name, handler)
            try:
                yield state
            finally:
                for name, handler in listeners:
                    event.remove(store.session, name, handler)

    app.router.lifespan_context = lifespan
