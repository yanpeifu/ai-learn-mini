"""LangChain 适配层测试：全部用假模型，零网络、零成本。"""

import logging

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel, GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.services.llm.base import (
    ChatMessage,
    LLMBadFormatError,
    LLMTimeoutError,
    LLMTransientError,
    LLMUnavailableError,
)
from app.services.llm.langchain_provider import LangChainLLMProvider, map_llm_exception


class OutlineStub(BaseModel):
    title: str
    count: int


class _StubModel:
    """长得像 chat model 的测试替身：既能返回文本，也能给出结构化输出。"""

    def __init__(
        self,
        *,
        text: str = '{"title": "货币政策", "count": 3}',
        structured_payload: object | None = None,
        raise_exc: BaseException | None = None,
        supports_structured: bool = True,
    ) -> None:
        self.text = text
        self.structured_payload = structured_payload
        self.raise_exc = raise_exc
        self.supports_structured = supports_structured
        self.invocations: list[object] = []

    def invoke(self, messages, **kwargs):  # noqa: ANN001, ANN003, ARG002
        self.invocations.append(messages)
        if self.raise_exc:
            raise self.raise_exc
        return AIMessage(content=self.text)

    def with_structured_output(self, schema, **kwargs):  # noqa: ANN001, ANN003, ARG002
        if not self.supports_structured:
            raise NotImplementedError("with_structured_output is not implemented for this model.")
        stub = self

        class _Runner:
            def invoke(self, messages, **kwargs):  # noqa: ANN001, ANN003, ARG002
                if stub.raise_exc:
                    raise stub.raise_exc
                return stub.structured_payload

        return _Runner()


class _FakeHttpError(Exception):
    def __init__(self, status_code: int, message: str = "boom") -> None:
        super().__init__(message)
        self.status_code = status_code


def _provider(model) -> LangChainLLMProvider:  # noqa: ANN001
    return LangChainLLMProvider.from_chat_model(model)


def test_chat_returns_text_and_metadata() -> None:
    provider = _provider(GenericFakeChatModel(messages=iter(["你好，我是颜宝"])))

    result = provider.chat([ChatMessage.system("s"), ChatMessage.user("u")])

    assert result.text == "你好，我是颜宝"
    assert result.provider == "fake"
    assert result.model == "fake-model"
    assert result.latency_ms >= 0


def test_chat_json_parses_plain_json() -> None:
    provider = _provider(_StubModel(supports_structured=False))

    parsed, result = provider.chat_json([ChatMessage.user("出题")], OutlineStub)

    assert parsed.title == "货币政策"
    assert parsed.count == 3
    assert result.text.startswith('{"title"')


def test_chat_json_repairs_fenced_json_with_trailing_comma() -> None:
    model = _StubModel(
        text='```json\n{"title": "行政复议", "count": 5,}\n```',
        supports_structured=False,
    )

    parsed, _ = _provider(model).chat_json([ChatMessage.user("出题")], OutlineStub)

    assert parsed.title == "行政复议"


def test_chat_json_raises_bad_format_for_garbage() -> None:
    model = _StubModel(text="这道题我出不出来。", supports_structured=False)

    with pytest.raises(LLMBadFormatError):
        _provider(model).chat_json([ChatMessage.user("出题")], OutlineStub)


def test_chat_json_raises_bad_format_when_schema_not_matched() -> None:
    model = _StubModel(text='{"title": "只有标题"}', supports_structured=False)

    with pytest.raises(LLMBadFormatError):
        _provider(model).chat_json([ChatMessage.user("出题")], OutlineStub)


def test_chat_json_uses_structured_output_when_supported() -> None:
    payload = {
        "parsed": OutlineStub(title="结构化返回", count=2),
        "raw": AIMessage(content="ignored"),
        "parsing_error": None,
    }
    model = _StubModel(structured_payload=payload)

    parsed, result = _provider(model).chat_json([ChatMessage.user("出题")], OutlineStub)

    assert parsed.title == "结构化返回"
    assert result.provider == "fake"


