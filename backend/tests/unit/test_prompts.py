"""提示词契约测试：约束一旦被删掉就会失败，避免以后改坏提示词。"""

from app.schemas.generation import OutlinePoint
from app.services.prompts import (
    build_backfill_prompt,
    build_outline_prompt,
    build_questions_prompt,
    build_repair_prompt,
    format_outline,
)

POINTS = [
    OutlinePoint(id="kp1", title="存款准备金率", summary="缴存比例决定可放贷资金"),
    OutlinePoint(id="kp2", title="再贴现率", summary="央行借款利率"),
    OutlinePoint(id="kp3", title="公开市场操作", summary="买券投放、卖券回笼"),
]


def test_outline_prompt_requires_three_to_five_points() -> None:
    prompt = build_outline_prompt("存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例……")

    assert "3-5 个" in prompt
    assert "kp1" in prompt
    assert "json" in prompt  # DeepSeek json_object 模式必须出现这个关键词
    assert "「」" in prompt  # 禁止英文双引号


def test_questions_prompt_keeps_all_verified_constraints() -> None:
    prompt = build_questions_prompt(POINTS, total=15, per_level=5)

    # 结构与题量
    assert "15 道题" in prompt
    assert "各有 5 道" in prompt
    assert "level_seq" in prompt
    # 沿用 quality_check.py 已验证的约束
    assert "至少被 1 道题覆盖" in prompt
    assert "严禁使用" in prompt and "以上都对" in prompt
    assert "不少于 40 个汉字" in prompt
    assert "从 A 开始连续编号" in prompt
    assert "难度要有梯度" in prompt
    assert "不得引入外部知识" in prompt
    assert "禁止使用英文双引号" in prompt
    assert "完整闭合" in prompt
    assert "hint" in prompt


def test_questions_prompt_embeds_outline_text() -> None:
    prompt = build_questions_prompt(POINTS, total=15, per_level=5)

    assert "kp1｜存款准备金率：缴存比例决定可放贷资金" in prompt


def test_format_outline_renders_ids_and_summaries() -> None:
    rendered = format_outline(POINTS)

    assert rendered.count("- kp") == 3
    assert "公开市场操作" in rendered


def test_repair_prompt_lists_defects_and_keeps_ids_stable() -> None:
    prompt = build_repair_prompt(
        POINTS,
        [("q3", ["答案 E 不在选项 ['A', 'B', 'C', 'D'] 中", "讲解过短（27 字）"])],
    )

    assert "q3" in prompt
    assert "答案 E 不在选项" in prompt
    assert "保持每道题的 id、level_seq、knowledge_point_id 与原来完全一致" in prompt


def test_backfill_prompt_contains_gaps() -> None:
    prompt = build_backfill_prompt(POINTS, ["第 2 关还缺 2 题，知识点是 kp2", "第 3 关还缺 1 题"])

    assert "第 2 关还缺 2 题" in prompt
    assert "不要重复" in prompt
