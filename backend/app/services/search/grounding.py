"""按需取外部资料：配额 → 画像 → 检索 → 日志。整段逻辑不抛异常（只降级）。

「大纲」和「出题」两次生成共用这条链路。因为资料不落库（design.md D6 的取舍），
出题阶段会按大纲的知识点**再检索一次**——代价是每次学习可能消耗两次检索额度，
换来的是不用加表、不用迁移。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.config import Settings
from app.services.quota import record_search_usage, search_quota_exceeded
from app.services.search.base import (
    REASON_DISABLED,
    REASON_QUOTA,
    REASON_UNAVAILABLE,
    SearchHit,
    SearchProvider,
)
from app.services.search.profiles import KnowledgeTraits, build_profile

logger = logging.getLogger("app.search")


@dataclass(frozen=True)
class GroundingResult:
    """一次取资料的结果。``ok=False`` 表示本次没有可用资料（含所有降级情形）。"""

    references: tuple[SearchHit, ...] = ()
    attempted: bool = False
    degraded: bool = True
    reason: str | None = None
    credits: int | None = None
    trimmed: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.references)


def trim_references(
    hits: Sequence[SearchHit], max_chars: int
) -> tuple[tuple[SearchHit, ...], bool]:
    """按注入预算裁剪资料（保护模型上下文，不是输入框的字数校验）。"""
    if max_chars <= 0:
        return tuple(hits), False

    kept: list[SearchHit] = []
    used = 0
    trimmed = False
    for hit in hits:
        body = (hit.raw_content or hit.content or "").strip()
        remaining = max_chars - used
        if remaining <= 0:
            trimmed = True
            break
        if len(body) > remaining:
            body = body[:remaining]
            trimmed = True
        kept.append(
            SearchHit(
                title=hit.title,
                url=hit.url,
                content=body,
                raw_content=None,
                score=hit.score,
            )
        )
        used += len(body)
    return tuple(kept), trimmed


def gather_references(
    provider: SearchProvider,
    *,
    queries: Sequence[str],
    traits: KnowledgeTraits,
    settings: Settings,
    user_id: int | None = None,
    purpose: str = "outline",
) -> GroundingResult:
    """按需检索资料；任何失败都只降级，不打断生成（对应 spec 的降级要求）。"""
    cleaned = [query.strip() for query in queries if query and query.strip()]
    if not cleaned:
        return GroundingResult(degraded=True, reason=REASON_DISABLED)

    if settings.search_effective_mode == "off":
        logger.info(
            "本次没有联网检索（检索未配置或被关闭）",
            extra={"kind": "search", "purpose": purpose, "reason": REASON_DISABLED},
        )
        return GroundingResult(degraded=True, reason=REASON_DISABLED)

    if user_id is not None and search_quota_exceeded(user_id, settings, None):
        logger.info(
            "今日检索次数已用完，本次直接按无资料生成",
            extra={"kind": "search", "purpose": purpose, "reason": REASON_QUOTA},
        )
        return GroundingResult(degraded=True, reason=REASON_QUOTA)

    profile = build_profile(traits, settings)
    try:
        outcome = provider.search(cleaned, profile)
    except Exception:  # noqa: BLE001 - 检索绝不能拖垮生成
        logger.exception(
            "联网检索出现未预期错误，按无资料继续",
            extra={"kind": "search", "purpose": purpose, "reason": REASON_UNAVAILABLE},
        )
        return GroundingResult(attempted=True, degraded=True, reason=REASON_UNAVAILABLE)

    if user_id is not None:
        record_search_usage(user_id)

    references, trimmed = trim_references(outcome.hits, settings.search_context_max_chars)
    logger.info(
        f"联网检索完成：拿到 {len(references)} 条资料"
        + ("（已按注入预算裁剪）" if trimmed else ""),
        extra={
            "kind": "search",
            "purpose": purpose,
            "reason": outcome.reason,
            "hits": len(references),
            "credits": outcome.credits,
            "latency_ms": outcome.latency_ms,
            # 只记来源域名级信息，便于事后追溯又不泄露正文
            "sources": [hit.url for hit in references[:5]],
            "include_raw_content": profile.include_raw_content,
            "search_depth": profile.search_depth,
            "topic": profile.topic,
        },
    )
    return GroundingResult(
        references=references,
        attempted=True,
        degraded=not references,
        reason=outcome.reason,
        credits=outcome.credits,
        trimmed=trimmed,
    )
