"""LLM 门面接口测试：业务层只依赖自研接口，且该接口不引入 langchain。"""

import sys

import pytest
from app.services.llm.base import (
    ChatMessage,
    LLMBadFormatError,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    LLMUsage,
    estimate_cost,
)


def test_chat_message_helpers() -> None:
    assert ChatMessage.system("s").role == "system"
    assert ChatMessage.user("u").role == "user"
    assert ChatMessage.assistant("a").role == "assistant"
    assert ChatMessage.user("你好").content == "你好"


def test_usage_total_tokens() -> None:
    usage = LLMUsage(prompt_tokens=600, completion_tokens=3500)

    assert usage.total_tokens == 4100


def test_estimate_cost_uses_input_output_prices() -> None:
    usage = LLMUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000)

    cost = estimate_cost(usage, input_price_per_million=1.0, output_price_per_million=4.0)

    assert cost == pytest.approx(5.0)


def test_error_taxonomy_marks_fatal_and_retryable() -> None:
    assert issubclass(LLMUnavailableError, LLMError)
    assert issubclass(LLMTimeoutError, LLMError)
    assert issubclass(LLMBadFormatError, LLMError)

    # 401/402/403 这类问题重试没有意义，必须立即中止
    assert LLMUnavailableError("boom").retryable is False
    assert LLMTimeoutError("slow").retryable is True
    assert LLMBadFormatError("bad json").retryable is True


def test_protocol_is_implementable_without_langchain() -> None:
    from app.services.llm.base import LLMProvider, LLMResult

    class DummyProvider:
        name = "dummy"

        def chat(self, messages, **kwargs) -> LLMResult:
            return LLMResult(
                text="hi",
                provider=self.name,
                model="dummy-1",
                latency_ms=1,
                usage=None,
            )

        def chat_json(self, messages, schema, **kwargs):
            raise NotImplementedError

        def cost_estimate(self, usage: LLMUsage) -> float:
            return 0.0

    provider: LLMProvider = DummyProvider()

    assert provider.name == "dummy"
    assert provider.chat([ChatMessage.user("hi")]).text == "hi"


def test_base_module_does_not_import_langchain() -> None:
    """约束②：业务代码不 import langchain，框架只允许出现在 adapter 层。"""
    import app.services.llm.base  # noqa: F401

    assert not [name for name in sys.modules if name.startswith("langchain")]
