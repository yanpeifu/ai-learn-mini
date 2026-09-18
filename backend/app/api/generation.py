"""生成任务进度查询（配合「后台任务 + 前端轮询」机制）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.errors import AppError, ErrorCode
from app.core.response import ok
from fastapi import Request

router = APIRouter(tags=["generation"])


@router.get("/generation/tasks/{task_id}")
def get_task(task_id: str, request: Request, user: CurrentUser) -> dict:
    registry = request.app.state.task_registry
    task = registry.get(task_id)
    if task is None or task.user_id != user.id:
        raise AppError(ErrorCode.NOT_FOUND, "这个任务不存在或已过期，重新点一次吧")
    return ok(task.to_payload())
