"""No-write, revision-bound snapshots for trusted local review preparation.

An operator ID is a local administrative identity, never remote authentication.
Snapshots and their MACs confer neither legal review nor publication authority.
"""

import base64
import hashlib
import hmac
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from . import provision_mappings as mappings
from . import source_reviews as reviews
from .db import User
from .provision_mapping_models import ProvisionMappingHead
from .public_sources import PublicSourceError
from .source_review_models import SourceReviewHead

REQUIRED_USES = frozenset({"storage", "local_processing", "internal_display", "export", "indexing", "local_inference"})
MAC_DOMAIN = b"lawyer-assistant:review-preparation:mac-key:v1\0"
PAYLOAD_DOMAIN = b"lawyer-assistant:review-preparation:manifest:v1\0"


class SnapshotError(ValueError):
    """Safe local-operator error, with no credentials, paths or private text."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _copy(value):
    return json.loads(_canonical(value))


class _ReadOnlySession(Session):
    pass


@event.listens_for(_ReadOnlySession, "before_flush")
def _deny_flush(session, flush_context, instances):
    if session.new or session.dirty or session.deleted:
        raise SnapshotError("Review preparation cannot write database records")


def _read_statements_only(connection, cursor, statement, parameters, context, executemany):
    # PostgreSQL row locks require a normal transaction; SET TRANSACTION READ ONLY
    # rejects SELECT FOR UPDATE. Only our controlled SELECT/SHOW SQL is permitted.
    # This is an internal store interface, not a facility for untrusted SQL.
    if not re.match(r"\s*(?:SELECT|SHOW)\b", statement, re.IGNORECASE):
        raise SnapshotError("Review preparation permits read queries only")


class _Reader:
    def __init__(self, engine, key):
        self.engine = engine
        self.session = sessionmaker(engine, class_=_ReadOnlySession, expire_on_commit=False, autoflush=False)
        self._cipher = Fernet(key)
        self._mac_key = hmac.digest(base64.urlsafe_b64decode(key), MAC_DOMAIN, "sha256")

    def decode(self, row):
        return json.loads(self._cipher.decrypt(row.payload.encode("utf-8")))

    def preparation_mac(self, payload: bytes) -> str:
        if not isinstance(payload, bytes):
            raise SnapshotError("Preparation integrity payload must be bytes")
        return hmac.new(self._mac_key, PAYLOAD_DOMAIN + payload, hashlib.sha256).hexdigest()


@contextmanager
def readonly_store(settings):
    """Open existing storage only; never initialize a schema, user or key file."""
    engine = None
    try:
        database_url = settings.database_url
        if database_url == "sqlite:///./.data/workspace.db":
            database_url = f"sqlite:///{settings.data_dir / 'workspace.db'}"
        url = make_url(database_url)
        backend = url.get_backend_name()
        if backend == "sqlite":
            path = Path(url.database or "")
            if (not settings.demo_mode or not url.database or not path.is_file() or path.is_symlink()
                    or url.query):
                raise SnapshotError("An existing explicit demo database is required for SQLite")
            # mode=ro prevents creating a replacement database if the checked file
            # disappears before connection; it also enforces SQLite's write ban.
            uri = "file:" + quote(str(path.absolute()), safe="/") + "?mode=ro"
            engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(
                uri, uri=True, check_same_thread=False), pool_pre_ping=True)
        elif backend == "postgresql":
            engine = create_engine(database_url, pool_pre_ping=True, connect_args={
                "connect_timeout": 5,
                "options": "-c lock_timeout=5000 -c statement_timeout=15000",
            })
        else:
            raise SnapshotError("Production review preparation requires PostgreSQL")
        key = settings.encryption_key
        if not key and settings.demo_mode:
            key_path = settings.data_dir / "demo-encryption.key"
            if not key_path.is_file() or key_path.is_symlink() or key_path.stat().st_size > 1024:
                raise SnapshotError("An existing demo encryption key is required")
            key = key_path.read_text(encoding="ascii").strip()
        if not key:
            raise SnapshotError("An existing encryption key is required")
        try:
            reader = _Reader(engine, key.encode("ascii"))
        except (ValueError, UnicodeError, TypeError):
            raise SnapshotError("The configured encryption key is invalid") from None
        event.listen(engine, "before_cursor_execute", _read_statements_only)
        yield reader
    except (OSError, SQLAlchemyError):
        raise SnapshotError("Existing review storage could not be opened safely") from None
    finally:
        if engine is not None:
            engine.dispose()


def _operator(session, operator_id, *, shared=False):
    operator = session.scalar(select(User).where(User.id == operator_id).with_for_update(read=shared)
                              .execution_options(populate_existing=True))
    if operator is None or not operator.active or operator.role not in {"admin", "curator"}:
        raise SnapshotError("An existing active administrator or curator operator is required")
    return operator


def _package(source_store, source_id):
    try:
        return source_store.verified_package(source_id)
    except (PublicSourceError, OSError):
        raise SnapshotError("The source package is unavailable or failed integrity validation") from None


def _load(store, session, package, operator, expected_source_revision, expected_mapping_revision, *, shared=False):
    source_head = session.scalar(select(SourceReviewHead).where(
        SourceReviewHead.firm_id == operator.firm_id, SourceReviewHead.source_id == package.detail["id"])
        .with_for_update(read=shared).execution_options(populate_existing=True))
    if source_head is None or source_head.revision != expected_source_revision:
        raise SnapshotError("The source review revision changed or is unavailable")
    source_review = reviews._projection(store, source_head, package)
    reviews._history(store, session, source_head)
    if source_review["assigned_to"] is None or source_review["assigned_to"]["id"] != operator.id:
        raise SnapshotError("The operator must own the current source review")
    assessments = source_review["assessments"]
    if set(assessments) != set(reviews.CATEGORIES) or any(item["decision"] != "accepted" for item in assessments.values()):
        raise SnapshotError("All four current source assessments must be accepted")
    if not REQUIRED_USES.issubset(assessments["rights"]["permitted_uses"]):
        raise SnapshotError("Source rights do not cover the required preparation and corpus uses")
    mapping_head = session.scalar(select(ProvisionMappingHead).where(
        ProvisionMappingHead.firm_id == operator.firm_id, ProvisionMappingHead.source_id == package.detail["id"])
        .with_for_update(read=shared).execution_options(populate_existing=True))
    if mapping_head is None or mapping_head.revision != expected_mapping_revision:
        raise SnapshotError("The mapping revision changed or is unavailable")
    projection, history = mappings._projection(store, session, mapping_head, package)
    summary = {"revision": source_head.revision, "assigned_to": source_review["assigned_to"], "ready": True}
    state = mappings._state(package, mapping_head.revision, summary, projection, history)
    if not state["handoff_ready"] or not state["items"] or any(
            not item["non_whitespace_covered"] or item["resolution"] is None for item in state["items"]):
        raise SnapshotError("Every mapping must be accepted, current and fully grounded")
    binding = {
        "schema_version": "legal-review-snapshot-v1", "source_id": package.detail["id"],
        "source_version_id": package.metadata.source_version_id, "source_artifacts": package.detail["artifacts"],
        "firm_id": operator.firm_id, "operator_id": operator.id,
        "source_review_head_id": source_head.id, "mapping_head_id": mapping_head.id,
        "source_review_revision": source_head.revision, "mapping_revision": mapping_head.revision,
        "projections_sha256": hashlib.sha256(_canonical({"source_review": source_review,
                                                         "provision_mappings": projection})).hexdigest(),
    }
    return {"package": package, "state": _copy(state), "source_review": _copy(source_review), "binding": _copy(binding)}


@contextmanager
def locked_snapshot(store, source_store, *, operator_id, source_id,
                    expected_source_review_revision, expected_mapping_revision, shared=False):
    """Hold a validated local snapshot stable through a caller's bounded atomic output.

