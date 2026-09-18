"""修复/补题时 LLM 只需要返回 questions 列表。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

from app.schemas.generation import GeneratedQuestion, salvage_questions


class QuestionListPayload(BaseModel):
    questions: list[GeneratedQuestion] = []

    @model_validator(mode="before")
    @classmethod
    def _salvage(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("questions"), list):
            return {**data, "questions": salvage_questions(data["questions"])}
        return data
