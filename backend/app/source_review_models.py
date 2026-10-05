"""Firm-confidential review state, separate from matter and public graph records."""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now, uid


class SourceReviewHead(Base):
    __tablename__ = "source_review_heads"
    __table_args__ = (UniqueConstraint("firm_id", "source_id", name="uq_source_review_firm_source"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class SourceReviewEvent(Base):
    __tablename__ = "source_review_events"
    __table_args__ = (UniqueConstraint("head_id", "revision", name="uq_source_review_event_revision"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    head_id: Mapped[str] = mapped_column(ForeignKey("source_review_heads.id"), index=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


@event.listens_for(SourceReviewEvent, "before_update")
@event.listens_for(SourceReviewEvent, "before_delete")
def _immutable_event(mapper, connection, target):
    raise ValueError("Source review events are append-only")
