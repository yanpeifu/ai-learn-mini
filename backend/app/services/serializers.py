"""把数据库模型转成「可以下发给小程序」的结构。"""

from __future__ import annotations

from collections.abc import Sequence

from app.models import Level, Question
from app.repositories import LevelRepository, QuestionRepository
from sqlalchemy.orm import Session


def to_public_question(question: Question) -> dict:
    """注意：不返回 answer_json / explanation（防抓包作弊）。"""
    return {
        "id": question.id,
        "seq": question.seq,
        "type": question.type,
        "difficulty": question.difficulty,
        "stem": question.stem,
        "options": [
            {"key": str(option.get("key", "")), "text": str(option.get("text", ""))}
            for option in (question.options_json or [])
        ],
    }


def to_public_level(level: Level, questions: Sequence[Question]) -> dict:
    items = [to_public_question(question) for question in questions]
    return {
        "id": level.id,
        "seq": level.seq,
        "title": level.title,
        "knowledge_point": level.knowledge_point,
        "question_count": len(items),
        "questions": items,
    }


def build_public_levels(
    db: Session, outline_id: int, *, include_disabled: bool = False
) -> list[dict]:
    """按关卡组装下发数据；被举报下线的题目默认不下发（PRD M3-06）。"""
    levels = LevelRepository(db).list_by_outline(outline_id)
    question_repo = QuestionRepository(db)
    payload: list[dict] = []
    for level in levels:
        questions = question_repo.list_by_level(level.id)
        if not include_disabled:
            questions = [q for q in questions if q.disabled_at is None]
        payload.append(to_public_level(level, questions))
    return payload
