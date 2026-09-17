"""「我的」页数据（PRD F6 / P5）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.repositories import MistakeRepository, StatsRepository


@dataclass
class UserStats:
    study_count: int
    answered_count: int
    avg_accuracy: float
    study_days: int
    streak_days: int
    mistake_due_count: int


def build_user_stats(db: Session, *, user_id: int) -> UserStats:
    repo = StatsRepository(db)
    dates = sorted({moment.date() for moment in repo.study_dates(user_id)}, reverse=True)
    return UserStats(
        study_count=repo.study_count(user_id),
        answered_count=repo.answered_count(user_id),
        avg_accuracy=repo.average_accuracy(user_id),
        study_days=len(dates),
        streak_days=streak_days(dates),
        mistake_due_count=MistakeRepository(db).count_due(user_id),
    )


def streak_days(dates: list[date], *, today: date | None = None) -> int:
    """连续学习天数：从今天（或昨天）往前连续计数。"""
    if not dates:
        return 0
    current_day = today or utcnow().date()
    latest = dates[0]
    if latest == current_day:
        cursor = current_day
    elif latest == current_day - timedelta(days=1):
        cursor = latest
    else:
        return 0

    known = set(dates)
    streak = 0
    while cursor in known:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
