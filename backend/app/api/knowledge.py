"""知识大纲与出题接口（PRD K1–K4 / M4-03~M4-06）。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from app.api.deps import AppSettings, CurrentUser, DbSession, LlmProvider, SearchDep
from app.core.errors import AppError, ErrorCode
from app.core.response import ok
from app.models import KnowledgeOutline
from app.repositories import KnowledgeOutlineRepository, KnowledgeSourceRepository
from app.schemas.knowledge import (
    LevelsGenerateRequest,
    OutlineGenerateRequest,
    OutlineSaveRequest,
)
from app.services.level_service import start_levels_task
from app.services.outline_service import generate_outline
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
    search: SearchDep,
) -> dict:
    """生成知识大纲：一次模型调用拆出 3–5 个知识点；需要时先联网取资料再重跑一次。"""
    ensure_outline_quota(db, user.id, settings)
    result = generate_outline(
        provider, payload.raw_text, settings, search=search, user_id=user.id
    )
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
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: LlmProvider,
    search: SearchDep,
) -> dict:
    """提交出题任务，**立即返回 task_id**（出题在后台跑，前端轮询进度）。

    这样长耗时不再受隧道重置、90 秒请求超时、手机切后台的影响；
    同一个大纲重复提交会复用同一个任务，不会重复扣费。
    """
    outline = _get_owned_outline(db, payload.outline_id, user.id)
    ensure_levels_quota(db, user.id, settings)

    task_id, reused = start_levels_task(
        registry=request.app.state.task_registry,
        session_factory=request.app.state.session_factory,
        provider=provider,
        search_provider=search,
        settings=settings,
        outline_id=outline.id,
        user_id=user.id,
    )
    return ok(
        {
            "task_id": task_id,
            "status": "running",
            "reused": reused,
            "outline_id": outline.id,
        }
    )
