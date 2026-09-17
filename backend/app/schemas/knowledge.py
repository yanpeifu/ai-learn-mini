from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.quiz import PublicLevel


class OutlineGenerateRequest(BaseModel):
    raw_text: str = Field(description="20–2000 字的知识文本")


class OutlinePointPublic(BaseModel):
    id: str
    title: str
    summary: str


class OutlineGenerateResponse(BaseModel):
    outline_id: int
    source_id: int
    title: str
    points: list[OutlinePointPublic]


class OutlineSaveRequest(BaseModel):
    points: list[OutlinePointPublic] = Field(min_length=2, max_length=5)


class OutlineDetailResponse(BaseModel):
    id: int
    title: str
    status: str
    points: list[OutlinePointPublic]
    levels: list[PublicLevel] = []


class LevelsGenerateRequest(BaseModel):
    outline_id: int


class LevelsGenerateResponse(BaseModel):
    outline_id: int
    levels: list[PublicLevel]


class TemplatePublic(BaseModel):
    id: str
    name: str
    icon: str
    prefill: str
