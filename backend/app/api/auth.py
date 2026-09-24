"""登录接口（PRD F7 / M4-01）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AppSettings, DbSession
from app.core.auth import create_access_token
from app.core.response import ok
from app.repositories import UserRepository
from app.schemas.auth import LoginRequest
from app.services.wechat import resolve_openid

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginRequest, db: DbSession, settings: AppSettings) -> dict:
    """静默登录：code → openid → 查/建用户 → 返回自定义 token。"""
    openid = resolve_openid(payload.code, settings)
    user = UserRepository(db).get_or_create_by_openid(openid)
    token = create_access_token(user.id, settings)
    return ok(
        {
            "token": token,
            "user": {
                "id": user.id,
                "nickname": user.nickname,
                "avatar_url": user.avatar_url,
                "is_member": user.is_member,
            },
        }
    )
