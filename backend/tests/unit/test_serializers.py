"""下发数据的序列化测试：**绝不能带答案**。"""

import pytest
from app.models import Question
from app.repositories import (
    KnowledgeOutlineRepository,
    KnowledgeSourceRepository,
    LevelRepository,
    QuestionRepository,
    UserRepository,
)
from app.services.serializers import build_public_levels, to_public_question


@pytest.fixture()
def quiz_context(db_session):  # noqa: ANN001
    """一个用户 / 一个知识点 / 一个关卡，供多道题复用同一个 outline。"""
    user = UserRepository(db_session).get_or_create_by_openid("serializer-user")
    source = KnowledgeSourceRepository(db_session).create(
        user_id=user.id, raw_text="知" * 30, title="知识点"
    )
    outline = KnowledgeOutlineRepository(db_session).create(
        source_id=source.id,
        user_id=user.id,
        title="大纲",
        points=[{"id": "kp1", "title": "存款准备金率", "summary": "说明"}],
    )
    level = LevelRepository(db_session).create(
        outline_id=outline.id,
        seq=1,
        title="第 1 关 · 存款准备金率",
        knowledge_point="存款准备金率",
    )
    return outline, level


def _question(db_session, quiz_context, **overrides) -> Question:  # noqa: ANN001
    outline, level = quiz_context
    defaults = dict(
        level_id=level.id,
        outline_id=outline.id,
        seq=1,
        type="single",
        difficulty=2,
        stem="提高存款准备金率会怎样？",
        options=[
            {"key": "A", "text": "变多"},
            {"key": "B", "text": "变少"},
            {"key": "C", "text": "不变"},
            {"key": "D", "text": "无法判断"},
        ],
        answer=["B"],
        explanation="准备金率提高后可用于放贷的资金减少。",
    )
    defaults.update(overrides)
    return QuestionRepository(db_session).create(**defaults)


def test_public_question_has_no_answer_or_explanation(db_session, quiz_context) -> None:  # noqa: ANN001
    question = _question(db_session, quiz_context)

    payload = to_public_question(question)

    assert set(payload) == {"id", "seq", "type", "difficulty", "stem", "options"}
    assert "answer" not in str(payload)
    assert "explanation" not in str(payload)
    assert payload["options"][1] == {"key": "B", "text": "变少"}


def test_disabled_questions_are_not_served(db_session, quiz_context) -> None:  # noqa: ANN001
    visible = _question(db_session, quiz_context, seq=1)
    hidden = _question(
        db_session, quiz_context, seq=2, stem="第二题：下列哪一项说法是正确的？"
    )
    QuestionRepository(db_session).set_disabled(hidden.id)

    levels = build_public_levels(db_session, visible.outline_id)

    assert len(levels[0]["questions"]) == 1
    assert levels[0]["questions"][0]["id"] == visible.id


def test_include_disabled_returns_everything(db_session, quiz_context) -> None:  # noqa: ANN001
    visible = _question(db_session, quiz_context, seq=1)
    hidden = _question(
        db_session, quiz_context, seq=2, stem="第二题：下列哪一项说法是正确的？"
    )
    QuestionRepository(db_session).set_disabled(hidden.id)

    levels = build_public_levels(db_session, visible.outline_id, include_disabled=True)

    assert len(levels[0]["questions"]) == 2
