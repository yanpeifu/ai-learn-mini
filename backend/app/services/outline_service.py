"""知识大纲生成（PRD F2 / M3-02），含「按需联网取资料」。

流程：解析输入（网址则先抓正文）→ 第一次大纲调用（顺带判断是否需要最新资料）
→ 需要时检索 → 带参考资料重跑一次大纲 → 没资料时在结果里显式标注「未联网核实」。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import (
    TEXT_SENSITIVE_MESSAGE,
    find_sensitive_word,
    validate_raw_text,
)
from app.schemas.generation import OutlinePayload
from app.services.generation import GenerationCall, invoke_json
from app.services.llm.base import ChatMessage, LLMProvider
from app.services.prompts import OUTLINE_SYSTEM_PROMPT, build_outline_prompt
from app.services.search.base import REASON_DISABLED, REASON_NOT_NEEDED, SearchProvider
from app.services.search.grounding import GroundingResult, gather_references
from app.services.search.profiles import KnowledgeTraits, build_profile
from app.services.search.urls import extract_urls

logger = logging.getLogger("app.outline")

#: 没有任何外部资料时，写进知识点说明里的显式标注（让不确定性在现有界面上可见）
UNVERIFIED_MARK = "（未联网核实）"
URL_UNREADABLE_MESSAGE = "这个链接没能读到内容，换一个链接，或者直接把文字粘进来试试"
URL_READING_OFF_MESSAGE = "现在还不能读取链接，请直接把文字粘进来"


@dataclass
class OutlineResult:
    payload: OutlinePayload
    call: GenerationCall[OutlinePayload]
    grounding: GroundingResult | None = None
    source_url: str | None = None

    @property
    def attempts(self) -> int:
        return self.call.attempts


def detect_locale(text: str) -> str:
    """粗判中英文：中文用例更多时按国内用户处理（决定要不要加中文/地域偏置）。"""
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return "zh" if cjk >= 5 else "other"


def annotate_unverified(payload: OutlinePayload) -> OutlinePayload:
    """没有外部资料时，把「未联网核实」显式写进用户能看到的说明里。"""
    points = [
        point.model_copy(update={"summary": f"{point.summary}{UNVERIFIED_MARK}"})
        for point in payload.points
    ]
    return payload.model_copy(update={"points": points})


def resolve_knowledge_source(
    raw_text: str | None,
    *,
    search: SearchProvider | None,
    settings: Settings,
) -> tuple[str, str | None]:
    """输入含网址时先抓整页正文。

    这条路径**不套用 20–2000 字校验**（网址抓下来的正文通常远超上上限），
    但仍然要过敏感词；抓不到正文时明确告诉用户，而不是拿一个网址字符串去出题。
    """
    text = (raw_text or "").strip()
    urls = extract_urls(text)
    if not urls or search is None:
        return (
            validate_raw_text(
                raw_text,
                min_chars=settings.raw_text_min_chars,
                max_chars=settings.raw_text_max_chars,
            ),
            None,
        )

    url = urls[0]
    outcome = search.extract(url, build_profile(KnowledgeTraits(), settings))
    if not outcome.ok or not outcome.text.strip():
        message = (
            URL_READING_OFF_MESSAGE
            if outcome.reason == REASON_DISABLED
            else URL_UNREADABLE_MESSAGE
        )
        raise AppError(ErrorCode.INVALID_INPUT, message)

    body = outcome.text.strip()
    if find_sensitive_word(body):
        raise AppError(ErrorCode.INVALID_INPUT, TEXT_SENSITIVE_MESSAGE)
    extra = text.replace(url, "").strip()
    logger.info(
        "已按网址抓取正文",
        extra={"kind": "extract", "url": url, "chars": len(body)},
    )
    return (f"{extra}\n\n{body}" if extra else body), url


def _gather_grounding(
    payload: OutlinePayload,
    text: str,
    *,
    search: SearchProvider | None,
    settings: Settings,
    user_id: int | None,
) -> GroundingResult:
    if search is None:
        return GroundingResult(degraded=True, reason=REASON_DISABLED)
    force = settings.search_effective_mode == "always"
    if not payload.needs_external_reference and not force:
        return GroundingResult(degraded=True, reason=REASON_NOT_NEEDED)

    queries = list(payload.search_queries) or ([payload.title] if payload.title else [])
    return gather_references(
        search,
        queries=queries,
        traits=KnowledgeTraits(
            complexity=payload.complexity,
            timeliness=payload.timeliness,
            locale=detect_locale(text),
        ),
        settings=settings,
        user_id=user_id,
        purpose="outline",
    )


def generate_outline(
    provider: LLMProvider,
    raw_text: str | None,
    settings: Settings,
    *,
    search: SearchProvider | None = None,
    user_id: int | None = None,
) -> OutlineResult:
    """把用户输入的文本拆成 3–5 个知识点。

    非法输入在这里就被拦下（不浪费一次模型调用）；
    模型侧的异常交给 invoke_json 统一重试 / 中止。
    """
    text, source_url = resolve_knowledge_source(raw_text, search=search, settings=settings)
    messages = [
        ChatMessage.system(OUTLINE_SYSTEM_PROMPT),
        ChatMessage.user(build_outline_prompt(text)),
    ]
    call = invoke_json(provider, messages, OutlinePayload, purpose="outline", settings=settings)
    payload = call.payload

    grounding = _gather_grounding(
        payload, text, search=search, settings=settings, user_id=user_id
    )
    if grounding.ok:
        grounded_messages = [
            ChatMessage.system(OUTLINE_SYSTEM_PROMPT),
            ChatMessage.user(build_outline_prompt(text, references=grounding.references)),
        ]
        try:
            grounded_call = invoke_json(
                provider,
                grounded_messages,
                OutlinePayload,
                purpose="outline_grounded",
                settings=settings,
            )
            return OutlineResult(
                payload=grounded_call.payload,
                call=grounded_call,
                grounding=grounding,
                source_url=source_url,
            )
        except AppError as exc:
            # 已经有一份可用的大纲了，带资料那次失败就退回它，并按「未核实」标注
            logger.warning(
                "带参考资料的大纲生成失败，沿用第一次结果并标注未联网核实",
                extra={"code": exc.code, "stage": "outline_grounded"},
            )
            grounding = GroundingResult(degraded=True, reason=exc.code)

    return OutlineResult(
        payload=annotate_unverified(payload),
        call=call,
        grounding=grounding,
        source_url=source_url,
    )
