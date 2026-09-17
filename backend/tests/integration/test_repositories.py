"""数据访问层测试：每张表的基础 CRUD 都能用（M2-05 验收）。"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import AnswerRecord, Attempt, KnowledgeOutline, Level, Question
from app.repositories import (
    AnswerRecordRepository,
    AttemptRepository,
    KnowledgeOutlineRepository,
    KnowledgeSourceRepository,
    LevelRepository,
    MistakeRepository,
    QuestionReportRepository,
    QuestionRepository,
    UserRepository,
)


@pytest.fixture()
def user(db_session: Session):
    return UserRepository(db_session).get_or_create_by_openid("openid-crud")


@pytest.fixture()
def outline(db_session: Session, user):
    source = KnowledgeSourceRepository(db_session).create(
        user_id=user.id,
        raw_text="行政复议与行政诉讼的区别：受理机关、审查范围与程序都不同。" * 2,
        title="行政复议与行政诉讼",
    )
    return KnowledgeOutlineRepository(db_session).create(
        source_id=source.id,
        user_id=user.id,
        title="行政复议与行政诉讼",
        points=[{"id": "kp1", "title": "受理机关", "summary": "区别之一"}],
    )


def test_user_get_or_create_is_idempotent(db_session: Session) -> None:
    repo = UserRepository(db_session)

    first = repo.get_or_create_by_openid("openid-x")
    second = repo.get_or_create_by_openid("openid-x")

    assert first.id == second.id
    assert first.nickname == "学习者"
    assert first.last_login_at is not None


def test_source_repository_counts_chars(db_session: Session, user) -> None:
    raw = "光合作用是植物利用光能，把二氧化碳和水转化成有机物并释放氧气的过程。"

    source = KnowledgeSourceRepository(db_session).create(
        user_id=user.id, raw_text=raw, title="光合作用"
    )

    assert source.id is not None
    assert source.char_count == len(raw)
    assert source.input_type == "text"


def test_outline_repository_update_points(db_session: Session, outline) -> None:
    repo = KnowledgeOutlineRepository(db_session)

    updated = repo.update_points(
        outline.id, points=[{"id": "kp1", "title": "改后的标题", "summary": "说明"}]
    )

    assert updated is not None
    assert updated.outline_json[0]["title"] == "改后的标题"
    assert repo.get(outline.id).status == "ready"


def test_level_and_question_repository(db_session: Session, outline) -> None:
    level_repo = LevelRepository(db_session)
    question_repo = QuestionRepository(db_session)

    level = level_repo.create(
        outline_id=outline.id, seq=1, title="第 1 关 · 基础概念", knowledge_point="受理机关"
    )
    questions = [
        question_repo.create(
            level_id=level.id,
            outline_id=outline.id,
            seq=seq,
            type="single",
            difficulty=2,
            stem=f"第 {seq} 题的题干",
            options=[{"key": "A", "text": "选项A"}, {"key": "B", "text": "选项B"}],
            answer=["A"],
            explanation="讲解内容" * 12,
        )
        for seq in range(1, 6)
    ]
    question_repo.replace_level_questions(level.id, questions[1:3])

    assert level_repo.count_by_outline(outline.id) == 1
    assert question_repo.count_by_level(level.id) == 2
    assert question_repo.list_by_level(level.id)[0].seq == 2


def test_attempt_and_answers(db_session: Session, user, outline) -> None:
    level = LevelRepository(db_session).create(
        outline_id=outline.id, seq=1, title="第 1 关", knowledge_point="受理机关"
    )
    question = QuestionRepository(db_session).create(
        level_id=level.id,
        outline_id=outline.id,
        seq=1,
        type="judge",
        difficulty=1,
        stem="行政复议只能向上一级行政机关提出。",
        options=[{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}],
        answer=["B"],
        explanation="也可以向法定复议机关提出。" * 5,
    )
    att_repo = AttemptRepository(db_session)
    attempt = att_repo.create(user_id=user.id, outline_id=outline.id, total_count=15)

    record = AnswerRecordRepository(db_session).create(
        attempt_id=attempt.id,
        question_id=question.id,
        user_id=user.id,
        answer=["A"],
        is_correct=False,
        elapsed_ms=5200,
    )
    att_repo.finish(
        attempt.id,
        correct_count=0,
        accuracy=Decimal("0.00"),
        duration_ms=5200,
        star=0,
    )

    assert record.id is not None
    assert att_repo.get_ongoing(user.id) is None
    finished = att_repo.get(attempt.id)
    assert finished.status == "finished"
    assert finished.finished_at is not None
    assert AnswerRecordRepository(db_session).count_by_attempt(attempt.id) == 1
    assert AnswerRecordRepository(db_session).has_answered(attempt.id, question.id) is True


def test_mistake_and_report_repository(db_session: Session, user, outline) -> None:
    level = LevelRepository(db_session).create(
        outline_id=outline.id, seq=1, title="第 1 关", knowledge_point="受理机关"
    )
    question = QuestionRepository(db_session).create(
        level_id=level.id,
        outline_id=outline.id,
        seq=1,
        type="single",
        difficulty=1,
        stem="题干",
        options=[{"key": "A", "text": "a"}, {"key": "B", "text": "b"}],
        answer=["A"],
        explanation="讲解" * 30,
    )

    mistake_repo = MistakeRepository(db_session)
    first = mistake_repo.record_wrong(user.id, question.id, interval_days=1)
    second = mistake_repo.record_wrong(user.id, question.id, interval_days=1)

    assert first.id == second.id
    assert second.wrong_count == 2
    assert second.next_review_at > datetime.now(timezone.utc)
    assert mistake_repo.count_due(user.id) == 0  # 还没到复习时间

    report_repo = QuestionReportRepository(db_session)
    count = report_repo.create(question_id=question.id, user_id=user.id, reason="wrong_answer")
    assert count == 1
    assert report_repo.count_pending(question.id) == 1
    assert report_repo.is_flagged(question.id, threshold=3) is False

    report_repo.create(question_id=question.id, user_id=user.id, reason="unclear")
    report_repo.create(question_id=question.id, user_id=user.id, reason="duplicate")
    assert report_repo.is_flagged(question.id, threshold=3) is True
