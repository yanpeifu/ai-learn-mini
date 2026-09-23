"""离线实现：检索被关闭时的空实现，以及供开发/测试用的假实现。全程零网络。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.services.search.base import (
    REASON_DISABLED,
    REASON_NO_RESULTS,
    ExtractOutcome,
    SearchHit,
    SearchOutcome,
    SearchProfile,
)


class NoopSearchProvider:
    """检索未配置或被关闭时装配：任何调用都不发请求，直接当作「没有资料」。"""

    name = "noop"

    def search(self, queries: Sequence[str], profile: SearchProfile) -> SearchOutcome:  # noqa: ARG002
        return SearchOutcome(
            query=queries[0] if queries else "",
            degraded=True,
            reason=REASON_DISABLED,
        )

    def extract(self, url: str, profile: SearchProfile) -> ExtractOutcome:  # noqa: ARG002
        return ExtractOutcome(url=url, ok=False, reason=REASON_DISABLED)


class MockSearchProvider:
    """按预置数据返回结果，供离线开发与单测使用。"""

    name = "mock-search"

    def __init__(
        self,
        hits: Sequence[SearchHit] | None = None,
        *,
        extracted_text: str | None = None,
        search_reason: str | None = None,
        extract_reason: str | None = None,
        credits: int | None = 1,
        latency_ms: int = 1,
    ) -> None:
        self._hits = list(hits or [])
        self._extracted_text = extracted_text
        self._search_reason = search_reason
        self._extract_reason = extract_reason
        self.credits = credits
        self.latency_ms = latency_ms
        self.calls: list[dict[str, Any]] = []

    def search(self, queries: Sequence[str], profile: SearchProfile) -> SearchOutcome:
        self.calls.append({"kind": "search", "queries": list(queries), "profile": profile})
        if self._search_reason:
            return SearchOutcome(
                query=queries[0] if queries else "",
                degraded=True,
                reason=self._search_reason,
                latency_ms=self.latency_ms,
            )
        return SearchOutcome(
            query=queries[0] if queries else "",
            hits=tuple(self._hits),
            credits=self.credits,
            latency_ms=self.latency_ms,
        )

    def extract(self, url: str, profile: SearchProfile) -> ExtractOutcome:
        self.calls.append({"kind": "extract", "url": url, "profile": profile})
        if self._extract_reason:
            return ExtractOutcome(
                url=url,
                ok=False,
                reason=self._extract_reason,
                latency_ms=self.latency_ms,
            )
        text = self._extracted_text or ""
        return ExtractOutcome(
            url=url,
            text=text,
            ok=bool(text),
            reason=None if text else REASON_NO_RESULTS,
            credits=self.credits,
            latency_ms=self.latency_ms,
        )
