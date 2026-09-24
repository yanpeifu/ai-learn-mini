from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONVariant, UTCDateTime, utcnow


class KnowledgeSource(Base):
    """知识源：用户输入的那段原始内容。"""

    __tablename__ = "knowledge_source"
    __table_args__ = (Index("ix_knowledge_source_user", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    input_type: Mapped[str] = mapped_column(String(16), default="text")
    raw_text: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(128))
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KnowledgeOutline(Base):
    """知识大纲：AI 拆出的 3–5 个知识点。"""

    __tablename__ = "knowledge_outline"
    __table_args__ = (Index("ix_knowledge_outline_user", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("knowledge_source.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String(128), default="")
    outline_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONVariant, default=list)
    status: Mapped[str] = mapped_column(String(16), default="generating")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
