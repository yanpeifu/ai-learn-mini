"""按配置装配 LLMProvider。

关于 fallback 的一个工程决定：这里用「门面级 fallback」而不是 LangChain 的
`with_fallbacks()`。原因是 `chat_model.with_fallbacks([...])` 返回的是 Runnable，
会丢掉 `with_structured_output`（结构化输出是我们解析题目 JSON 的主路径）；
而门面级 fallback 对 Mock/Fake 同样生效，也更容易单测。
"""

from __future__ import annotations

from typing import Any, Sequence, TypeVar

from pydantic import BaseModel

from app.core.config import Settings
from app.services.llm.base import (
    ChatMessage,
    LLMError,
    LLMProvider,
    LLMResult,
    LLMUsage,
    LLMUnavailableError,
)
from app.services.llm.mock import MockProvider

ModelT = TypeVar("ModelT", bound=BaseModel)


class FallbackLLMProvider:
    """主供应商失败（不可用/波动/超时）时自动切到备用供应商。"""

    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        if not providers:
            raise ValueError("FallbackLLMProvider 至少需要一个 provider")
        self.providers = list(providers)
        self.name = self.providers[0].name

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> LLMResult:
        return self._try("chat", messages, kwargs)

    def chat_json(
        self, messages: Sequence[ChatMessage], schema: type[ModelT], **kwargs: Any
    ) -> tuple[ModelT, LLMResult]:
        return self._try("chat_json", messages, kwargs, schema)

    def cost_estimate(self, usage: LLMUsage | None) -> float:
        return self.providers[0].cost_estimate(usage)

    def _try(self, method: str, messages: Sequence[ChatMessage], kwargs: dict[str, Any], schema: Any = None):
        last_error: LLMError | None = None
        for index, provider in enumerate(self.providers):
            try:
                if method == "chat":
                    return provider.chat(messages, **kwargs)
                return provider.chat_json(messages, schema, **kwargs)
            except LLMError as exc:
                last_error = exc
                is_last = index == len(self.providers) - 1
                if is_last:
                    raise
                continue
        raise last_error or LLMUnavailableError("所有模型供应商都不可用")


def build_provider(settings: Settings) -> LLMProvider:
    """按 .env 的 LLM_PROVIDER / LLM_FALLBACKS 装配；切换供应商不需要改业务代码。"""
    if settings.llm_provider == "mock":
        return MockProvider()

    from app.services.llm.langchain_provider import LangChainLLMProvider

    providers: list[LLMProvider] = [LangChainLLMProvider.from_settings(settings)]
    for fallback in settings.llm_fallback_providers:
        providers.append(LangChainLLMProvider.from_settings(settings, provider_name=fallback))
    if len(providers) == 1:
        return providers[0]
    return FallbackLLMProvider(providers)
