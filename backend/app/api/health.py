"""健康检查（M1-01 验收：GET /api/health 返回 200）。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.response import ok

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    return ok(
        {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "env": settings.env,
            "llm_provider": settings.llm_provider,
            "database": settings.database_url.split("://", 1)[0],
        }
    )
