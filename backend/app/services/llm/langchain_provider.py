"""LangChain 版 LLMProvider 实现 —— 全项目唯一允许 import langchain 的地方。

设计要点（见《方案设计文档》4.3）：
1. 业务代码只依赖 `app.services.llm.base.LLMProvider`，本文件被替换掉也不影响业务；
2. 优先用 LangChain 的结构化输出（with_structured_output），失败则降级为
   「原始文本 + 三级 JSON 修复」——因为假模型（GenericFakeChatModel）与部分供应商不支持结构化输出；
3. 401/402/403 立刻中止（不可重试），超时/429/5xx 标记为可重试；
4. 每次调用都写一条结构化日志（provider/model/耗时/token/估算成本），满足 M1-02、M3-05。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Sequence, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.core.config import Settings
from app.core.logging import log_llm_call
from app.services.llm.base import (
    ChatMessage,
    LLMBadFormatError,
    LLMError,
    LLMProvider,
    LLMResult,
    LLMTimeoutError,
    LLMTransientError,
    LLMUnavailableError,
    LLMUsage,
    estimate_cost,
)
from app.services.llm.json_repair import extract_json

ModelT = TypeVar("ModelT", bound=BaseModel)

FATAL_STATUS_CODES = {401, 402, 403}
TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

_MESSAGE_CLASSES: dict[str, type[BaseMessage]] = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}

# DeepSeek（以及部分 OpenAI 兼容服务）在使用 response_format=json_object 时，
# 要求提示词里必须出现 "json" 这个词，否则直接返回 400。
# 这里统一兜住，避免以后每写一个业务提示词都要记得这件事。
JSON_MODE_HINT = (
    "请只输出一个合法的 json 对象，不要输出解释文字，也不要用 Markdown 代码块包裹。"
    "字段结构如下：{schema}"
)


def schema_hint(schema: type[BaseModel]) -> str:
    parts: list[str] = []
    for name, field in schema.model_fields.items():
        annotation = field.annotation
        type_name = getattr(annotation, "__name__", str(annotation))
        description = field.description or ""
        parts.append(f"{name}: {type_name}（{description}）" if description else f"{name}: {type_name}")
    return "{ " + ", ".join(parts) + " }"


def to_langchain_messages(messages: Sequence[ChatMessage]) -> list[BaseMessage]:
    return [_MESSAGE_CLASSES[m.role](m.content) for m in messages]


def message_to_text(content: Any) -> str:
    """新版 LangChain 的 content 可能是字符串，也可能是 content blocks 列表。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "".join(parts)
    return str(content or "")


def extract_usage(message: Any) -> LLMUsage | None:
    meta = getattr(message, "usage_metadata", None)
    if not meta:
        return None
    return LLMUsage(
        prompt_tokens=int(meta.get("input_tokens") or 0),
        completion_tokens=int(meta.get("output_tokens") or 0),
    )


def status_code_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "http_status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def map_llm_exception(exc: BaseException, *, provider: str | None = None) -> LLMError:
    """把各家 SDK 的异常统一映射成我们的错误分类（决定「重试」还是「立刻中止」）。"""
    if isinstance(exc, LLMError):
        return exc
    status = status_code_of(exc)
    text = str(exc).lower()
    if status in FATAL_STATUS_CODES:
        return LLMUnavailableError(f"模型服务返回 {status}", provider=provider, raw=exc)
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in text or "timed out" in text:
        return LLMTimeoutError("模型调用超时", provider=provider, raw=exc)
    if status in TRANSIENT_STATUS_CODES or "rate limit" in text or "connection" in text:
        return LLMTransientError(f"模型服务临时不可用（{status or 'network'}）", provider=provider, raw=exc)
    if isinstance(exc, (json.JSONDecodeError, ValueError, NotImplementedError, TypeError)):
        return LLMBadFormatError(str(exc), provider=provider, raw=exc)
    return LLMError(f"{type(exc).__name__}: {exc}", provider=provider, raw=exc)


