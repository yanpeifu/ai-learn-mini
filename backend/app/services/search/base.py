"""外部资料检索门面 —— 业务代码唯一允许依赖的检索抽象。

设计约束（见本 change 的 design.md D2）：
1. 本文件不 import 任何 langchain*，保证业务层与框架解耦；
2. 业务层只拿到自研数据结构（SearchProfile / SearchHit / SearchOutcome / ExtractOutcome）；
3. 换搜索供应商 = 换实现，业务代码零改动。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

SearchDepth = Literal["basic", "advanced", "fast", "ultra-fast"]
SearchTopic = Literal["general", "news", "finance"]
TimeRange = Literal["day", "week", "month", "year"]
ExtractDepth = Literal["basic", "advanced"]

# 降级 / 失败原因（字符串常量，便于日志与断言）
REASON_NOT_CONFIGURED = "not_configured"
REASON_DISABLED = "disabled"
REASON_NOT_NEEDED = "not_needed"
REASON_NO_RESULTS = "no_results"
REASON_UNAUTHORIZED = "unauthorized"
REASON_RATE_LIMITED = "rate_limited"
REASON_TIMEOUT = "timeout"
REASON_UNAVAILABLE = "unavailable"
REASON_QUOTA = "quota_exceeded"


@dataclass(frozen=True)
class SearchProfile:
    """一次检索要用的参数画像。

    刻意分成两层（依据 langchain-tavily==0.2.18 的真实签名与源码，见 design.md）：

    - **创建期参数**：``include_raw_content`` / ``max_results`` / ``country``
      调用时再传会被工具直接拒绝（源码里有 forbidden_params 检查），
      所以「动态调整」只能靠「先决定画像 → 再创建对应工具」实现。
    - **调用期参数**：``search_depth`` / ``topic`` / ``time_range`` / ``include_domains``
      每次调用都能传，不需要进入工具实例的缓存 key。
    """

    include_raw_content: bool = False
    max_results: int = 5
    country: str | None = None
    search_depth: SearchDepth = "basic"
    topic: SearchTopic = "general"
    time_range: TimeRange | None = None
    include_domains: tuple[str, ...] = ()
    extract_depth: ExtractDepth = "basic"

    @property
    def tool_key(self) -> tuple[bool, int, str | None]:
        """工具实例的缓存 key：只包含「建工具时才能定」的参数。"""
        return (self.include_raw_content, self.max_results, self.country)


@dataclass(frozen=True)
class SearchHit:
    """一条检索结果。``raw_content`` 只有在画像要求整页正文时才有值。"""

    title: str
    url: str
    content: str
    raw_content: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class SearchOutcome:
    """一次关键词检索的结果汇总。``degraded=True`` 表示本次没拿到资料（含降级）。"""

    query: str = ""
    hits: tuple[SearchHit, ...] = ()
    credits: int | None = None
    latency_ms: int = 0
    degraded: bool = False
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.hits)


@dataclass(frozen=True)
class ExtractOutcome:
    """一次网址抽取的结果。``ok=False`` 时由上层决定如何提示用户。"""

    url: str
    text: str = ""
    credits: int | None = None
    latency_ms: int = 0
    ok: bool = False
    reason: str | None = None


@runtime_checkable
class SearchProvider(Protocol):
    """门面：业务层只调用这两个方法。"""

    name: str

    def search(self, queries: Sequence[str], profile: SearchProfile) -> SearchOutcome:
        """按关键词检索，返回汇总结果（拿不到资料时以 degraded 表达，不抛异常）。"""

    def extract(self, url: str, profile: SearchProfile) -> ExtractOutcome:
        """按网址抽取整页正文（失败时以 ok=False 表达，由上层决定是否提示用户）。"""
