"""判定与结算测试（PRD F4 判分规则 / F5 星级与薄弱点）。"""

from decimal import Decimal

import pytest
from app.core.config import Settings
from app.models import Question
from app.repositories import AttemptRepository, MistakeRepository
from app.services.attempt_service import (
    build_settlement,
    judge,
    star_for,
)


def _question(db_session, quiz_setup, index: int = 0, level: int = 0) -> Question:  # noqa: ANN001
    return quiz_setup["levels"][level][1][index]


def test_judge_single_choice_requires_exact_key(db_session, quiz_setup) -> None:  # noqa: ANN001
    question = _question(db_session, quiz_setup)
    correct = list(question.answer_json)
    wrong = [key for key in ("A", "B", "C", "D") if key not in correct][:1]

    assert judge(question, correct) is True
    assert judge(question, wrong) is False
    assert judge(question, []) is False


def test_judge_is_case_insensitive_and_order_insensitive() -> None:
    class _Q:
        answer_json = ["A", "C"]

    assert judge(_Q(), ["c", "a"]) is True  # type: ignore[arg-type]
    assert judge(_Q(), ["A"]) is False  # 多选少选也算错
    assert judge(_Q(), ["A", "B", "C"]) is False  # 多选多选也算错


@pytest.mark.parametrize(
    ("accuracy", "star"),
    [(100.0, 3), (90.0, 3), (89.9, 2), (70.0, 2), (69.9, 1), (50.0, 1), (49.9, 0), (0.0, 0)],
)
def test_star_rules(accuracy: float, star: int) -> None:
    assert star_for(accuracy) == star


def _answer_all(db_session, quiz_setup, attempt_id: int, *, correct: bool) -> None:
    from app.services.attempt_service import submit_answer

    user = quiz_setup["user"]
    attempt = AttemptRepository(db_session).get(attempt_id)
    for _level, questions in quiz_setup["levels"]:
        for question in questions:
            answer = list(question.answer_json)
            if not correct:
                answer = [key for key in ("A", "B", "C", "D") if key not in answer][:1]
            submit_answer(
                db_session,
                user_id=user.id,
                attempt=attempt,
                question=question,
                answer=answer,
                elapsed_ms=3000,
            )


def test_all_correct_gives_three_stars_and_no_weak_point(db_session, quiz_setup, settings: Settings) -> None:  # noqa: ANN001
    attempt = AttemptRepository(db_session).create(
        user_id=quiz_setup["user"].id, outline_id=quiz_setup["outline"].id, total_count=15
    )
    _answer_all(db_session, quiz_setup, attempt.id, correct=True)

    settlement = build_settlement(db_session, attempt=attempt, settings=settings)

    assert settlement.correct_count == 15
    assert settlement.accuracy == 100.0
    assert settlement.star == 3
    assert settlement.weak_points == []
    assert len(settlement.points) == 3
    assert settlement.duration_ms == 15 * 3000
    assert "掌握" in settlement.advice


def test_all_wrong_gives_zero_stars_weak_points_and_encouraging_advice(db_session, quiz_setup, settings: Settings) -> None:  # noqa: ANN001
    attempt = AttemptRepository(db_session).create(
        user_id=quiz_setup["user"].id, outline_id=quiz_setup["outline"].id, total_count=15
    )
    _answer_all(db_session, quiz_setup, attempt.id, correct=False)

    settlement = build_settlement(db_session, attempt=attempt, settings=settings)

    assert settlement.accuracy == 0.0
    assert settlement.star == 0
    assert settlement.weak_points
    assert "先看看错题" in settlement.advice
    # 答错的题都进了错题池
    mistakes = MistakeRepository(db_session).count_due(quiz_setup["user"].id)
    assert mistakes == 0  # 复习时间在 1 天后，当前还不到期
    assert MistakeRepository(db_session).get_by_user_question(
        quiz_setup["user"].id, _question(db_session, quiz_setup).id
    ) is not None


def test_partial_answers_are_scored_against_total(db_session, quiz_setup, settings: Settings) -> None:  # noqa: ANN001
    from app.services.attempt_service import submit_answer

    attempt = AttemptRepository(db_session).create(
        user_id=quiz_setup["user"].id, outline_id=quiz_setup["outline"].id, total_count=15
    )
    first_question = _question(db_session, quiz_setup)
    submit_answer(
        db_session,
        user_id=quiz_setup["user"].id,
        attempt=attempt,
        question=first_question,
        answer=list(first_question.answer_json),
        elapsed_ms=1000,
    )

    settlement = build_settlement(db_session, attempt=attempt, settings=settings)

    assert settlement.correct_count == 1
    assert settlement.total_count == 15
    assert settlement.accuracy == pytest.approx(6.7)  # 1/15 = 6.67% → 保留一位小数


def test_duplicate_submission_is_idempotent(db_session, quiz_setup) -> None:  # noqa: ANN001
    from app.services.attempt_service import submit_answer

    attempt = AttemptRepository(db_session).create(
        user_id=quiz_setup["user"].id, outline_id=quiz_setup["outline"].id, total_count=15
    )
    question = _question(db_session, quiz_setup)
    first = submit_answer(
        db_session,
        user_id=quiz_setup["user"].id,
        attempt=attempt,
        question=question,
        answer=list(question.answer_json),
        elapsed_ms=1000,
    )
    wrong = [key for key in ("A", "B", "C", "D") if key not in question.answer_json][:1]
    second = submit_answer(
        db_session,
        user_id=quiz_setup["user"].id,
        attempt=attempt,
        question=question,
        answer=wrong,
        elapsed_ms=9999,
    )

    assert first.is_correct is True
    assert second.already_answered is True
    assert second.is_correct is True  # 保留首次判定
    assert second.correct_count == 1
    assert second.answered_count == 1


def test_combo_counts_trailing_correct_answers(db_session, quiz_setup) -> None:  # noqa: ANN001
    from app.services.attempt_service import submit_answer

    attempt = AttemptRepository(db_session).create(
        user_id=quiz_setup["user"].id, outline_id=quiz_setup["outline"].id, total_count=15
    )
    questions = quiz_setup["levels"][0][1][:4]
    combo = 0
    for index, question in enumerate(questions):
        answer = list(question.answer_json) if index < 3 else [
            key for key in ("A", "B", "C", "D") if key not in question.answer_json
        ][:1]
        judgment = submit_answer(
            db_session,
            user_id=quiz_setup["user"].id,
            attempt=attempt,
            question=question,
            answer=answer,
            elapsed_ms=1000,
        )
        combo = judgment.combo

    assert combo == 0  # 最后一题答错，连击清零
