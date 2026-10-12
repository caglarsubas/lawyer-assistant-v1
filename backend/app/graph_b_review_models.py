from sqlalchemy import Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class GraphBReviewHead(Base):
    __tablename__ = "graph_b_review_heads"
    __table_args__ = (UniqueConstraint("firm_id", "context_id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    context_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str]


class GraphBReviewEvent(Base):
    __tablename__ = "graph_b_review_events"
    __table_args__ = (UniqueConstraint("head_id", "revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    firm_id: Mapped[str] = mapped_column(String(64), index=True)
    head_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(80))
    payload: Mapped[str]


@event.listens_for(GraphBReviewEvent, "before_update")
@event.listens_for(GraphBReviewEvent, "before_delete")
def immutable(*args):
    raise ValueError("Graph B signed review history is append-only")
