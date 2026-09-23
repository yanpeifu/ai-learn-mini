"""出题阶段的资料注入测试（tasks 4.4）。"""

from app.core.config import Settings
from app.schemas.generation import OutlinePoint
from app.services.question_service import generate_question_set
from app.services.search.base import SearchHit
from tests.fakes import ScriptedProvider, make_question_set, outline_points

REFERENCES = [
    SearchHit(
        title="Harness Engineering 官方文档",
        url="https://example.com/harness",
        content="摘要",
        raw_content="整页正文",
    )
]


def test_questions_prompt_carries_references(settings: Settings) -> None:
    provider = ScriptedProvider([make_question_set()])
    points = [OutlinePoint(**item) for item in outline_points()]

    result = generate_question_set(provider, points, settings, references=REFERENCES)

    assert len(result.payload.questions) == 15
    assert "参考资料" in provider.calls[0]["text"]
    assert "https://example.com/harness" in provider.calls[0]["text"]


def test_existing_structural_rules_still_hold_with_references(settings: Settings) -> None:
    """注入资料不得削弱既有的「15 题 / 3 关 / 覆盖每个知识点」校验。"""
    provider = ScriptedProvider([make_question_set()])
    points = [OutlinePoint(**item) for item in outline_points()]

    result = generate_question_set(provider, points, settings, references=REFERENCES)

    per_level: dict[int, int] = {}
    for question in result.payload.questions:
        per_level[question.level_seq] = per_level.get(question.level_seq, 0) + 1

    assert per_level == {1: 5, 2: 5, 3: 5}
    covered = {question.knowledge_point_id for question in result.payload.questions}
    assert covered == {"kp1", "kp2", "kp3"}


def test_generation_without_references_keeps_working(settings: Settings) -> None:
    provider = ScriptedProvider([make_question_set()])
    points = [OutlinePoint(**item) for item in outline_points()]

    result = generate_question_set(provider, points, settings)

    assert len(result.payload.questions) == 15
    assert "参考资料" not in provider.calls[0]["text"]
