"""单用户每日生成次数限制（PRD M3-05，防滥用）。"""

from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.db.types import utcnow
from app.repositories import KnowledgeOutlineRepository, KnowledgeSourceRepository


def today_start(now: datetime | None = None) -> datetime:
    moment = now or utcnow()
    return datetime.combine(moment.date(), time.min, tzinfo=timezone.utc)


def ensure_outline_quota(db: Session, user_id: int, settings: Settings) -> None:
    used = KnowledgeSourceRepository(db).count_since(user_id, today_start())
    if used >= settings.daily_outline_quota:
        raise AppError(
            ErrorCode.QUOTA_EXCEEDED,
            f"今天的生成次数用完啦（{settings.daily_outline_quota} 次），明天再来",
        )


def ensure_levels_quota(db: Session, user_id: int, settings: Settings) -> None:
    used = KnowledgeOutlineRepository(db).count_with_levels_since(user_id, today_start())
    if used >= settings.daily_level_quota:
        raise AppError(
            ErrorCode.QUOTA_EXCEEDED,
            f"今天的出题次数用完啦（{settings.daily_level_quota} 次），明天再来",
        )
