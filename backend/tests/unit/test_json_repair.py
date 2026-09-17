"""JSON 修复测试：把 quality_check.py 已验证的三级降级逻辑钉死在测试里。"""

import pytest

from app.services.llm.json_repair import balance_and_close, extract_json, strip_trailing_commas


def test_plain_json() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_fenced_json_block() -> None:
    text = '```json\n{"outline": [{"id": "kp1"}]}\n```'

    assert extract_json(text) == {"outline": [{"id": "kp1"}]}


def test_json_with_surrounding_prose() -> None:
    text = '好的，这是结果：\n{"a": 1, "b": [1, 2]}\n希望对你有帮助。'

    assert extract_json(text) == {"a": 1, "b": [1, 2]}


def test_trailing_commas_are_removed() -> None:
    assert strip_trailing_commas('{"a": [1, 2,], }') == '{"a": [1, 2] }'
    assert extract_json('{"a": 1,}') == {"a": 1}


def test_truncated_json_is_repaired_by_dropping_incomplete_element() -> None:
    """截断修复的行为与 quality_check.py 完全一致：

    只保留最后一个「完整闭合」的元素边界，写了一半的那条会被丢弃
    （宁可少一道题，也不要给用户半截数据）。
    """
    text = '{"outline": [{"id": "kp1", "title": "存款准备金率"}, {"id": "kp2", "title": "公开市场操作"'

    data = extract_json(text)

    assert data["outline"][0]["title"] == "存款准备金率"
    assert len(data["outline"]) == 1


def test_truncated_inside_string_is_rejected() -> None:
    # 截断在半个字符串里，无法安全修复 —— 必须报错而不是给出错误数据
    with pytest.raises(ValueError):
        extract_json('{"title": "存款准备金率的作用机制是，提高准备金率会')


def test_empty_text_is_rejected() -> None:
    with pytest.raises(ValueError):
        extract_json("   ")


def test_non_json_garbage_is_rejected() -> None:
    with pytest.raises(ValueError):
        extract_json("我觉得这道题出得不太好，建议重写。")


def test_balance_and_close_returns_none_for_unbalanced_string() -> None:
    assert balance_and_close('{"a": "b') is None
    assert balance_and_close('{"a": [1, 2') == '{"a": [1, 2]}'
