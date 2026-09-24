"""质量校验测试：逐项覆盖致命项、警告项，以及三条「刻意不报」的反例。

另有一条 parity 测试：同一份数据分别交给我们的实现与 `quality_check.py`，
两边结论必须一致（PRD 明确要求复用已验证逻辑，不能有两套标准）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from app.services.quality import (
    FATAL_CODES,
    audit_payload,
    audit_question_set,
    extract_asserted_answers,
    group_fatal_issues,
    is_low_quality_option,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_quality_script():
    spec = importlib.util.spec_from_file_location(
        "quality_check_script", PROJECT_ROOT / "quality_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # dataclass 需要模块已注册到 sys.modules（否则取不到 cls.__module__ 对应的命名空间）
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _codes(issues) -> set[str]:  # noqa: ANN001
    return {issue.code for issue in issues}


def _single_question(**overrides: Any) -> dict[str, Any]:
    question: dict[str, Any] = {
        "id": "q1",
        "knowledge_point_id": "kp1",
        "type": "single",
        "difficulty": 2,
        "stem": "提高存款准备金率会怎样影响商业银行可放贷资金？",
        "options": [
            {"key": "A", "text": "变多"},
            {"key": "B", "text": "变少"},
            {"key": "C", "text": "不变"},
            {"key": "D", "text": "无法判断"},
        ],
        "answer": ["B"],
        "explanation": "准备金率提高后银行要缴存更多准备金，可用于放贷的资金自然减少。" * 2,
    }
    question.update(overrides)
    return question


def _payload(*questions: dict[str, Any]) -> dict[str, Any]:
    return {
        "outline": [{"id": "kp1", "title": "存款准备金率", "summary": "缴存比例"}],
        "questions": list(questions) or [_single_question()],
    }


# ---------- 致命项 ----------


def test_answer_not_in_options_is_fatal() -> None:
    issues = audit_payload(_payload(_single_question(answer=["E"])))

    assert "answer_not_in_options" in _codes(issues)
    assert group_fatal_issues(issues)


def test_option_text_duplicate_is_fatal() -> None:
    question = _single_question(
        options=[
            {"key": "A", "text": "变少"},
            {"key": "B", "text": "变少"},
            {"key": "C", "text": "不变"},
            {"key": "D", "text": "无法判断"},
        ]
    )

    assert "option_text_dup" in _codes(audit_payload(_payload(question)))


def test_option_key_gap_is_fatal() -> None:
    # PRD F3：选项 key 跳号 / 缺号属于致命问题
    question = _single_question(
        options=[
            {"key": "A", "text": "甲"},
            {"key": "C", "text": "乙"},
            {"key": "D", "text": "丙"},
            {"key": "E", "text": "丁"},
        ],
        answer=["C"],
    )

    assert "option_key_gap" in _codes(audit_payload(_payload(question)))


def test_low_quality_option_is_fatal() -> None:
    question = _single_question(
        options=[
            {"key": "A", "text": "变少"},
            {"key": "B", "text": "变多"},
            {"key": "C", "text": "不变"},
            {"key": "D", "text": "以上都对"},
        ]
    )

    assert is_low_quality_option("以上都对")
    assert "option_low_quality" in _codes(audit_payload(_payload(question)))


def test_judge_option_count_is_fatal() -> None:
    question = _single_question(
        type="judge",
        options=[
            {"key": "A", "text": "正确"},
            {"key": "B", "text": "错误"},
            {"key": "C", "text": "不确定"},
            {"key": "D", "text": "以上都对"},
        ],
        answer=["A"],
    )

    assert "judge_option_count" in _codes(audit_payload(_payload(question)))


def test_single_option_count_is_fatal() -> None:
    question = _single_question(
        options=[{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}], answer=["A"]
    )

    assert "single_option_count" in _codes(audit_payload(_payload(question)))


def test_multiple_answer_count_is_fatal() -> None:
    question = _single_question(type="multiple", answer=["A"])

    assert "answer_count_mismatch" in _codes(audit_payload(_payload(question)))


def test_kp_ref_invalid_is_fatal() -> None:
    question = _single_question(knowledge_point_id="kp9")

    assert "kp_ref_invalid" in _codes(audit_payload(_payload(question)))


def test_explanation_answer_mismatch_is_fatal() -> None:
    question = _single_question(
        answer=["B"],
        explanation="正确答案应为 A、B、C，因为准备金率提高会减少可放贷资金，这是货币政策的核心传导机制。",
    )

    assert "explanation_answer_mismatch" in _codes(audit_payload(_payload(question)))


def test_stem_duplicate_requires_both_similar_stem_and_overlapping_options() -> None:
    first = _single_question(id="q1")
    second = _single_question(id="q2")

    issues = _codes(audit_payload(_payload(first, second)))

    assert "stem_duplicate" in issues


# ---------- 三条刻意不报（防止误报把好题改坏）----------


def test_minimal_pair_options_are_not_flagged() -> None:
    """只差一两个字的「最小对照选项」是优秀干扰项，不能报。"""
    question = _single_question(
        options=[
            {"key": "A", "text": "光从光密射向光疏"},
            {"key": "B", "text": "光从光疏射向光密"},
            {"key": "C", "text": "光垂直入射"},
            {"key": "D", "text": "光在真空中传播"},
        ],
        answer=["A"],
    )

    assert "option_text_dup" not in _codes(audit_payload(_payload(question)))


def test_parallel_stems_with_different_options_are_not_flagged() -> None:
    """句式相同但考察不同知识点的并列出题，是好的教学设计。"""
    first = _single_question(id="q1", stem="求基期量的公式是？")
    second = _single_question(
        id="q2",
        stem="求增长量的公式是？",
        options=[
            {"key": "A", "text": "现期量 - 基期量"},
            {"key": "B", "text": "基期量 × 增长率"},
            {"key": "C", "text": "现期量 ÷ 增长率"},
            {"key": "D", "text": "增长量 ÷ 基期量"},
        ],
        answer=["A"],
    )

    assert "stem_duplicate" not in _codes(audit_payload(_payload(first, second)))


def test_explaining_wrong_options_is_not_an_answer_mismatch() -> None:
    """「故不选 D」「若选 B 则相反」是标准教学写法，不算答案不一致。"""
    explanation = (
        "准备金率提高会减少可放贷资金，所以选 B。"
        "故不选 D；若选 A 则与原文相反，C 与之无关。"
    ) * 2
    question = _single_question(answer=["B"], explanation=explanation)

    codes = _codes(audit_payload(_payload(question)))

    assert "explanation_answer_mismatch" not in codes
    assert set(extract_asserted_answers(explanation)) == {"B"}


# ---------- 警告项 ----------


def test_short_explanation_is_a_warning_not_fatal() -> None:
    question = _single_question(explanation="准备金率提高会减少可放贷资金，所以答案是 B。")

    issues = audit_payload(_payload(question))

    assert "explanation_too_short" in _codes(issues)
    assert not group_fatal_issues(issues)


def test_uncovered_knowledge_point_is_a_warning() -> None:
    payload = _payload(_single_question())
    payload["outline"].append({"id": "kp2", "title": "再贴现率", "summary": "央行借款利率"})

    issues = audit_payload(payload)

    assert "kp_uncovered" in _codes(issues)
    assert not group_fatal_issues(issues)


def test_flat_difficulty_is_a_warning() -> None:
    questions = [_single_question(id="q1"), _single_question(id="q2")]
    issues = audit_payload(_payload(*questions))

    assert "difficulty_flat" in _codes(issues)


def test_option_set_reused_by_three_questions_is_a_warning() -> None:
    questions = [
        _single_question(id="q1", stem="关于存款准备金率，下列说法正确的是？"),
        _single_question(id="q2", stem="关于再贴现率，下列说法正确的是？"),
        _single_question(id="q3", stem="关于公开市场操作，下列说法正确的是？"),
    ]

    assert "option_set_duplicate" in _codes(audit_payload(_payload(*questions)))


# ---------- 我们自己这套 15 题结构的额外规则 ----------


def test_question_count_and_level_count_are_checked() -> None:
    payload = _payload(_single_question(level_seq=1))

    codes = _codes(audit_question_set(payload, total_levels=3, per_level=5))

    assert "question_count" in codes
    assert "level_question_count" in codes


def test_all_fatal_codes_are_declared_in_the_fatal_set() -> None:
    for code in ("answer_not_in_options", "option_key_gap", "stem_duplicate", "level_question_count"):
        assert code in FATAL_CODES


# ---------- 与 quality_check.py 的一致性 ----------


def test_parity_with_quality_check_script_on_defective_payload() -> None:
    """坏样例：脚本报出的问题我们一个都不能漏（可以多报我们自己新增的规则）。"""
    script = _load_quality_script()
    payload = script.MOCK_PAYLOAD_DEFECTIVE

    ours = _codes(audit_payload(payload))
    theirs = _codes(script.audit_case(payload))

    missing = theirs - ours
    assert not missing, f"移植后漏掉了脚本能报出的问题：{missing}"
    extra = ours - theirs
    assert extra <= {"option_key_gap"}, f"多报了预期之外的规则：{extra}"


def test_parity_with_quality_check_script_on_clean_payload() -> None:
    """干净样例：两边都必须是零问题，保证不会误报。"""
    script = _load_quality_script()
    payload = script.MOCK_PAYLOAD_CLEAN

    assert _codes(audit_payload(payload)) == set()
    assert _codes(script.audit_case(payload)) == set()
