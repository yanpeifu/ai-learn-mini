"""下发到小程序的题目结构。

**这里刻意不包含 answer / explanation**（PRD 2.5 接口设计要求第 3 条：
题目下发时不能包含答案，防止抓包作弊）。正确答案只在提交作答后返回。
"""

from __future__ import annotations

from pydantic import BaseModel


class PublicOption(BaseModel):
    key: str
    text: str


class PublicQuestion(BaseModel):
    id: int
    seq: int
    type: str
    difficulty: int
    stem: str
    options: list[PublicOption]


class PublicLevel(BaseModel):
    id: int
    seq: int
    title: str
    knowledge_point: str
    question_count: int
    questions: list[PublicQuestion]
