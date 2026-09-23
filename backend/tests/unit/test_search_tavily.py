"""Tavily 适配层测试：错误归一、失败形态、懒加载边界。全程零网络。"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.search.base import (
    REASON_NO_RESULTS,
    REASON_RATE_LIMITED,
    REASON_TIMEOUT,
    REASON_UNAUTHORIZED,
    REASON_UNAVAILABLE,
    SearchProfile,
)
from app.services.search.tavily import TavilySearchProvider, classify_error


@pytest.fixture()
def settings() -> Settings:
    return Settings(_env_file=None, tavily_api_key="tvly-test", search_max_queries=2)


@pytest.fixture(autouse=True)
def _clear_tool_cache():
    """工具实例带缓存，测试之间必须隔离。"""
    from app.services.search import tavily

    tavily._search_tool.cache_clear()
    tavily._extract_tool.cache_clear()
    yield
    tavily._search_tool.cache_clear()
    tavily._extract_tool.cache_clear()


def test_classify_http_status_codes() -> None:
    assert classify_error(ValueError("Error 401: Unauthorized")) == REASON_UNAUTHORIZED
    assert classify_error(ValueError("Error 403: Forbidden")) == REASON_UNAUTHORIZED
    assert classify_error(ValueError("Error 429: too many")) == REASON_RATE_LIMITED
    assert classify_error(ValueError("Error 432: plan limit")) == REASON_RATE_LIMITED
    assert classify_error(ValueError("Error 433: pay-as-you-go")) == REASON_RATE_LIMITED


def test_classify_timeout_empty_and_unknown() -> None:
    assert classify_error(TimeoutError("request timed out")) == REASON_TIMEOUT
    assert classify_error(ValueError("Error 500: boom")) == REASON_UNAVAILABLE
    assert classify_error(ValueError("No search results found for 'x'")) == REASON_NO_RESULTS


def test_search_degrades_on_unauthorized(settings: Settings, monkeypatch) -> None:
    provider = TavilySearchProvider(settings)

    def boom(api_key: str, query: str, profile: SearchProfile):
        raise ValueError("Error 401: Unauthorized: missing or invalid API key.")

    monkeypatch.setattr(provider, "_invoke_search", boom)

    outcome = provider.search(["harness engineering"], SearchProfile())

    assert outcome.degraded is True
    assert outcome.hits == ()
    assert outcome.reason == REASON_UNAUTHORIZED


def test_search_degrades_on_rate_limit(settings: Settings, monkeypatch) -> None:
    provider = TavilySearchProvider(settings)

    def boom(api_key: str, query: str, profile: SearchProfile):
        raise ValueError("Error 429: Your request has been blocked due to excessive requests.")

    monkeypatch.setattr(provider, "_invoke_search", boom)

    assert provider.search(["q"], SearchProfile()).reason == REASON_RATE_LIMITED


def test_tool_wrapped_error_is_detected(settings: Settings, monkeypatch) -> None:
    """真实工具会把上游异常吞成 {"error": exc} 返回，适配层必须识别出来。"""
    from langchain_tavily._utilities import TavilySearchAPIWrapper

    def fake_raw_results(self, **kwargs):
        raise ValueError("Error 429: blocked due to excessive requests")

    monkeypatch.setattr(TavilySearchAPIWrapper, "raw_results", fake_raw_results)

    outcome = TavilySearchProvider(settings).search(["q"], SearchProfile())

    assert outcome.degraded is True
    assert outcome.reason == REASON_RATE_LIMITED


def test_search_parses_hits_and_credits(settings: Settings, monkeypatch) -> None:
    from langchain_tavily._utilities import TavilySearchAPIWrapper

    def fake_raw_results(self, **kwargs):
        return {
            "results": [
                {
                    "title": "Harness Engineering 说明",
                    "url": "https://example.com/harness",
                    "content": "摘要",
                    "raw_content": "整页正文",
                    "score": 0.91,
                },
                {"title": "重复来源", "url": "https://example.com/harness", "content": "重复"},
            ],
            "usage": {"credits": 1},
        }

    monkeypatch.setattr(TavilySearchAPIWrapper, "raw_results", fake_raw_results)

    outcome = TavilySearchProvider(settings).search(["harness"], SearchProfile())

    assert outcome.ok is True
    assert len(outcome.hits) == 1  # 同一 URL 去重
    assert outcome.hits[0].raw_content == "整页正文"
    assert outcome.credits == 1


def test_extract_failure_is_reported(settings: Settings, monkeypatch) -> None:
    from langchain_tavily._utilities import TavilyExtractAPIWrapper

    def fake_raw_results(self, **kwargs):
        raise ValueError("Error 403: Forbidden")

    monkeypatch.setattr(TavilyExtractAPIWrapper, "raw_results", fake_raw_results)

    outcome = TavilySearchProvider(settings).extract("https://example.com", SearchProfile())

    assert outcome.ok is False
    assert outcome.text == ""
    assert outcome.reason == REASON_UNAUTHORIZED


def test_extract_returns_page_text(settings: Settings, monkeypatch) -> None:
    from langchain_tavily._utilities import TavilyExtractAPIWrapper

    def fake_raw_results(self, **kwargs):
        return {
            "results": [{"url": "https://example.com", "raw_content": "整页正文内容"}],
            "failed_results": [],
            "usage": {"credits": 1},
        }

    monkeypatch.setattr(TavilyExtractAPIWrapper, "raw_results", fake_raw_results)

    outcome = TavilySearchProvider(settings).extract("https://example.com", SearchProfile())

    assert outcome.ok is True
    assert outcome.text == "整页正文内容"
    assert outcome.credits == 1


def test_adapter_imports_langchain_tavily_lazily() -> None:
    code = (
        "import sys;"
        "import app.services.search.tavily as adapter;"
        "leaked = [n for n in sys.modules if n.startswith('langchain_tavily')];"
        "assert not leaked, leaked;"
        "print('lazy')"
    )
    backend_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "lazy" in result.stdout


def test_only_the_adapter_imports_langchain_tavily() -> None:
    """约束：真正 import langchain_tavily 的只有适配层这一个文件（注释不算）。"""
    import_pattern = re.compile(r"^\s*(?:from|import)\s+langchain_tavily", re.MULTILINE)
    app_root = Path(__file__).resolve().parents[2] / "app"
    offenders = [
        str(path.relative_to(app_root))
        for path in app_root.rglob("*.py")
        if import_pattern.search(path.read_text(encoding="utf-8")) and path.name != "tavily.py"
    ]

    assert offenders == []
