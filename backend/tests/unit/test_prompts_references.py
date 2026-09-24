"""提示词里的「参考资料」段测试（tasks 4.1）。"""

from app.schemas.generation import OutlinePoint
from app.services.prompts import (
    build_backfill_prompt,
    build_outline_prompt,
    build_questions_prompt,
    build_repair_prompt,
    render_references,
)
from app.services.search.base import SearchHit

POINTS = [OutlinePoint(id="kp1", title="知识点一", summary="说明一")]
HITS = [
    SearchHit(
        title="Harness Engineering 官方文档",
        url="https://example.com/harness",
        content="摘要内容",
        raw_content="整页正文内容",
    )
]


def test_render_references_is_empty_without_hits() -> None:
    assert render_references([]) == ""


def test_render_references_carries_url_body_and_rules() -> None:
    rendered = render_references(HITS)

    assert "【参考资料】" in rendered
    assert "https://example.com/harness" in rendered
    assert "整页正文内容" in rendered  # 有 raw_content 时优先用它
    assert "以参考资料为准" in rendered


def test_outline_prompt_changes_when_references_present() -> None:
    without = build_outline_prompt("一段足够长的知识内容" * 3)
    with_refs = build_outline_prompt("一段足够长的知识内容" * 3, references=HITS)

    assert "参考资料" not in without
    assert "参考资料" in with_refs
    assert "https://example.com/harness" in with_refs


def test_questions_repair_backfill_prompts_accept_references() -> None:
    questions = build_questions_prompt(POINTS, total=15, per_level=5, references=HITS)
    repair = build_repair_prompt(POINTS, [("q1", ["答案不在选项里"])], references=HITS)
    backfill = build_backfill_prompt(POINTS, ["第 1 关还缺 1 题"], references=HITS)

    for prompt in (questions, repair, backfill):
        assert "参考资料" in prompt
        assert "https://example.com/harness" in prompt


def test_outline_prompt_asks_for_reference_decision_fields() -> None:
    prompt = build_outline_prompt("一段足够长的知识内容" * 3)

    assert "needs_external_reference" in prompt
    assert "search_queries" in prompt
    assert "complexity" in prompt
    assert "timeliness" in prompt