The caller must discard its newly written output if context exit raises. On
PostgreSQL account and ledger locks prevent concurrent authorization/review edits;
the final byte read separately detects changes to filesystem source artifacts.
Internal runtime reads may share row locks; preparation remains exclusive by default.
Shared readers must never mutate rows or upgrade locks inside this context.
"""
    if (type(shared) is not bool or not isinstance(operator_id, str) or not 1 <= len(operator_id) <= 64
            or not isinstance(source_id, str) or re.fullmatch(r"[0-9a-f]{64}", source_id) is None
            or any(type(value) is not int or not 1 <= value <= 1000
                   for value in (expected_source_review_revision, expected_mapping_revision))):
        raise SnapshotError("Supply exact source, operator and positive review revisions")
    try:
        with store.session() as session:
            operator = _operator(session, operator_id, shared=shared)
            identity = (operator.id, operator.firm_id, operator.role)
            package = _package(source_store, source_id)
            snapshot = _load(store, session, package, operator,
                             expected_source_review_revision, expected_mapping_revision, shared=shared)
            original_binding = _canonical(snapshot["binding"])
            original_bytes = {name: bytes(content) for name, content in package.artifacts.items()}
            yield snapshot
            operator = _operator(session, operator_id, shared=shared)
            if (operator.id, operator.firm_id, operator.role) != identity:
                raise SnapshotError("The operator identity or role changed during preparation")
            verified_package = _package(source_store, source_id)
            if verified_package.artifacts != original_bytes:
                raise SnapshotError("The source package changed during preparation")
            final = _load(store, session, verified_package, operator,
                          expected_source_review_revision, expected_mapping_revision, shared=shared)
            if _canonical(final["binding"]) != original_binding:
                raise SnapshotError("Review state changed during preparation")
            # Session context closes with rollback. No COMMIT, audit or mutation.
    except HTTPException:
        raise SnapshotError("Review ledger integrity validation failed") from None
    except SQLAlchemyError:
        raise SnapshotError("Existing review storage is unavailable or changed concurrently") from None
