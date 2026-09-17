"""LLM 结构化输出的数据模型（也是 quality 校验的输入结构）。

字段与 `quality_check.py` 里已验证的输出契约保持一致：
{"outline": [{id,title,summary}], "questions": [{...}]}
这里额外加了 level_seq（MVP 是 3 关 × 5 题）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

QuestionType = Literal["single", "multiple", "judge"]


class OutlinePoint(BaseModel):
    id: str = Field(description="知识点 id，从 kp1 开始连续编号")
    title: str = Field(description="知识点名称，不超过 30 字")
    summary: str = Field(description="一句话说明，不超过 40 字")


class OutlinePayload(BaseModel):
    title: str = Field(default="", description="用不超过 20 字概括这段内容的主题")
    points: list[OutlinePoint] = Field(min_length=3, max_length=5)


class GeneratedOption(BaseModel):
    key: str = Field(description="选项 key，从 A 开始连续编号")
    text: str


class GeneratedHint(BaseModel):
    """苏格拉底式引导问题（L3，V0.5 使用；MVP 允许为 null）。"""

    stem: str
    options: list[GeneratedOption]
    answer: list[str]


class GeneratedQuestion(BaseModel):
    id: str
    level_seq: int | None = Field(default=None, ge=1, le=3)
    knowledge_point_id: str
    type: QuestionType
    difficulty: int = Field(ge=1, le=5)
    stem: str
    options: list[GeneratedOption]
    answer: list[str]
    explanation: str
    hint: GeneratedHint | None = None


class GeneratedQuestionSet(BaseModel):
    outline: list[OutlinePoint] = Field(min_length=3, max_length=5)
    questions: list[GeneratedQuestion]

    def to_payload(self) -> dict:
        """转成 quality_check.py 使用的原始 dict 结构，便于与脚本做一致性校验。"""
        return self.model_dump(mode="json")
