"""取资料链路测试：降级、限额、日志（tasks 3.4、4.5）。"""

import logging

import pytest

from app.core.config import Settings
from app.services.quota import record_search_usage, reset_search_usage, search_used_today
from app.services.search.base import REASON_QUOTA, SearchHit
from app.services.search.grounding import gather_references, trim_references
from app.services.search.mock import MockSearchProvider
from app.services.search.profiles import KnowledgeTraits

HITS = [SearchHit(title="资料", url="https://e.com/a", content="摘要")]


@pytest.fixture(autouse=True)
def _reset_usage():
    reset_search_usage()
    yield
    reset_search_usage()


@pytest.fixture()
def search_settings() -> Settings:
    return Settings(_env_file=None, tavily_api_key="tvly-test", daily_search_quota=2)


def test_gather_references_returns_hits(search_settings: Settings) -> None:
    provider = MockSearchProvider(hits=HITS)

    result = gather_references(
        provider,
        queries=["harness engineering"],
        traits=KnowledgeTraits(complexity="complex"),
        settings=search_settings,
        user_id=1,
    )

    assert result.ok is True
    assert result.references[0].url == "https://e.com/a"
    assert search_used_today(1) == 1


def test_keyword_failure_degrades_without_raising(search_settings: Settings) -> None:
    provider = MockSearchProvider(search_reason="rate_limited")

    result = gather_references(
        provider,
        queries=["q"],
        traits=KnowledgeTraits(),
        settings=search_settings,
        user_id=1,
    )

    assert result.ok is False
    assert result.reason == "rate_limited"


def test_search_disabled_never_calls_provider() -> None:
    provider = MockSearchProvider(hits=HITS)
    settings = Settings(_env_file=None)  # 没有 Key → 等效关闭

    result = gather_references(
        provider, queries=["q"], traits=KnowledgeTraits(), settings=settings, user_id=1
    )

    assert result.reason == "disabled"
    assert provider.calls == []


def test_daily_quota_stops_further_searches(search_settings: Settings) -> None:
    provider = MockSearchProvider(hits=HITS)
    limited = search_settings.model_copy(update={"daily_search_quota": 1})

    first = gather_references(
        provider, queries=["q"], traits=KnowledgeTraits(), settings=limited, user_id=1
    )
    second = gather_references(
        provider, queries=["q"], traits=KnowledgeTraits(), settings=limited, user_id=1
    )

    assert first.ok is True
    assert second.ok is False
    assert second.reason == REASON_QUOTA
    assert len(provider.calls) == 1  # 达到上限后不再发起检索


def test_quota_is_per_user(search_settings: Settings) -> None:
    provider = MockSearchProvider(hits=HITS)
    limited = search_settings.model_copy(update={"daily_search_quota": 1})

    gather_references(
        provider, queries=["q"], traits=KnowledgeTraits(), settings=limited, user_id=1
    )
    other = gather_references(
        provider, queries=["q"], traits=KnowledgeTraits(), settings=limited, user_id=2
    )

    assert other.ok is True
    assert search_used_today(1) == 1
    assert search_used_today(2) == 1


def test_search_is_logged_with_credits_and_sources(search_settings: Settings) -> None:
    """直接挂一个 handler 收日志：caplog 会受全局日志配置（propagate=False）影响。"""
    records: list[logging.LogRecord] = []

    class _Catcher(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("app.search")
    handler = _Catcher()
    # configure_logging() 里用的是 dictConfig(disable_existing_loggers=True)，
    # 应用初始化之后这个 logger 可能处于 disabled 状态，这里临时开启。
    was_disabled = logger.disabled
    logger.disabled = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        provider = MockSearchProvider(hits=HITS, credits=2)
        gather_references(
            provider,
            queries=["q"],
            traits=KnowledgeTraits(),
            settings=search_settings,
            user_id=1,
        )
    finally:
        logger.removeHandler(handler)
        logger.disabled = was_disabled

    matched = [record for record in records if getattr(record, "credits", None) == 2]
    assert matched, "检索日志里应当记录 credits"
    assert matched[0].sources == ["https://e.com/a"]
    assert matched[0].hits == 1


def test_trim_references_respects_budget() -> None:
    hits = [
        SearchHit(title="A", url="https://a.com", content="a" * 10, raw_content="x" * 30),
        SearchHit(title="B", url="https://b.com", content="b" * 10),
    ]

    kept, trimmed = trim_references(hits, 20)

    assert trimmed is True
    assert len(kept) == 1
    assert len(kept[0].content) == 20


def test_record_and_reset_usage() -> None:
    record_search_usage(9, 3)

    assert search_used_today(9) == 3
