from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.quiz import PublicLevel


class AttemptStartRequest(BaseModel):
    outline_id: int


class AttemptStartResponse(BaseModel):
    attempt_id: int
    status: str
    total_count: int
    levels: list[PublicLevel]


class AnswerRequest(BaseModel):
    question_id: int
    answer: list[str] = Field(min_length=1)
    elapsed_ms: int = Field(default=0, ge=0)


class AnswerResponse(BaseModel):
    is_correct: bool
    correct_answer: list[str]
    explanation: str
    correct_count: int
    answered_count: int
    combo: int
    already_answered: bool = False


class LevelScore(BaseModel):
    level_seq: int
    title: str
    knowledge_point: str
    total: int
    correct: int
    accuracy: float


class Settlement(BaseModel):
    accuracy: float
    star: int
    duration_ms: int
    correct_count: int
    total_count: int
    points: list[LevelScore] = []
    weak_points: list[LevelScore] = []
    advice: str = ""


class AttemptFinishResponse(Settlement):
    attempt_id: int
    status: str
