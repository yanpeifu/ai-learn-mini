"""「我的」页数据接口（PRD F6）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import ok
from app.services.stats_service import build_user_stats

router = APIRouter(tags=["user"])


@router.get("/user/stats")
def user_stats(db: DbSession, user: CurrentUser) -> dict:
    stats = build_user_stats(db, user_id=user.id)
    return ok(
        {
            "study_count": stats.study_count,
            "answered_count": stats.answered_count,
            "avg_accuracy": stats.avg_accuracy,
            "study_days": stats.study_days,
            "streak_days": stats.streak_days,
            "mistake_due_count": stats.mistake_due_count,
        }
    )
