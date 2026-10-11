"""Encrypted firm-local decision mapping ledger; never public graph records."""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now, uid


class DecisionMappingHead(Base):
    __tablename__ = "decision_mapping_heads"
    __table_args__ = (UniqueConstraint("firm_id", "source_id", name="uq_decision_mapping_firm_source"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class DecisionMappingEvent(Base):
    __tablename__ = "decision_mapping_events"
    __table_args__ = (UniqueConstraint("head_id", "revision", name="uq_decision_mapping_event_revision"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    head_id: Mapped[str] = mapped_column(ForeignKey("decision_mapping_heads.id"), index=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


@event.listens_for(DecisionMappingEvent, "before_update")
@event.listens_for(DecisionMappingEvent, "before_delete")
def _immutable_event(mapper, connection, target):
    raise ValueError("Decision mapping events are append-only")
