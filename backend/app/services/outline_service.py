"""知识大纲生成（PRD F2 / M3-02）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.security import validate_raw_text
from app.schemas.generation import OutlinePayload
from app.services.generation import GenerationCall, invoke_json
from app.services.llm.base import ChatMessage, LLMProvider
from app.services.prompts import OUTLINE_SYSTEM_PROMPT, build_outline_prompt


@dataclass
class OutlineResult:
    payload: OutlinePayload
    call: GenerationCall[OutlinePayload]

    @property
    def attempts(self) -> int:
        return self.call.attempts


def generate_outline(
    provider: LLMProvider, raw_text: str | None, settings: Settings
) -> OutlineResult:
    """把用户输入的文本拆成 3–5 个知识点。

    非法输入在这里就被拦下（不浪费一次模型调用）；
    模型侧的异常交给 invoke_json 统一重试 / 中止。
    """
    text = validate_raw_text(
        raw_text,
        min_chars=settings.raw_text_min_chars,
        max_chars=settings.raw_text_max_chars,
    )
    messages = [
        ChatMessage.system(OUTLINE_SYSTEM_PROMPT),
        ChatMessage.user(build_outline_prompt(text)),
    ]
    call = invoke_json(provider, messages, OutlinePayload, purpose="outline", settings=settings)
    return OutlineResult(payload=call.payload, call=call)
