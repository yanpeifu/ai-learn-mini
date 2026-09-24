from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class QuestionReport(Base):
    """题目举报（L8 第四层兜底：同一题被 3 人反馈则先下架复核）。"""

    __tablename__ = "question_report"
    __table_args__ = (Index("ix_question_report_question_status", "question_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("question.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    reason: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(String(256), default=None)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
