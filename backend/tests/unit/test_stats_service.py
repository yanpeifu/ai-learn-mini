"""连续学习天数与「我的」页统计测试。"""

from datetime import date, timedelta

from app.services.stats_service import build_user_stats, streak_days
from sqlalchemy.orm import Session


def test_streak_days_without_records() -> None:
    assert streak_days([]) == 0


def test_streak_days_counts_consecutive_days_from_today() -> None:
    today = date(2026, 9, 17)
    dates = [today, today - timedelta(days=1), today - timedelta(days=2)]

    assert streak_days(dates, today=today) == 3


def test_streak_days_allows_last_activity_yesterday() -> None:
    today = date(2026, 9, 17)
    dates = [today - timedelta(days=1), today - timedelta(days=2)]

    assert streak_days(dates, today=today) == 2


def test_streak_days_breaks_on_gap() -> None:
    today = date(2026, 9, 17)
    dates = [today, today - timedelta(days=1), today - timedelta(days=3)]

    assert streak_days(dates, today=today) == 2


def test_streak_days_zero_when_last_activity_is_old() -> None:
    today = date(2026, 9, 17)

    assert streak_days([today - timedelta(days=5)], today=today) == 0


def test_build_user_stats_counts_attempts_and_answers(db_session: Session, quiz_setup) -> None:  # noqa: ANN001
    from app.repositories import AttemptRepository
    from app.services.attempt_service import submit_answer

    attempt = AttemptRepository(db_session).create(
        user_id=quiz_setup["user"].id, outline_id=quiz_setup["outline"].id, total_count=15
    )
    question = quiz_setup["levels"][0][1][0]
    submit_answer(
        db_session,
        user_id=quiz_setup["user"].id,
        attempt=attempt,
        question=question,
        answer=list(question.answer_json),
        elapsed_ms=1500,
    )
    AttemptRepository(db_session).finish(
        attempt.id, correct_count=1, accuracy=__import__("decimal").Decimal("6.7"), duration_ms=1500, star=0
    )

    stats = build_user_stats(db_session, user_id=quiz_setup["user"].id)

    assert stats.study_count == 1
    assert stats.answered_count == 1
    assert stats.avg_accuracy == 6.7
    assert stats.study_days == 1
    assert stats.streak_days == 1
