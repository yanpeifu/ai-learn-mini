"""LLM 适配层：框架（LangChain）只允许出现在本包内。"""

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
)
from app.services.llm.factory import FallbackLLMProvider, build_provider
from app.services.llm.mock import MockProvider

__all__ = [
    "ChatMessage",
    "FallbackLLMProvider",
    "LLMBadFormatError",
    "LLMError",
    "LLMProvider",
    "LLMResult",
    "LLMTimeoutError",
    "LLMTransientError",
    "LLMUnavailableError",
    "LLMUsage",
    "MockProvider",
    "build_provider",
]
