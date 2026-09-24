"""输入校验测试（PRD F1 的四条校验规则）。"""

import pytest

from app.core.errors import AppError
from app.core.security import (
    TEXT_SENSITIVE_MESSAGE,
    TEXT_TOO_LONG_MESSAGE,
    TEXT_TOO_SHORT_MESSAGE,
    find_sensitive_word,
    validate_raw_text,
)

VALID_TEXT = "存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例，提高准备金率会减少可放贷资金。"


def test_valid_text_is_trimmed_and_returned() -> None:
    assert validate_raw_text(f"  {VALID_TEXT}  ") == VALID_TEXT


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_text_is_rejected(text) -> None:
    with pytest.raises(AppError) as excinfo:
        validate_raw_text(text)

    assert excinfo.value.code == "INVALID_INPUT"
    assert excinfo.value.message == TEXT_TOO_SHORT_MESSAGE
    assert excinfo.value.status_code == 400


def test_too_short_text_is_rejected() -> None:
    with pytest.raises(AppError) as excinfo:
        validate_raw_text("货币政策")

    assert excinfo.value.message == TEXT_TOO_SHORT_MESSAGE


def test_too_long_text_is_rejected() -> None:
    with pytest.raises(AppError) as excinfo:
        validate_raw_text("知" * 2001)

    assert excinfo.value.message == TEXT_TOO_LONG_MESSAGE


def test_boundary_lengths_are_accepted() -> None:
    assert len(validate_raw_text("知" * 20)) == 20
    assert len(validate_raw_text("知" * 2000)) == 2000


def test_sensitive_word_is_rejected() -> None:
    with pytest.raises(AppError) as excinfo:
        validate_raw_text(VALID_TEXT + "另外给大家推荐一个赌博网站")

    assert excinfo.value.message == TEXT_SENSITIVE_MESSAGE


def test_find_sensitive_word_returns_the_hit_word() -> None:
    assert find_sensitive_word("这段文字里出现了毒品两个字") == "毒品"
    assert find_sensitive_word("这段文字很干净") is None
