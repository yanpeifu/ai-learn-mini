"""画像决策测试：表驱动覆盖「简单 / 复杂 / 强时效 / 国内 / 国外」五种输入。"""

import pytest

from app.core.config import Settings
from app.services.search.profiles import KnowledgeTraits, build_profile


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        _env_file=None,
        tavily_api_key="tvly-test",
        search_max_results_min=3,
        search_max_results_max=8,
        search_country="china",
        search_preferred_domains="example.cn, example.org",
    )


def test_simple_stable_zh(settings: Settings) -> None:
    profile = build_profile(KnowledgeTraits(), settings)

    # 创建期参数
    assert profile.include_raw_content is False
    assert profile.max_results == 3
    assert profile.country == "china"
    # 调用期参数
    assert profile.search_depth == "basic"
    assert profile.topic == "general"
    assert profile.time_range is None
    assert profile.include_domains == ("example.cn", "example.org")
    assert profile.extract_depth == "basic"


def test_complex_zh_takes_deeper_and_more(settings: Settings) -> None:
    profile = build_profile(KnowledgeTraits(complexity="complex"), settings)

    assert profile.include_raw_content is True
    assert profile.max_results == 8
    assert profile.search_depth == "advanced"
    assert profile.topic == "general"
    assert profile.extract_depth == "advanced"


def test_time_sensitive_uses_news_and_limits_range(settings: Settings) -> None:
    profile = build_profile(
        KnowledgeTraits(complexity="complex", timeliness="time_sensitive"), settings
    )

    assert profile.topic == "news"
    assert profile.time_range == "month"
    # country 只在 topic=general 时合法，news 下必须清空
    assert profile.country is None


def test_foreign_locale_drops_zh_biases(settings: Settings) -> None:
    profile = build_profile(KnowledgeTraits(locale="other"), settings)

    assert profile.country is None
    assert profile.include_domains == ()


def test_simple_and_complex_differ_in_expected_fields(settings: Settings) -> None:
    simple = build_profile(KnowledgeTraits(), settings)
    complex_ = build_profile(KnowledgeTraits(complexity="complex"), settings)

    assert simple.tool_key != complex_.tool_key
    assert simple.search_depth == "basic"
    assert complex_.search_depth == "advanced"
