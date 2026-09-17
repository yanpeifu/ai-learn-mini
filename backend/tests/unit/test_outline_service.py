"""大纲生成服务测试：输入校验、重试策略、致命错误立即中止。"""

import pytest
from app.core.config import Settings
from app.core.errors import AppError
from app.services.llm.base import (
    LLMBadFormatError,
    LLMTimeoutError,
    LLMTransientError,
    LLMUnavailableError,
)
from app.services.outline_service import generate_outline
from tests.fakes import ScriptedProvider, outline_payload

VALID_TEXT = "存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例，提高准备金率会减少可放贷资金。"


def test_generates_outline_on_first_attempt(settings: Settings) -> None:
    provider = ScriptedProvider([outline_payload()])

    result = generate_outline(provider, VALID_TEXT, settings)

    assert [point.id for point in result.payload.points] == ["kp1", "kp2", "kp3"]
    assert result.payload.title == "货币政策三大工具"
    assert result.attempts == 1
    assert len(provider.calls) == 1
    assert provider.calls[0]["purpose"] == "outline"


def test_invalid_input_is_rejected_without_calling_the_model(settings: Settings) -> None:
    provider = ScriptedProvider([outline_payload()])

    with pytest.raises(AppError) as excinfo:
        generate_outline(provider, "太短了", settings)

    assert excinfo.value.code == "INVALID_INPUT"
    assert provider.calls == []


@pytest.mark.parametrize(
    "error",
    [
        LLMBadFormatError("模型返回损坏的 JSON"),
        LLMTimeoutError("模型超时"),
        LLMTransientError("429"),
    ],
)
def test_retryable_errors_are_retried_then_succeed(settings: Settings, error: Exception) -> None:
    provider = ScriptedProvider([error, outline_payload()])

    result = generate_outline(provider, VALID_TEXT, settings)

    assert result.attempts == 2
    assert len(provider.calls) == 2


def test_retry_exhausted_returns_bad_format_error(settings: Settings) -> None:
    provider = ScriptedProvider([LLMBadFormatError("坏 JSON")] * 3)

    with pytest.raises(AppError) as excinfo:
        generate_outline(provider, VALID_TEXT, settings)

    assert excinfo.value.code == "LLM_BAD_FORMAT"
    assert len(provider.calls) == settings.llm_max_retries + 1


def test_retry_exhausted_on_timeout_returns_timeout_error(settings: Settings) -> None:
    provider = ScriptedProvider([LLMTimeoutError("超时")] * 3)

    with pytest.raises(AppError) as excinfo:
        generate_outline(provider, VALID_TEXT, settings)

    assert excinfo.value.code == "LLM_TIMEOUT"


def test_retry_exhausted_on_transient_returns_generation_failed(settings: Settings) -> None:
    provider = ScriptedProvider([LLMTransientError("503")] * 3)

    with pytest.raises(AppError) as excinfo:
        generate_outline(provider, VALID_TEXT, settings)

    assert excinfo.value.code == "GENERATION_FAILED"


def test_unavailable_aborts_immediately_without_retry(settings: Settings) -> None:
    provider = ScriptedProvider([LLMUnavailableError("401 未授权"), outline_payload()])

    with pytest.raises(AppError) as excinfo:
        generate_outline(provider, VALID_TEXT, settings)

    assert excinfo.value.code == "LLM_UNAVAILABLE"
    assert excinfo.value.message == "服务暂时不可用，请稍后再试"  # 不暴露 401 等技术细节
    assert len(provider.calls) == 1  # 只调用一次，没有重试
