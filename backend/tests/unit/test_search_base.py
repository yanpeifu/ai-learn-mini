"""检索门面测试：业务层只依赖自研接口，且该接口不引入 langchain_tavily。"""

import subprocess
import sys
from pathlib import Path

from app.services.search.base import (
    ExtractOutcome,
    SearchHit,
    SearchOutcome,
    SearchProfile,
    SearchProvider,
)


def test_profile_tool_key_only_holds_creation_time_params() -> None:
    """缓存 key 必须只含创建期参数，否则调用期参数变化会让缓存的工具"粘"住旧档位。"""
    profile = SearchProfile(
        include_raw_content=True,
        max_results=8,
        country="china",
        search_depth="advanced",
        topic="news",
        time_range="month",
        include_domains=("example.cn",),
    )

    assert profile.tool_key == (True, 8, "china")


def test_outcome_ok_reflects_hits() -> None:
    empty = SearchOutcome(query="x", degraded=True, reason="no_results")
    filled = SearchOutcome(
        query="x", hits=(SearchHit(title="t", url="https://e.com", content="c"),)
    )

    assert empty.ok is False
    assert filled.ok is True


def test_extract_outcome_defaults_to_failure() -> None:
    outcome = ExtractOutcome(url="https://e.com")

    assert outcome.ok is False
    assert outcome.text == ""


def test_protocol_is_implementable_without_langchain() -> None:
    class DummySearch:
        name = "dummy"

        def search(self, queries, profile) -> SearchOutcome:
            return SearchOutcome(query=queries[0], hits=())

        def extract(self, url, profile) -> ExtractOutcome:
            return ExtractOutcome(url=url, text="正文", ok=True)

    provider: SearchProvider = DummySearch()

    assert provider.name == "dummy"
    assert provider.extract("https://e.com", SearchProfile()).text == "正文"
    assert provider.search(["a"], SearchProfile()).query == "a"


def test_facade_does_not_import_langchain_tavily() -> None:
    """必须在独立进程里断言：同一次 pytest 运行里别的测试会加载它。"""
    backend_root = Path(__file__).resolve().parents[2]
    code = (
        "import sys;"
        "import app.services.search as facade;"
        "leaked = [n for n in sys.modules if n.startswith('langchain_tavily')];"
        "assert not leaked, leaked;"
        "print('clean')"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "clean" in result.stdout
