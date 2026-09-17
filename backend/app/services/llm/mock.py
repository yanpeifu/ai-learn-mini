"""MockProvider：离线开发与测试用，按 Pydantic schema 返回预置数据，0 成本、不联网。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence, TypeVar

from pydantic import BaseModel

from app.services.llm.base import (
    ChatMessage,
    LLMBadFormatError,
    LLMResult,
    LLMUsage,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class MockProvider:
    name = "mock"

    def __init__(
        self,
        responses: Mapping[Any, Any] | None = None,
        *,
        model_id: str = "mock-model",
        text: str | None = None,
        latency_ms: int = 1,
    ) -> None:
        self.model_id = model_id
        self._responses: dict[str, Any] = {}
        for key, value in (responses or {}).items():
            self._responses[self._key(key)] = value
        self._text = text
        self.latency_ms = latency_ms
        self.calls: list[dict[str, Any]] = []

    @staticmethod
    def _key(key: Any) -> str:
        if isinstance(key, str):
            return key
        if isinstance(key, type) and issubclass(key, BaseModel):
            return key.__name__
        return str(key)

    def payload_for(self, schema: type[BaseModel]) -> Any:
        if schema.__name__ not in self._responses:
            raise LLMBadFormatError(
                f"MockProvider 没有为 {schema.__name__} 配置返回数据（可先注册 responses）",
                provider=self.name,
            )
        return self._responses[schema.__name__]

    def chat(
        self, messages: Sequence[ChatMessage], *, purpose: str = "chat", **kwargs: Any
    ) -> LLMResult:  # noqa: ARG002
        self.calls.append({"purpose": purpose, "messages": list(messages)})
        text = self._text if self._text is not None else json.dumps(
            {"mock": True}, ensure_ascii=False
        )
        return LLMResult(
            text=text,
            provider=self.name,
            model=self.model_id,
            latency_ms=self.latency_ms,
            usage=None,
        )

    def chat_json(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT],
        *,
        purpose: str = "chat_json",
        **kwargs: Any,
    ) -> tuple[ModelT, LLMResult]:
        self.calls.append({"purpose": purpose, "messages": list(messages), "schema": schema.__name__})
        payload = self.payload_for(schema)
        parsed = payload if isinstance(payload, schema) else schema.model_validate(payload)
        return parsed, LLMResult(
            text=json.dumps(payload, ensure_ascii=False, default=str),
            provider=self.name,
            model=self.model_id,
            latency_ms=self.latency_ms,
            usage=None,
            meta={"mock": True},
        )

    def cost_estimate(self, usage: LLMUsage | None) -> float:  # noqa: ARG002
        return 0.0

    @classmethod
    def from_fixture_dir(cls, directory: Path, *, text: str | None = None) -> MockProvider:
        """夹具文件名 = Pydantic 模型类名，例如 OutlinePayload.json / QuestionSetPayload.json。"""
        responses: dict[str, Any] = {}
        for file in sorted(Path(directory).glob("*.json")):
            responses[file.stem] = json.loads(file.read_text(encoding="utf-8"))
        return cls(responses, text=text)
