"""离线实现测试：假实现能替换 provider，业务代码在无网络下可跑通。"""

from app.core.config import Settings
from app.services.search.base import (
    REASON_DISABLED,
    REASON_NO_RESULTS,
    SearchHit,
    SearchOutcome,
    SearchProfile,
    SearchProvider,
)
from app.services.search.factory import build_search_provider
from app.services.search.mock import MockSearchProvider, NoopSearchProvider


def test_noop_provider_returns_no_material() -> None:
    provider = NoopSearchProvider()

    search = provider.search(["任何关键词"], SearchProfile())
    extract = provider.extract("https://example.com", SearchProfile())

    assert search.degraded is True
    assert search.reason == REASON_DISABLED
    assert extract.ok is False
    assert extract.reason == REASON_DISABLED


def test_mock_provider_walks_both_paths() -> None:
    provider = MockSearchProvider(
        hits=[SearchHit(title="新工具文档", url="https://e.com/a", content="摘要")],
        extracted_text="整页正文",
    )

    search = provider.search(["harness engineering"], SearchProfile())
    extract = provider.extract("https://e.com/a", SearchProfile())

    assert search.ok is True
    assert search.hits[0].url == "https://e.com/a"
    assert extract.ok is True
    assert extract.text == "整页正文"
    assert [call["kind"] for call in provider.calls] == ["search", "extract"]


def test_mock_provider_can_simulate_degradation() -> None:
    provider = MockSearchProvider(search_reason="rate_limited", extract_reason="timeout")

    assert provider.search(["q"], SearchProfile()).reason == "rate_limited"
    assert provider.extract("https://e.com", SearchProfile()).reason == "timeout"


def test_empty_extract_text_is_reported_as_no_results() -> None:
    provider = MockSearchProvider(extracted_text="")

    outcome = provider.extract("https://e.com", SearchProfile())

    assert outcome.ok is False
    assert outcome.reason == REASON_NO_RESULTS


def test_business_layer_works_with_a_fake_provider() -> None:
    """业务代码只认门面接口，因此离线也能跑通。"""

    def collect(provider: SearchProvider, queries: list[str]) -> SearchOutcome:
        return provider.search(queries, SearchProfile())

    fake = MockSearchProvider(hits=[SearchHit(title="t", url="https://e.com", content="c")])

    assert collect(fake, ["q"]).ok is True


def test_factory_returns_noop_when_key_missing() -> None:
    assert build_search_provider(Settings(_env_file=None)).name == "noop"


def test_factory_returns_noop_when_disabled() -> None:
    settings = Settings(_env_file=None, tavily_api_key="tvly-test", search_mode="off")

    assert build_search_provider(settings).name == "noop"


def test_factory_returns_tavily_when_configured() -> None:
    settings = Settings(_env_file=None, tavily_api_key="tvly-test", search_mode="auto")

    assert build_search_provider(settings).name == "tavily"
