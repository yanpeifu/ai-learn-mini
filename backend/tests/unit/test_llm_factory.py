"""供应商装配与 fallback 测试：切换 DeepSeek / 百炼 / 火山 只改配置，不动代码。"""

import json

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.services.llm.base import (
    ChatMessage,
    LLMBadFormatError,
    LLMResult,
    LLMTransientError,
    LLMUnavailableError,
)
from app.services.llm.factory import FallbackLLMProvider, build_provider
from app.services.llm.mock import MockProvider


class OutlineStub(BaseModel):
    title: str


def test_build_provider_returns_mock_when_configured(settings: Settings) -> None:
    provider = build_provider(settings)

    assert isinstance(provider, MockProvider)
    assert provider.name == "mock"


def test_build_provider_requires_api_key_for_real_provider(settings: Settings) -> None:
    real = settings.model_copy(update={"llm_provider": "deepseek", "llm_api_key": None})

    with pytest.raises(LLMUnavailableError) as excinfo:
        build_provider(real)

    assert "API Key" in str(excinfo.value)


def test_build_provider_builds_langchain_provider_for_deepseek(settings: Settings) -> None:
    real = settings.model_copy(update={"llm_provider": "deepseek", "llm_api_key": "sk-test"})

    provider = build_provider(real)

    assert provider.name == "deepseek"
    assert getattr(provider, "model_id", None) == "deepseek-chat"


def test_build_provider_supports_bailian_and_fallbacks(settings: Settings) -> None:
    real = settings.model_copy(
        update={
            "llm_provider": "bailian",
            "bailian_api_key": "sk-bailian",
            "volcengine_api_key": "sk-volc",
            "llm_fallbacks": "volcengine",
        }
    )

    provider = build_provider(real)

    assert isinstance(provider, FallbackLLMProvider)
    assert [p.name for p in provider.providers] == ["bailian", "volcengine"]
    assert provider.providers[0].model_id == real.bailian_model


def _result(text: str = "ok") -> LLMResult:
    return LLMResult(text=text, provider="stub", model="stub-1", latency_ms=1)


class _StubProvider:
    def __init__(self, name: str, *, error: Exception | None = None) -> None:
        self.name = name
        self.error = error

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003, ARG002
        if self.error:
            raise self.error
        return _result()

    def chat_json(self, messages, schema, **kwargs):  # noqa: ANN001, ANN003, ARG002
        if self.error:
            raise self.error
        return schema(title=f"from-{self.name}"), _result()

    def cost_estimate(self, usage):  # noqa: ANN001, ARG002
        return 0.0


def test_fallback_uses_secondary_provider_on_failure() -> None:
    primary = _StubProvider("primary", error=LLMUnavailableError("401"))
    secondary = _StubProvider("secondary")
    provider = FallbackLLMProvider([primary, secondary])

    parsed, _ = provider.chat_json([ChatMessage.user("hi")], OutlineStub)

    assert parsed.title == "from-secondary"
    assert provider.name == "primary"


def test_fallback_keeps_trying_on_transient_error() -> None:
    providers = [
        _StubProvider("a", error=LLMTransientError("429")),
        _StubProvider("b", error=LLMTransientError("503")),
        _StubProvider("c"),
    ]

    parsed, _ = FallbackLLMProvider(providers).chat_json([ChatMessage.user("hi")], OutlineStub)

    assert parsed.title == "from-c"


def test_fallback_raises_last_error_when_all_fail() -> None:
    providers = [
        _StubProvider("a", error=LLMUnavailableError("401")),
        _StubProvider("b", error=LLMUnavailableError("402")),
    ]

    with pytest.raises(LLMUnavailableError) as excinfo:
        FallbackLLMProvider(providers).chat([ChatMessage.user("hi")])

    assert "402" in str(excinfo.value)


def test_fallback_requires_at_least_one_provider() -> None:
    with pytest.raises(ValueError):
        FallbackLLMProvider([])


def test_mock_provider_reads_fixture_dir(tmp_path) -> None:
    (tmp_path / "OutlineStub.json").write_text(
        json.dumps({"title": "夹具大纲"}, ensure_ascii=False), encoding="utf-8"
    )
    provider = MockProvider.from_fixture_dir(tmp_path)

    parsed, _ = provider.chat_json([ChatMessage.user("hi")], OutlineStub)

    assert parsed.title == "夹具大纲"
    assert provider.cost_estimate(None) == 0.0
    assert provider.calls[0]["schema"] == "OutlineStub"


def test_mock_provider_without_fixture_raises_bad_format() -> None:
    with pytest.raises(LLMBadFormatError):
        MockProvider().chat_json([ChatMessage.user("hi")], OutlineStub)
