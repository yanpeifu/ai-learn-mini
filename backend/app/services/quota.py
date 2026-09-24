"""单用户每日生成次数限制（PRD M3-05，防滥用）。"""

from __future__ import annotations

import threading
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


# --------------------------------------------------------------------------- #
# 联网检索的每日上限
# 检索结果不落库（design.md D6），没有现成的表可计数，所以用进程内计数。
# 已知局限：多实例部署时不共享、进程重启即清零；单实例部署足够防滥用。
# 注意：超过上限只**降级**（按无资料继续生成），不像生成次数那样直接报错。
# --------------------------------------------------------------------------- #

_search_usage: dict[tuple[int, str], int] = {}
_search_lock = threading.Lock()


def _search_key(user_id: int, now: datetime | None = None) -> tuple[int, str]:
    return (user_id, today_start(now).date().isoformat())


def search_used_today(user_id: int, now: datetime | None = None) -> int:
    with _search_lock:
        return _search_usage.get(_search_key(user_id, now), 0)


def search_quota_exceeded(
    user_id: int, settings: Settings, now: datetime | None = None
) -> bool:
    return search_used_today(user_id, now) >= settings.daily_search_quota


def record_search_usage(user_id: int, count: int = 1, now: datetime | None = None) -> None:
    with _search_lock:
        key = _search_key(user_id, now)
        _search_usage[key] = _search_usage.get(key, 0) + count


def reset_search_usage() -> None:
    """测试用：清空计数。"""
    with _search_lock:
        _search_usage.clear()
