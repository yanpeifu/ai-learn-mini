"""LLMProvider 门面接口 —— 业务代码唯一允许依赖的 LLM 抽象。

设计约束（见《方案设计文档》4.3）：
1. 本文件不 import 任何 langchain，保证业务层与框架解耦；
2. 业务层只拿到 ChatMessage / LLMResult / LLMUsage 这几个自研数据结构；
3. 换供应商 = 换实现，业务代码零改动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Sequence, TypeVar, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str

    @classmethod
    def system(cls, content: str) -> ChatMessage:
        return cls("system", content)

    @classmethod
    def user(cls, content: str) -> ChatMessage:
        return cls("user", content)

    @classmethod
    def assistant(cls, content: str) -> ChatMessage:
        return cls("assistant", content)


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    usage: LLMUsage | None = None
    raw: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


def estimate_cost(
    usage: LLMUsage | None,
    *,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    """按「元 / 百万 token」估算成本，用于日志与限流监控。"""
    if usage is None:
        return 0.0
    return round(
        usage.prompt_tokens / 1_000_000 * input_price_per_million
        + usage.completion_tokens / 1_000_000 * output_price_per_million,
        6,
    )


class LLMError(Exception):
    """LLM 层统一异常基类。retryable 决定上层是否重试。"""

    retryable: bool = False
    code: str = "LLM_ERROR"

    def __init__(self, message: str, *, provider: str | None = None, raw: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.raw = raw


class LLMUnavailableError(LLMError):
    """401 / 402 / 403 等致命错误：立刻中止，不重试，不向用户暴露技术细节。"""

    retryable = False
    code = "LLM_UNAVAILABLE"


class LLMTimeoutError(LLMError):
    retryable = True
    code = "LLM_TIMEOUT"


class LLMBadFormatError(LLMError):
    retryable = True
    code = "LLM_BAD_FORMAT"


class LLMTransientError(LLMError):
    """429 / 5xx / 网络抖动：属于可重试的临时故障。"""

    retryable = True
    code = "LLM_TRANSIENT"


ModelT = TypeVar("ModelT")


@runtime_checkable
class LLMProvider(Protocol):
    """门面：业务层只调用这三个方法。"""

    name: str

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> LLMResult:
        """纯文本对话。"""

    def chat_json(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT],
        **kwargs: Any,
    ) -> tuple[ModelT, LLMResult]:
        """结构化输出：返回 (校验通过的对象, 调用元信息)。"""

    def cost_estimate(self, usage: LLMUsage | None) -> float:
        """本次调用的估算成本（元）。"""