class LangChainLLMProvider:
    """用 LangChain 的 chat model 实现我们的 LLMProvider 门面。"""

    def __init__(
        self,
        chat_model: Any,
        *,
        name: str,
        model_id: str,
        structured_method: str = "json_mode",
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 4.0,
        log_calls: bool = True,
    ) -> None:
        # 允许注入任意「长得像 chat model」的对象，便于测试用假模型（zero network / zero cost）
        self._model = chat_model
        self.name = name
        self.model_id = model_id
        self.structured_method = structured_method
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million
        self.log_calls = log_calls

    # ---------- 构造 ----------
    @classmethod
    def from_settings(
        cls, settings: Settings, provider_name: str | None = None
    ) -> LangChainLLMProvider:
        provider = provider_name or settings.llm_provider
        base_url, model, api_key = settings.provider_credentials(provider)
        if not api_key:
            raise LLMUnavailableError(f"{provider} 未配置 API Key", provider=provider)
        chat_model = init_chat_model(
            model,
            model_provider="openai",  # 三家供应商都是 OpenAI 兼容协议
            base_url=base_url,
            api_key=api_key,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
            # LangChain 自带指数退避重试；文档明确 401/404 不会重试，与我们的要求一致
            max_retries=settings.llm_max_retries,
        )
        return cls(
            chat_model,
            name=provider,
            model_id=model,
            structured_method=settings.llm_structured_method,
            input_price_per_million=settings.llm_input_price_per_million,
            output_price_per_million=settings.llm_output_price_per_million,
            log_calls=settings.log_llm_calls,
        )

    @classmethod
    def from_chat_model(
        cls,
        chat_model: Any,
        *,
        name: str = "fake",
        model_id: str = "fake-model",
        structured_method: str = "json_mode",
        log_calls: bool = True,
    ) -> LangChainLLMProvider:
        """测试与本地开发用：把任意假模型包成 provider。"""
        return cls(
            chat_model,
            name=name,
            model_id=model_id,
            structured_method=structured_method,
            log_calls=log_calls,
        )

    # ---------- 门面方法 ----------
    def chat(
        self, messages: Sequence[ChatMessage], *, purpose: str = "chat", **kwargs: Any
    ) -> LLMResult:
        started = time.perf_counter()
        try:
            message = self._model.invoke(to_langchain_messages(messages), **kwargs)
        except BaseException as exc:  # noqa: BLE001 - 统一交给 map_llm_exception 分类
            mapped = map_llm_exception(exc, provider=self.name)
            self._log(purpose=purpose, latency_ms=_elapsed_ms(started), success=False, error=mapped)
            raise mapped from exc
        result = LLMResult(
            text=message_to_text(getattr(message, "content", "")),
            provider=self.name,
            model=self.model_id,
            latency_ms=_elapsed_ms(started),
            usage=extract_usage(message),
            raw=message,
            meta={"response_metadata": getattr(message, "response_metadata", {}) or {}},
        )
        self._log(purpose=purpose, result=result)
        return result

    def chat_json(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT],
        *,
        purpose: str = "chat_json",
        **kwargs: Any,
    ) -> tuple[ModelT, LLMResult]:
        effective_messages = self._effective_messages(messages, schema)
        lc_messages = to_langchain_messages(effective_messages)
        structured = self._structured_runner(schema)

        if structured is not None:
            started = time.perf_counter()
            try:
                payload = structured.invoke(lc_messages, **kwargs)
            except BaseException as exc:  # noqa: BLE001
                mapped = map_llm_exception(exc, provider=self.name)
                self._log(purpose=purpose, latency_ms=_elapsed_ms(started), success=False, error=mapped)
                raise mapped from exc
            parsed, raw_message, parsing_error = _split_structured_payload(payload)
            if parsed is not None and parsing_error is None:
                result = self._result_from_message(
                    raw_message, latency_ms=_elapsed_ms(started)
                )
                self._log(purpose=purpose, result=result)
                return _as_model(parsed, schema), result
            # 结构化输出失败 → 降级到「原始文本 + JSON 修复」
            fallback_text = message_to_text(getattr(raw_message, "content", ""))
            if not fallback_text:
                raise LLMBadFormatError(
                    f"结构化输出失败：{parsing_error}", provider=self.name, raw=payload
                )
            return self._parse_text(fallback_text, schema, purpose, started, raw_message)

        # 模型不支持结构化输出（例如 LangChain 的假模型）→ 走文本 + 修复
        text_result = self.chat(effective_messages, purpose=purpose, **kwargs)
        return self._parse_text(text_result.text, schema, purpose, None, text_result.raw, text_result)

    def cost_estimate(self, usage: LLMUsage | None) -> float:
        return estimate_cost(
            usage,
            input_price_per_million=self.input_price_per_million,
            output_price_per_million=self.output_price_per_million,
        )

    # ---------- 内部工具 ----------
    def _structured_runner(self, schema: type[ModelT]) -> Any | None:
        try:
            return self._model.with_structured_output(
                schema, method=self.structured_method, include_raw=True
            )
        except (NotImplementedError, TypeError, ValueError, AttributeError):
            # 模型不支持结构化输出，交给上层降级
            return None

    def _effective_messages(
        self, messages: Sequence[ChatMessage], schema: type[BaseModel]
    ) -> list[ChatMessage]:
        """json_mode 下补一条带 schema 说明的 system 提示（见 JSON_MODE_HINT 注释）。"""
        if self.structured_method != "json_mode":
            return list(messages)
        hint = ChatMessage.system(JSON_MODE_HINT.format(schema=schema_hint(schema)))
        return [hint, *messages]

    def _parse_text(
        self,
        text: str,
        schema: type[ModelT],
        purpose: str,
        latency_ms: int | None,
        raw: Any = None,
        result: LLMResult | None = None,
    ) -> tuple[ModelT, LLMResult]:
        try:
            data = extract_json(text)
            parsed = schema.model_validate(data)
        except Exception as exc:  # noqa: BLE001 - 统一转成结构错误
            raise LLMBadFormatError(str(exc), provider=self.name, raw=text) from exc
        result = result or self._result_from_message(raw, latency_ms=latency_ms or 0)
        self._log(purpose=purpose, result=result)
        return parsed, result

    def _result_from_message(self, message: Any, *, latency_ms: int) -> LLMResult:
        return LLMResult(
            text=message_to_text(getattr(message, "content", "")),
            provider=self.name,
            model=self.model_id,
            latency_ms=latency_ms,
            usage=extract_usage(message),
            raw=message,
        )

    def _log(
        self,
        *,
        purpose: str,
        latency_ms: int | None = None,
        result: LLMResult | None = None,
        success: bool = True,
        error: BaseException | None = None,
    ) -> None:
        if not self.log_calls:
            return
        usage = result.usage if result else None
        effective_latency = latency_ms if latency_ms is not None else (result.latency_ms if result else 0)
        log_llm_call(
            provider=self.name,
            model=self.model_id,
            purpose=purpose,
            latency_ms=effective_latency,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            estimated_cost=self.cost_estimate(usage),
            success=success,
            error=None if error is None else f"{type(error).__name__}: {error}",
        )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _split_structured_payload(payload: Any) -> tuple[Any, Any, Any]:
    """with_structured_output(include_raw=True) 返回 {"raw","parsed","parsing_error"}。"""
    if isinstance(payload, dict) and "parsed" in payload:
        return payload.get("parsed"), payload.get("raw"), payload.get("parsing_error")
    return payload, None, None


def _as_model(value: Any, schema: type[ModelT]) -> ModelT:
    if isinstance(value, schema):
        return value
    return schema.model_validate(value)
