from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class Mistake(Base):
    """错题池（MVP 只落库，界面在 V0.5）。"""

    __tablename__ = "mistake"
    __table_args__ = (Index("ix_mistake_user_next_review", "user_id", "next_review_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("question.id"))
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    mastery: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_review_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
