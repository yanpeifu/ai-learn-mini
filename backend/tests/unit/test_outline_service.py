"""大纲生成服务测试：输入校验、重试策略、致命错误立即中止，以及联网取资料的分支。"""

import pytest
from app.core.config import Settings
from app.core.errors import AppError
from app.services.llm.base import (
    LLMBadFormatError,
    LLMTimeoutError,
    LLMTransientError,
    LLMUnavailableError,
)
from app.services.outline_service import (
    UNVERIFIED_MARK,
    URL_READING_OFF_MESSAGE,
    URL_UNREADABLE_MESSAGE,
    generate_outline,
)
from app.services.search.base import REASON_NOT_NEEDED, SearchHit
from app.services.search.mock import MockSearchProvider, NoopSearchProvider
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


# --------------------------------------------------------------------------- #
# 联网取资料（tasks 3.2 / 3.3 / 4.2 / 4.3）
# --------------------------------------------------------------------------- #


@pytest.fixture()
def search_settings(settings: Settings) -> Settings:
    """带 Key 的配置：否则检索会被判定为「未配置」而直接跳过。"""
    return settings.model_copy(update={"tavily_api_key": "tvly-test"})


def _payload_needing_reference() -> dict:
    return outline_payload() | {
        "needs_external_reference": True,
        "search_queries": ["harness engineering"],
        "complexity": "complex",
    }


LONG_PAGE = "这是从网页抓下来的正文。" * 400  # 远超 2000 字


def test_url_input_reads_page_and_skips_char_limit(search_settings: Settings) -> None:
    provider = ScriptedProvider([outline_payload()])
    search = MockSearchProvider(extracted_text=LONG_PAGE)

    result = generate_outline(
        provider, "https://example.com/post", search_settings, search=search, user_id=1
    )

    assert result.source_url == "https://example.com/post"
    assert "这是从网页抓下来的正文" in provider.calls[0]["text"]
    assert search.calls[0]["kind"] == "extract"


def test_url_with_extra_text_keeps_user_note(search_settings: Settings) -> None:
    provider = ScriptedProvider([outline_payload()])
    search = MockSearchProvider(extracted_text="网页正文内容")

    generate_outline(
        provider,
        "重点看第三章 https://example.com/post",
        search_settings,
        search=search,
        user_id=1,
    )

    assert "重点看第三章" in provider.calls[0]["text"]
    assert "网页正文内容" in provider.calls[0]["text"]


def test_url_extract_failure_is_user_visible(search_settings: Settings) -> None:
    provider = ScriptedProvider([outline_payload()])
    search = MockSearchProvider(extract_reason="unauthorized")

    with pytest.raises(AppError) as excinfo:
        generate_outline(
            provider, "https://example.com/post", search_settings, search=search, user_id=1
        )

    assert excinfo.value.code == "INVALID_INPUT"
    assert excinfo.value.message == URL_UNREADABLE_MESSAGE
    assert provider.calls == []  # 没拿到正文就不该浪费一次模型调用


def test_url_input_when_reading_disabled_asks_for_text(search_settings: Settings) -> None:
    provider = ScriptedProvider([outline_payload()])

    with pytest.raises(AppError) as excinfo:
        generate_outline(
            provider,
            "https://example.com/post",
            search_settings,
            search=NoopSearchProvider(),
            user_id=1,
        )

    assert excinfo.value.message == URL_READING_OFF_MESSAGE


def test_outline_uses_references_when_model_asks_for_them(
    search_settings: Settings,
) -> None:
    provider = ScriptedProvider([_payload_needing_reference(), outline_payload()])
    search = MockSearchProvider(
        hits=[SearchHit(title="官方文档", url="https://e.com/harness", content="摘要")]
    )

    result = generate_outline(provider, VALID_TEXT, search_settings, search=search, user_id=1)

    assert result.grounding is not None and result.grounding.ok is True
    assert UNVERIFIED_MARK not in result.payload.points[0].summary
    assert provider.calls[1]["purpose"] == "outline_grounded"
    assert "https://e.com/harness" in provider.calls[1]["text"]


def test_reference_fields_are_parsed_both_ways(search_settings: Settings) -> None:
    provider = ScriptedProvider([_payload_needing_reference(), outline_payload()])
    search = MockSearchProvider(
        hits=[SearchHit(title="官方文档", url="https://e.com/harness", content="摘要")]
    )

    generate_outline(provider, VALID_TEXT, search_settings, search=search, user_id=1)

    first_prompt = provider.calls[0]["text"]
    assert "needs_external_reference" in first_prompt  # 提示词确实要求了这些字段
    assert search.calls[0]["queries"] == ["harness engineering"]


def test_outline_is_marked_unverified_when_search_fails(
    search_settings: Settings,
) -> None:
    provider = ScriptedProvider([_payload_needing_reference()])
    search = MockSearchProvider(search_reason="rate_limited")

    result = generate_outline(provider, VALID_TEXT, search_settings, search=search, user_id=1)

    assert result.grounding is not None and result.grounding.ok is False
    assert UNVERIFIED_MARK in result.payload.points[0].summary
    assert len(provider.calls) == 1  # 没资料就不重跑


def test_outline_skips_search_when_model_says_not_needed(
    search_settings: Settings,
) -> None:
    provider = ScriptedProvider([outline_payload()])
    search = MockSearchProvider(hits=[SearchHit(title="t", url="https://e.com", content="c")])

    result = generate_outline(provider, VALID_TEXT, search_settings, search=search, user_id=1)

    assert result.grounding is not None
    assert result.grounding.reason == REASON_NOT_NEEDED
    assert search.calls == []
    assert UNVERIFIED_MARK in result.payload.points[0].summary


def test_grounded_call_failure_falls_back_to_first_outline(
    search_settings: Settings,
) -> None:
    # 第一次成功；带资料那次连续 3 次都坏 JSON（= 重试次数用尽）
    provider = ScriptedProvider(
        [_payload_needing_reference()] + [LLMBadFormatError("坏 JSON")] * 3
    )
    search = MockSearchProvider(
        hits=[SearchHit(title="官方文档", url="https://e.com/harness", content="摘要")]
    )

    result = generate_outline(provider, VALID_TEXT, search_settings, search=search, user_id=1)

    # 第一次调用已经有可用大纲，带资料那次失败就退回它并标注未核实
    assert result.payload.points
    assert UNVERIFIED_MARK in result.payload.points[0].summary
