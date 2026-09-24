from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONVariant, UTCDateTime, utcnow


class Attempt(Base):
    """一次完整的闯关（从开始到结算）。"""

    __tablename__ = "attempt"
    __table_args__ = (
        # 首页「继续上次的学习」与学习记录列表都靠这两个索引
        Index("ix_attempt_user_started", "user_id", "started_at"),
        Index("ix_attempt_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    outline_id: Mapped[int] = mapped_column(ForeignKey("knowledge_outline.id"))
    status: Mapped[str] = mapped_column(String(16), default="ongoing")
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    star: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class AnswerRecord(Base):
    """单题作答记录。"""

    __tablename__ = "answer_record"
    __table_args__ = (Index("ix_answer_record_attempt", "attempt_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempt.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("question.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user_answer_json: Mapped[list[str]] = mapped_column(JSONVariant, default=list)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    answered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
