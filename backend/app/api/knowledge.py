"""知识大纲与出题接口（PRD K1–K4 / M4-03~M4-06）。"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import AppSettings, CurrentUser, DbSession, LlmProvider
from app.core.errors import AppError, ErrorCode
from app.core.response import ok
from app.models import KnowledgeOutline
from app.repositories import (
    KnowledgeOutlineRepository,
    KnowledgeSourceRepository,
    LevelRepository,
    QuestionRepository,
)
from app.schemas.generation import GeneratedQuestionSet, OutlinePoint
from app.schemas.knowledge import (
    LevelsGenerateRequest,
    OutlineGenerateRequest,
    OutlineSaveRequest,
)
from app.services.outline_service import generate_outline
from app.services.question_service import generate_question_set
from app.services.quota import ensure_levels_quota, ensure_outline_quota
from app.services.serializers import build_public_levels

router = APIRouter(tags=["knowledge"])


def _get_owned_outline(db: Session, outline_id: int, user_id: int) -> KnowledgeOutline:
    outline = KnowledgeOutlineRepository(db).get(outline_id)
    if outline is None or outline.user_id != user_id:
        raise AppError(ErrorCode.OUTLINE_NOT_FOUND)
    return outline


@router.post("/knowledge/outline")
def create_outline(
    payload: OutlineGenerateRequest,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: LlmProvider,
) -> dict:
    """生成知识大纲：一次模型调用拆出 3–5 个知识点。"""
    ensure_outline_quota(db, user.id, settings)
    result = generate_outline(provider, payload.raw_text, settings)
    raw_text = payload.raw_text.strip()
    source = KnowledgeSourceRepository(db).create(
        user_id=user.id, raw_text=raw_text, title=result.payload.title or None
    )
    outline = KnowledgeOutlineRepository(db).create(
        source_id=source.id,
        user_id=user.id,
        title=result.payload.title or source.title,
        points=[point.model_dump() for point in result.payload.points],
    )
    return ok(
        {
            "outline_id": outline.id,
            "source_id": source.id,
            "title": outline.title,
            "points": outline.outline_json,
        }
    )


@router.get("/knowledge/outline/{outline_id}")
def get_outline(outline_id: int, db: DbSession, user: CurrentUser) -> dict:
    outline = _get_owned_outline(db, outline_id, user.id)
    return ok(
        {
            "id": outline.id,
            "title": outline.title,
            "status": outline.status,
            "points": outline.outline_json,
            "levels": build_public_levels(db, outline.id),
        }
    )


@router.put("/knowledge/outline/{outline_id}")
def save_outline(
    outline_id: int, payload: OutlineSaveRequest, db: DbSession, user: CurrentUser
) -> dict:
    """保存用户编辑后的大纲（PRD F2：可改标题、可删除，剩余不足 2 个禁止删）。"""
    _get_owned_outline(db, outline_id, user.id)
    if len(payload.points) < 2:
        raise AppError(ErrorCode.INVALID_INPUT, "至少要保留 2 个知识点，不然没法出题")
    updated = KnowledgeOutlineRepository(db).update_points(
        outline_id, points=[point.model_dump() for point in payload.points]
    )
    return ok({"ok": True, "points": updated.outline_json if updated else []})


@router.post("/knowledge/levels")
def create_levels(
    payload: LevelsGenerateRequest,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: LlmProvider,
) -> dict:
    """生成 3 关 × 5 题并落库；下发的题目不含答案。"""
    outline = _get_owned_outline(db, payload.outline_id, user.id)
    ensure_levels_quota(db, user.id, settings)

    points = [OutlinePoint(**item) for item in outline.outline_json]
    result = generate_question_set(provider, points, settings)
    _persist_levels(db, outline, result.payload)

    return ok(
        {
            "outline_id": outline.id,
            "levels": build_public_levels(db, outline.id),
            "stats": {
                "regenerated": result.regenerated,
                "dropped": result.dropped,
                "backfilled": result.backfilled,
                "warnings": len(result.issues),
            },
        }
    )


def _persist_levels(db: Session, outline: KnowledgeOutline, question_set: GeneratedQuestionSet) -> None:
    """把关卡与题目写入数据库（重新出题时先清掉旧的，避免题目翻倍）。"""
    level_repo = LevelRepository(db)
    question_repo = QuestionRepository(db)
    level_repo.delete_by_outline(outline.id)

    point_titles = {point["id"]: point["title"] for point in outline.outline_json}
    grouped: dict[int, list] = {}
    for question in question_set.questions:
        grouped.setdefault(question.level_seq or 1, []).append(question)

    for seq in sorted(grouped):
        questions = grouped[seq]
        dominant_kp = Counter(q.knowledge_point_id for q in questions).most_common(1)[0][0]
        kp_title = point_titles.get(dominant_kp, dominant_kp)
        level = level_repo.create(
            outline_id=outline.id,
            seq=seq,
            title=f"第 {seq} 关 · {kp_title}"[:64],
            knowledge_point=kp_title[:128],
            question_count=len(questions),
        )
        for index, question in enumerate(questions, 1):
            question_repo.create(
                level_id=level.id,
                outline_id=outline.id,
                seq=index,
                type=question.type,
                difficulty=question.difficulty,
                stem=question.stem,
                options=[option.model_dump() for option in question.options],
                answer=list(question.answer),
                explanation=question.explanation,
                hint=question.hint.model_dump() if question.hint else None,
            )
