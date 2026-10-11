"""Firm-confidential canonical identity proposals and independent review events."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now, uid


class DecisionIdentityHead(Base):
    __tablename__ = "decision_identity_heads"
    __table_args__ = (UniqueConstraint("firm_id", "source_id", name="uq_decision_identity_source"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)


class DecisionIdentityEvent(Base):
    __tablename__ = "decision_identity_events"
    __table_args__ = (UniqueConstraint("head_id", "revision", name="uq_decision_identity_revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    head_id: Mapped[str] = mapped_column(ForeignKey("decision_identity_heads.id"), index=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class DecisionIdentityReservation(Base):
    __tablename__ = "decision_identity_reservations"
    __table_args__ = (UniqueConstraint("firm_id", "canonical_id", name="uq_decision_canonical_reservation"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    canonical_id: Mapped[str] = mapped_column(String(180), index=True)
    payload: Mapped[str] = mapped_column(Text)


@event.listens_for(DecisionIdentityEvent, "before_update")
@event.listens_for(DecisionIdentityEvent, "before_delete")
def _immutable(mapper, connection, target):
    raise ValueError("Decision identity review events are append-only")
