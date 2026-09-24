"""结构化输出的容错测试：单题不合法不能拖垮整批 15 题。"""

from app.schemas.generation import (
    GeneratedQuestionSet,
    clamp_difficulty,
    normalize_question_type,
    salvage_questions,
)
from app.schemas.repair import QuestionListPayload
from tests.fakes import make_question_set, outline_points


def _raw_question(index: int = 1, **overrides) -> dict:
    question = make_question_set()["questions"][index - 1]
    question.update(overrides)
    return question


def test_normal_type_aliases() -> None:
    assert normalize_question_type("单选题") == "single"
    assert normalize_question_type("multiple_choice") == "multiple_choice"  # 未知别名保持原样，由校验器拒绝
    assert normalize_question_type("judge") == "judge"


def test_difficulty_is_clamped_instead_of_rejected() -> None:
    assert clamp_difficulty(7) == 5
    assert clamp_difficulty(0) == 1
    assert clamp_difficulty("4") == 4
    assert clamp_difficulty(None) == 3


def test_level_seq_out_of_range_is_accepted() -> None:
    payload = GeneratedQuestionSet.model_validate(
        {"outline": outline_points(), "questions": [_raw_question(1, level_seq=4)]}
    )

    assert payload.questions[0].level_seq == 4  # 出题服务会按顺序重新分配关卡


def test_difficulty_and_type_are_normalized() -> None:
    payload = GeneratedQuestionSet.model_validate(
        {
            "outline": outline_points(),
            "questions": [_raw_question(1, difficulty=9, type="单选题")],
        }
    )

    assert payload.questions[0].difficulty == 5
    assert payload.questions[0].type == "single"


def test_broken_question_is_dropped_and_others_survive() -> None:
    raw = make_question_set()
    broken = dict(raw["questions"][2])
    broken.pop("options")  # 完全坏掉的一题

    payload = GeneratedQuestionSet.model_validate(
        {"outline": outline_points(), "questions": [raw["questions"][0], broken, raw["questions"][3]]}
    )

    assert len(payload.questions) == 2
    assert [q.id for q in payload.questions] == [raw["questions"][0]["id"], raw["questions"][3]["id"]]


def test_missing_outline_is_tolerated() -> None:
    payload = GeneratedQuestionSet.model_validate({"questions": [_raw_question(1)]})

    assert payload.outline == []
    assert len(payload.questions) == 1


def test_repair_payload_also_salvages() -> None:
    raw = make_question_set()
    broken = dict(raw["questions"][1])
    broken.pop("stem")

    payload = QuestionListPayload.model_validate({"questions": [raw["questions"][0], broken]})

    assert len(payload.questions) == 1


def test_salvage_questions_returns_empty_for_all_broken() -> None:
    assert salvage_questions([{"id": "x"}, {"foo": "bar"}]) == []