def test_structured_parsing_error_falls_back_to_text_repair() -> None:
    payload = {
        "parsed": None,
        "raw": AIMessage(content='```json\n{"title": "降级解析", "count": 4}\n```'),
        "parsing_error": ValueError("bad schema"),
    }
    model = _StubModel(structured_payload=payload)

    parsed, _ = _provider(model).chat_json([ChatMessage.user("出题")], OutlineStub)

    assert parsed.title == "降级解析"


def test_structured_output_not_implemented_falls_back_to_text() -> None:
    # GenericFakeChatModel 就是不支持结构化输出的真实例子
    provider = _provider(GenericFakeChatModel(messages=iter(['{"title": "假模型", "count": 1}'])))

    parsed, _ = provider.chat_json([ChatMessage.user("出题")], OutlineStub)

    assert parsed.title == "假模型"


def test_json_mode_adds_the_word_json_to_the_prompt() -> None:
    """DeepSeek 的 json_object 模式要求提示词里出现 "json"，否则直接 400。"""
    model = _StubModel(supports_structured=False)
    provider = _provider(model)

    provider.chat_json([ChatMessage.user("把这段内容拆成知识点")], OutlineStub)

    sent_text = " ".join(m.content for m in model.invocations[0])
    assert "json" in sent_text.lower()
    assert "title" in sent_text and "count" in sent_text  # schema 说明也带上了


def test_non_json_mode_does_not_add_hint() -> None:
    model = _StubModel(supports_structured=False)
    provider = LangChainLLMProvider.from_chat_model(
        model, structured_method="function_calling"
    )

    provider.chat_json([ChatMessage.user("把这段内容拆成知识点")], OutlineStub)

    sent_text = " ".join(m.content for m in model.invocations[0])
    assert "字段结构如下" not in sent_text


@pytest.mark.parametrize("status", [401, 402, 403])
def test_fatal_status_codes_abort_without_retry(status: int) -> None:
    model = _StubModel(raise_exc=_FakeHttpError(status), supports_structured=False)

    with pytest.raises(LLMUnavailableError) as excinfo:
        _provider(model).chat([ChatMessage.user("hi")])

    assert excinfo.value.retryable is False
    assert excinfo.value.code == "LLM_UNAVAILABLE"
    assert str(status) in str(excinfo.value)


def test_timeout_is_retryable() -> None:
    model = _StubModel(raise_exc=TimeoutError("Request timed out"), supports_structured=False)

    with pytest.raises(LLMTimeoutError) as excinfo:
        _provider(model).chat([ChatMessage.user("hi")])

    assert excinfo.value.retryable is True


def test_rate_limit_is_transient() -> None:
    model = _StubModel(raise_exc=_FakeHttpError(429, "rate limit exceeded"), supports_structured=False)

    with pytest.raises(LLMTransientError) as excinfo:
        _provider(model).chat([ChatMessage.user("hi")])

    assert excinfo.value.retryable is True


def test_map_llm_exception_passes_through_existing_llm_error() -> None:
    original = LLMUnavailableError("already mapped")

    assert map_llm_exception(original) is original


def test_llm_call_is_logged_with_cost_fields(caplog: pytest.LogCaptureFixture) -> None:
    provider = _provider(_StubModel(supports_structured=False))

    with caplog.at_level(logging.INFO, logger="app.llm"):
        provider.chat_json([ChatMessage.user("出题")], OutlineStub, purpose="outline")

    record = caplog.records[-1]
    assert record.provider == "fake"
    assert record.model == "fake-model"
    assert record.purpose == "outline"
    assert record.latency_ms >= 0
    assert record.success is True


def test_llm_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    model = _StubModel(raise_exc=_FakeHttpError(401), supports_structured=False)

    with caplog.at_level(logging.INFO, logger="app.llm"), pytest.raises(LLMUnavailableError):
        _provider(model).chat([ChatMessage.user("hi")])

    record = caplog.records[-1]
    assert record.success is False
    assert "401" in record.error
