from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class User(Base):
    """用户表。"""

    __tablename__ = "user"
    __table_args__ = (Index("ix_user_openid", "openid", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    openid: Mapped[str] = mapped_column(String(64))
    nickname: Mapped[str] = mapped_column(String(64), default="学习者")
    avatar_url: Mapped[str | None] = mapped_column(String(512), default=None)
    is_member: Mapped[bool] = mapped_column(Boolean, default=False)
    member_expire_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
