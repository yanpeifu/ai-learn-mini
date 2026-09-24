from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONVariant, UTCDateTime, utcnow


class Level(Base):
    """关卡：MVP 为 3 关 × 5 题。"""

    __tablename__ = "level"
    __table_args__ = (UniqueConstraint("outline_id", "seq", name="uq_level_outline_seq"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    outline_id: Mapped[int] = mapped_column(ForeignKey("knowledge_outline.id"))
    seq: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(64))
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    question_count: Mapped[int] = mapped_column(Integer, default=5)


class Question(Base):
    """题目。

    注意：answer_json / explanation 属于「服务端私有数据」，
    下发到小程序前必须剔除（见 PRD 2.5 接口设计要求第 3 条）。
    """

    __tablename__ = "question"
    __table_args__ = (Index("ix_question_level_seq", "level_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("level.id"))
    outline_id: Mapped[int] = mapped_column(ForeignKey("knowledge_outline.id"))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(16))
    difficulty: Mapped[int] = mapped_column(SmallInteger, default=3)
    stem: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONVariant, default=list)
    answer_json: Mapped[list[str]] = mapped_column(JSONVariant, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    hint_json: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, default=None)
    quality_score: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    # 被举报 ≥3 次后自动下线（PRD M3-06）：不为空表示暂停下发
    disabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
