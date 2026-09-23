"""Tavily 适配层 —— 本项目里**唯一**允许 import langchain_tavily 的文件。

为什么写得这么小心（依据 langchain-tavily==0.2.18 的源码实测）：

1. ``max_results`` / ``include_raw_content`` / ``country`` / ``include_usage`` 是**创建期**参数，
   调用时再传会被工具直接拒绝（源码里有 forbidden_params 检查）。
2. ``search_depth`` / ``topic`` / ``time_range`` / ``include_domains`` 调用时能传，
   **但如果创建工具时也设了，实例值会覆盖调用值** —— 所以这里刻意不在实例上设它们，
   否则缓存复用会让上一次的档位"粘"到下一次。
3. 工具**不会在上游报错时抛异常**：``_run`` 会把 HTTP 错误吞成 ``{"error": exc}`` 返回，
   只有"搜不到结果"才抛 ``ToolException``。
   所以这里同时处理「返回 dict 里带 error」「直接抛异常」两种失败形态。
4. API Key 通过 ``TavilySearch(tavily_api_key=...)`` 显式传入，不去污染 os.environ。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from app.core.config import Settings
from app.services.search.base import (
    REASON_NO_RESULTS,
    REASON_RATE_LIMITED,
    REASON_TIMEOUT,
    REASON_UNAUTHORIZED,
    REASON_UNAVAILABLE,
    ExtractOutcome,
    SearchHit,
    SearchOutcome,
    SearchProfile,
)

logger = logging.getLogger("app.search")

_STATUS_TO_REASON = {
    "401": REASON_UNAUTHORIZED,
    "402": REASON_UNAUTHORIZED,
    "403": REASON_UNAUTHORIZED,
    "429": REASON_RATE_LIMITED,
    "432": REASON_RATE_LIMITED,
    "433": REASON_RATE_LIMITED,
}
_STATUS_PATTERN = re.compile(r"Error (\d{3})")
_EMPTY_MARKERS = ("No search results found", "No extracted results found")


def classify_error(exc: BaseException) -> str:
    """把上游异常归一到我们的原因码（供日志与降级判断使用）。"""
    message = str(exc)
    if any(marker in message for marker in _EMPTY_MARKERS):
        return REASON_NO_RESULTS
    match = _STATUS_PATTERN.search(message)
    if match:
        return _STATUS_TO_REASON.get(match.group(1), REASON_UNAVAILABLE)
    lower_name = type(exc).__name__.lower()
    if "timeout" in lower_name or "timed out" in message.lower():
        return REASON_TIMEOUT
    return REASON_UNAVAILABLE


def _raise_if_wrapped_error(raw: Any) -> None:
    """工具的 _run 会把上游异常吞进 {"error": exc} 返回，这里把它还原成异常。"""
    if isinstance(raw, dict) and raw.get("error"):
        error = raw["error"]
        raise error if isinstance(error, BaseException) else RuntimeError(str(error))
    if isinstance(raw, str):
        # handle_tool_error=False 时理论上不会有这种返回值，兜底当作失败处理
        raise RuntimeError(raw)


@lru_cache(maxsize=32)
def _search_tool(
    api_key: str,
    include_raw_content: bool,
    max_results: int,
    country: str | None,
) -> Any:
    """按创建期参数缓存工具实例：同一画像只构造一次。

    注意：这里**不设** search_depth / topic / time_range / include_domains ——
    它们在实例上会被当成默认值覆盖调用值，破坏「按需动态」。
    """
    from langchain_tavily import TavilySearch

    return TavilySearch(
        tavily_api_key=api_key,
        include_raw_content=include_raw_content,
        max_results=max_results,
        country=country,
        include_usage=True,  # 为了能记录本次消耗的 credits（创建期参数）
        handle_tool_error=False,  # 让「搜不到结果」以异常形式冒出来，便于统一分类
    )


@lru_cache(maxsize=4)
def _extract_tool(api_key: str) -> Any:
    from langchain_tavily import TavilyExtract

    return TavilyExtract(
        tavily_api_key=api_key,
        include_usage=True,
        handle_tool_error=False,
    )


def _credits_of(raw: dict[str, Any]) -> int | None:
    usage = raw.get("usage")
    if isinstance(usage, dict):
        credits = usage.get("credits")
        return credits if isinstance(credits, int) else None
    return None


def _hits_of(raw: dict[str, Any]) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for item in raw.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        hits.append(
            SearchHit(
                title=str(item.get("title") or "").strip(),
                url=url,
                content=str(item.get("content") or "").strip(),
                raw_content=(
                    str(item["raw_content"]).strip() if item.get("raw_content") else None
                ),
                score=item.get("score") if isinstance(item.get("score"), float) else None,
            )
        )
    return hits


class TavilySearchProvider:
    """基于 LangChain 官方 Tavily 集成的检索实现。"""

    name = "tavily"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------ #
    # 关键词检索
    # ------------------------------------------------------------------ #
    def search(self, queries: Sequence[str], profile: SearchProfile) -> SearchOutcome:
        started = time.monotonic()
        api_key = self._api_key()
        hits: list[SearchHit] = []
        credits: int | None = None
        seen: set[str] = set()
        first_query = ""
        reason: str | None = None

        for query in list(queries)[: self._settings.search_max_queries]:
            cleaned = query.strip()
            if not cleaned:
                continue
            first_query = first_query or cleaned
            try:
                raw = self._invoke_search(api_key, cleaned, profile)
            except BaseException as exc:  # noqa: BLE001 - 上游异常形态多样，统一归一
                reason = classify_error(exc)
                logger.info(
                    "本次联网检索没成功，按无资料继续",
                    extra={
                        "kind": "search",
                        "reason": reason,
                        "error_type": type(exc).__name__,
                    },
                )
                break

            found = _hits_of(raw)
            credits = _credits_of(raw) if credits is None else credits
            for hit in found:
                if hit.url in seen:
                    continue
                seen.add(hit.url)
                hits.append(hit)

        latency_ms = int((time.monotonic() - started) * 1000)
        if not hits and reason is None:
            reason = REASON_NO_RESULTS
        return SearchOutcome(
            query=first_query,
            hits=tuple(hits),
            credits=credits,
            latency_ms=latency_ms,
            degraded=not hits,
            reason=reason,
        )

    def _invoke_search(self, api_key: str, query: str, profile: SearchProfile) -> dict[str, Any]:
        tool = _search_tool(
            api_key, profile.include_raw_content, profile.max_results, profile.country
        )
        payload: dict[str, Any] = {
            "query": query,
            "search_depth": profile.search_depth,
            "topic": profile.topic,
        }
        if profile.time_range:
            payload["time_range"] = profile.time_range
        if profile.include_domains:
            payload["include_domains"] = list(profile.include_domains)

        raw = tool.invoke(payload)
        _raise_if_wrapped_error(raw)
        if not isinstance(raw, dict):
            raise RuntimeError(f"检索返回了预期之外的类型：{type(raw).__name__}")
        return raw

    # ------------------------------------------------------------------ #
    # 网址抽取
    # ------------------------------------------------------------------ #
    def extract(self, url: str, profile: SearchProfile) -> ExtractOutcome:
        started = time.monotonic()
        try:
            raw = self._invoke_extract(self._api_key(), url, profile)
        except BaseException as exc:  # noqa: BLE001
            reason = classify_error(exc)
            logger.info(
                "按网址抽取正文失败",
                extra={"kind": "extract", "reason": reason, "error_type": type(exc).__name__},
            )
            return ExtractOutcome(
                url=url,
                ok=False,
                reason=reason,
                latency_ms=int((time.monotonic() - started) * 1000),
            )

        text = ""
        for item in raw.get("results") or []:
            if isinstance(item, dict):
                text = str(item.get("raw_content") or item.get("content") or "").strip()
                if text:
                    break
        return ExtractOutcome(
            url=url,
            text=text,
            ok=bool(text),
            reason=None if text else REASON_NO_RESULTS,
            credits=_credits_of(raw),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def _invoke_extract(self, api_key: str, url: str, profile: SearchProfile) -> dict[str, Any]:
        tool = _extract_tool(api_key)
        raw = tool.invoke({"urls": [url], "extract_depth": profile.extract_depth})
        _raise_if_wrapped_error(raw)
        if not isinstance(raw, dict):
            raise RuntimeError(f"抽取返回了预期之外的类型：{type(raw).__name__}")
        return raw

    # ------------------------------------------------------------------ #
    def _api_key(self) -> str:
        key = (self._settings.tavily_api_key or "").strip()
        if not key:
            # 正常情况下 factory 不会装配本实现；这里只是防呆
            raise RuntimeError("未配置 TAVILY_API_KEY")
        return key
