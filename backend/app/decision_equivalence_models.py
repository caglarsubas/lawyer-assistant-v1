"""Private version-bound equivalence opinions; existing identity reservations stay intact."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now, uid


class DecisionEquivalenceHead(Base):
    __tablename__ = "decision_equivalence_heads"
    __table_args__ = (UniqueConstraint("firm_id", "context_id", name="uq_decision_equivalence_context"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    context_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)


class DecisionEquivalenceEvent(Base):
    __tablename__ = "decision_equivalence_events"
    __table_args__ = (UniqueConstraint("head_id", "revision", name="uq_decision_equivalence_revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    head_id: Mapped[str] = mapped_column(ForeignKey("decision_equivalence_heads.id"), index=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


@event.listens_for(DecisionEquivalenceEvent, "before_update")
@event.listens_for(DecisionEquivalenceEvent, "before_delete")
def _immutable(mapper, connection, target):
    raise ValueError("Decision equivalence opinions are append-only")
