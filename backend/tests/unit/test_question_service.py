"""出题服务测试：15 题结构、单题重生、丢弃补足、失败不留脏数据。"""

import pytest
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.generation import GeneratedQuestionSet, OutlinePoint
from app.services.llm.base import LLMBadFormatError, LLMUnavailableError
from app.services.quality import audit_question_set, fatal_issues
from app.services.question_service import (
    assign_levels,
    build_gaps,
    generate_question_set,
    merge_questions,
)
from tests.fakes import (
    ScriptedProvider,
    make_defective_question,
    make_question,
    make_question_set,
    outline_points,
)


def _points() -> list[OutlinePoint]:
    return [OutlinePoint(**point) for point in outline_points()]


def _level_counts(payload: GeneratedQuestionSet) -> dict[int, int]:
    counts: dict[int, int] = {}
    for question in payload.questions:
        counts[question.level_seq] = counts.get(question.level_seq, 0) + 1
    return counts


def test_generates_valid_set_without_any_repair(settings: Settings) -> None:
    provider = ScriptedProvider([make_question_set()])

    result = generate_question_set(provider, _points(), settings)

    assert len(result.payload.questions) == 15
    assert _level_counts(result.payload) == {1: 5, 2: 5, 3: 5}
    assert result.regenerated == 0
    assert result.dropped == 0
    assert result.backfilled == 0
    assert fatal_issues(
        audit_question_set(result.payload.to_payload(), total_levels=3, per_level=5)
    ) == []
    assert len(provider.calls) == 1


def test_level_seq_from_model_is_ignored_and_reassigned(settings: Settings) -> None:
    raw = make_question_set()
    for question in raw["questions"]:
        question["level_seq"] = 1  # 模型把 15 道题全写成第 1 关
    provider = ScriptedProvider([raw])

    result = generate_question_set(provider, _points(), settings)

    assert _level_counts(result.payload) == {1: 5, 2: 5, 3: 5}


def test_defective_question_is_regenerated(settings: Settings) -> None:
    raw = make_question_set()
    raw["questions"][2] = make_defective_question(3)
    # 修复回来的题要保持原来的 id 与知识点
    repaired = {"questions": [make_question(3, knowledge_point_id="kp3", level_seq=1)]}
    provider = ScriptedProvider([raw, repaired])

    result = generate_question_set(provider, _points(), settings)

    assert result.regenerated == 1
    assert result.dropped == 0
    assert len(result.payload.questions) == 15
    assert provider.calls[1]["purpose"] == "repair"


def test_repair_failure_drops_and_backfills(settings: Settings) -> None:
    raw = make_question_set()
    raw["questions"][3] = make_defective_question(4)
    provider = ScriptedProvider(
        [
            raw,
            LLMBadFormatError("修复调用失败"),  # 单题重生成失败
            # 第 4 题属于第 1 关，所以补一道第 1 关的题
            {"questions": [make_question(101, knowledge_point_id="kp1", level_seq=1)]},
        ]
    )

    result = generate_question_set(provider, _points(), settings)

    assert result.dropped == 1
    assert result.backfilled == 1
    assert len(result.payload.questions) == 15
    assert _level_counts(result.payload) == {1: 5, 2: 5, 3: 5}
    assert any(call["purpose"] == "backfill" for call in provider.calls)


def test_uncovered_knowledge_point_triggers_backfill(settings: Settings) -> None:
    raw = make_question_set()
    for question in raw["questions"]:
        question["knowledge_point_id"] = "kp1"  # kp2 / kp3 完全没有被覆盖
    provider = ScriptedProvider(
        [
            raw,
            {
                "questions": [
                    make_question(201, knowledge_point_id="kp2", level_seq=1),
                    make_question(202, knowledge_point_id="kp3", level_seq=1),
                ]
            },
        ]
    )

    result = generate_question_set(provider, _points(), settings)

    assert result.backfilled >= 1
    assert result.dropped >= 2  # 为了给 kp2 / kp3 腾位置，删掉了两道冗余题
    covered = {question.knowledge_point_id for question in result.payload.questions}
    assert {"kp1", "kp2", "kp3"} <= covered
    assert len(result.payload.questions) == 15
    backfill_call = next(call for call in provider.calls if call["purpose"] == "backfill")
    assert "还没有任何题目覆盖" in backfill_call["text"]


def test_generation_fails_cleanly_when_repair_and_backfill_both_fail(settings: Settings) -> None:
    raw = make_question_set()
    raw["questions"][0] = make_defective_question(1)
    provider = ScriptedProvider(
        [
            raw,
            LLMBadFormatError("修复失败"),
            LLMBadFormatError("补题失败"),
            LLMBadFormatError("补题再失败"),
        ]
    )

    with pytest.raises(AppError) as excinfo:
        generate_question_set(provider, _points(), settings)

    assert excinfo.value.code == "GENERATION_FAILED"


def test_unavailable_error_aborts_immediately(settings: Settings) -> None:
    provider = ScriptedProvider([LLMUnavailableError("402 余额不足")])

    with pytest.raises(AppError) as excinfo:
        generate_question_set(provider, _points(), settings)

    assert excinfo.value.code == "LLM_UNAVAILABLE"
    assert len(provider.calls) == 1


def test_assign_levels_splits_five_per_level() -> None:
    payload = GeneratedQuestionSet.model_validate(make_question_set())

    assigned = assign_levels(payload, total_levels=3, per_level=5)

    assert _level_counts(assigned) == {1: 5, 2: 5, 3: 5}


def test_merge_questions_places_backfill_into_the_right_level() -> None:
    payload = assign_levels(
        GeneratedQuestionSet.model_validate(make_question_set()), total_levels=3, per_level=5
    )
    removed = payload.questions[1]  # 第 1 关的一道题
    payload = payload.model_copy(
        update={"questions": [q for q in payload.questions if q.id != removed.id]}
    )
    backfilled = GeneratedQuestionSet.model_validate(
        {"outline": outline_points(), "questions": [make_question(301, level_seq=1)]}
    ).questions[0]

    merged = merge_questions(
        payload, [backfilled], total_levels=3, per_level=5
    )

    assert _level_counts(merged) == {1: 5, 2: 5, 3: 5}
    level_one_ids = {q.id for q in merged.questions if q.level_seq == 1}
    assert "q301" in level_one_ids


def test_build_gaps_reports_missing_questions_and_uncovered_points() -> None:
    payload = assign_levels(
        GeneratedQuestionSet.model_validate(
            {"outline": outline_points(), "questions": [make_question(1)]}
        ),
        total_levels=3,
        per_level=5,
    )

    gaps = build_gaps(payload, _points(), total_levels=3, per_level=5)

    assert any("第 1 关还缺 4 题" in gap for gap in gaps)
    assert any("kp2" in gap for gap in gaps)
