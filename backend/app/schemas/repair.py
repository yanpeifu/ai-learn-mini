"""修复/补题时 LLM 只需要返回 questions 列表。"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.generation import GeneratedQuestion


class QuestionListPayload(BaseModel):
    questions: list[GeneratedQuestion]
