"""数据模型测试：表名、字段、JSON 列、外键与索引必须与 PRD 2.4 一致。"""

from decimal import Decimal

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import (
    AnswerRecord,
    Attempt,
    KnowledgeOutline,
    KnowledgeSource,
    Level,
    Mistake,
    Question,
    QuestionReport,
    User,
)


def test_all_nine_tables_exist(db_engine) -> None:
    tables = set(inspect(db_engine).get_table_names())

    assert {
        "user",
        "knowledge_source",
        "knowledge_outline",
        "level",
        "question",
        "attempt",
        "answer_record",
        "mistake",
        "question_report",
    } <= tables


def test_question_columns_match_prd(db_engine) -> None:
    columns = {col["name"] for col in inspect(db_engine).get_columns("question")}

    assert columns == {
        "id",
        "level_id",
        "outline_id",
        "seq",
        "type",
        "difficulty",
        "stem",
        "options_json",
        "answer_json",
        "explanation",
        "hint_json",
        "quality_score",
        "created_at",
    }


def test_indexes_match_prd(db_engine) -> None:
    inspector = inspect(db_engine)

    def index_names(table: str) -> set[str]:
        return {idx["name"] for idx in inspector.get_indexes(table)}

    assert "ix_attempt_user_started" in index_names("attempt")
    assert "ix_answer_record_attempt" in index_names("answer_record")
    assert "ix_question_level_seq" in index_names("question")
    assert "ix_mistake_user_next_review" in index_names("mistake")
    assert "ix_question_report_question_status" in index_names("question_report")
    assert "ix_user_openid" in index_names("user")


def test_full_chain_roundtrip(db_session: Session) -> None:
    """一条测试覆盖「用户 → 知识源 → 大纲 → 关卡 → 题目 → 闯关 → 作答 → 错题 → 举报」全链路。"""
    user = User(openid="openid-1", nickname="学习者")
    db_session.add(user)
    db_session.flush()

    source = KnowledgeSource(
        user_id=user.id,
        input_type="text",
        raw_text="存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例。",
        title="存款准备金率",
        char_count=32,
    )
    db_session.add(source)
    db_session.flush()

    outline = KnowledgeOutline(
        source_id=source.id,
        user_id=user.id,
        title="货币政策三大工具",
        outline_json=[{"id": "kp1", "title": "存款准备金率", "summary": "缴存比例"}],
        status="ready",
    )
    db_session.add(outline)
    db_session.flush()

    level = Level(
        outline_id=outline.id,
        seq=1,
        title="第 1 关 · 基础概念",
        knowledge_point="存款准备金率",
        question_count=5,
    )
    db_session.add(level)
    db_session.flush()

    question = Question(
        level_id=level.id,
        outline_id=outline.id,
        seq=1,
        type="single",
        difficulty=2,
        stem="提高存款准备金率会怎样影响商业银行可放贷资金？",
        options_json=[
            {"key": "A", "text": "变多"},
            {"key": "B", "text": "变少"},
            {"key": "C", "text": "不变"},
            {"key": "D", "text": "无法判断"},
        ],
        answer_json=["B"],
        explanation="准备金率提高，银行要缴存更多准备金，可用于放贷的资金就会减少。",
        hint_json=None,
        quality_score=92,
    )
    db_session.add(question)
    db_session.flush()

    attempt = Attempt(
        user_id=user.id,
        outline_id=outline.id,
        status="ongoing",
        total_count=15,
    )
    db_session.add(attempt)
    db_session.flush()

    answer = AnswerRecord(
        attempt_id=attempt.id,
        question_id=question.id,
        user_id=user.id,
        user_answer_json=["A"],
        is_correct=False,
        elapsed_ms=8400,
    )
    db_session.add(answer)

    mistake = Mistake(user_id=user.id, question_id=question.id, wrong_count=1, mastery=0)
    db_session.add(mistake)

    report = QuestionReport(question_id=question.id, user_id=user.id, reason="unclear")
    db_session.add(report)
    db_session.commit()

    attempt.status = "finished"
    attempt.correct_count = 0
    attempt.accuracy = Decimal("0.00")
    attempt.duration_ms = 8400
    attempt.star = 0
    db_session.commit()

    stored = db_session.get(Attempt, attempt.id)
    assert stored is not None
    assert stored.status == "finished"
    assert stored.accuracy == Decimal("0.00")
    assert stored.started_at is not None and stored.started_at.tzinfo is not None
    assert stored.finished_at is None

    stored_question = db_session.get(Question, question.id)
    assert stored_question is not None
    assert stored_question.options_json[1] == {"key": "B", "text": "变少"}
    assert stored_question.answer_json == ["B"]
    assert stored_question.hint_json is None

    assert db_session.query(AnswerRecord).filter_by(attempt_id=attempt.id).count() == 1
    assert db_session.query(Mistake).filter_by(user_id=user.id).count() == 1
    assert db_session.query(QuestionReport).filter_by(question_id=question.id).count() == 1


def test_user_openid_is_unique(db_session: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    db_session.add(User(openid="dup-openid"))
    db_session.commit()
    db_session.add(User(openid="dup-openid"))

    try:
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
    else:  # pragma: no cover - 只有在唯一约束失效时才会走到
        raise AssertionError("openid 唯一约束没有生效")
