"""生成类调用的统一入口：重试策略 + 错误码映射。

PRD 2.2 的异常处理要求：
- 超时 / 网络抖动 / 返回格式不合法 → 自动重试（最多 2 次）；
- 401/402/403 → **立即中止**，不重试，向用户提示「服务暂时不可用，请稍后再试」；
- 重试仍失败 → 提示重试，且不产生脏数据。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services.llm.base import (
    ChatMessage,
    LLMBadFormatError,
    LLMError,
    LLMProvider,
    LLMResult,
    LLMTimeoutError,
    LLMTransientError,
    LLMUnavailableError,
)

logger = logging.getLogger("app.generation")

ModelT = TypeVar("ModelT", bound=BaseModel)

_RETRYABLE_TO_ERROR_CODE: dict[type[LLMError], ErrorCode] = {
    LLMTimeoutError: ErrorCode.LLM_TIMEOUT,
    LLMBadFormatError: ErrorCode.LLM_BAD_FORMAT,
    LLMTransientError: ErrorCode.GENERATION_FAILED,
}


@dataclass
class GenerationCall(Generic[ModelT]):
    payload: ModelT
    llm: LLMResult
    attempts: int


def invoke_json(
    provider: LLMProvider,
    messages: Sequence[ChatMessage],
    schema: type[ModelT],
    *,
    purpose: str,
    settings: Settings,
    max_retries: int | None = None,
) -> GenerationCall[ModelT]:
    """调用模型并做结构化解析，按 PRD 的策略重试与降级。"""
    retries = settings.llm_max_retries if max_retries is None else max_retries
    last_error: LLMError | None = None
    attempts = 0

    for attempt in range(1, retries + 2):
        attempts = attempt
        try:
            payload, llm_result = provider.chat_json(messages, schema, purpose=purpose)
            return GenerationCall(payload=payload, llm=llm_result, attempts=attempts)
        except LLMUnavailableError as exc:
            # 密钥、余额、权限问题：重试没有意义，立刻中止
            logger.warning(
                "大模型不可用，立即停止重试（请检查密钥或余额）",
                extra={
                    "purpose": purpose,
                    "attempt": attempt,
                    "code": "LLM_UNAVAILABLE",
                    "reason": str(exc),
                },
            )
            raise AppError(ErrorCode.LLM_UNAVAILABLE) from exc
        except (LLMTimeoutError, LLMBadFormatError, LLMTransientError) as exc:
            last_error = exc
            logger.info(
                f"这次没成功，正在自动重试（第 {attempt} 次）",
                extra={
                    "purpose": purpose,
                    "attempt": attempt,
                    "max_attempts": retries + 1,
                    "error_type": type(exc).__name__,
                },
            )
            continue

    code = _RETRYABLE_TO_ERROR_CODE.get(type(last_error), ErrorCode.GENERATION_FAILED)
    raise AppError(code) from last_error


def as_app_error(exc: LLMError) -> AppError:
    """把 LLM 层异常转成对外的业务异常（技术细节只进日志）。"""
    if isinstance(exc, LLMUnavailableError):
        return AppError(ErrorCode.LLM_UNAVAILABLE)
    return AppError(_RETRYABLE_TO_ERROR_CODE.get(type(exc), ErrorCode.GENERATION_FAILED))


def summarize_llm_result(result: LLMResult, *, provider: LLMProvider) -> dict[str, Any]:
    """给日志/埋点用的调用摘要（不含任何敏感内容）。"""
    usage = result.usage
    return {
        "provider": result.provider,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
        "estimated_cost": provider.cost_estimate(usage),
    }
