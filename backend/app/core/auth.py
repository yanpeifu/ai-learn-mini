"""自定义登录态：JWT（HS256）签发与校验。

PRD F7：小程序静默登录拿 code → 后端换 openid → 查/建用户 → 返回自定义 token，
之后所有写接口都在 Header 带 `Authorization: Bearer <token>`。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode


def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.token_expire_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.token_secret, algorithm=settings.token_algorithm)


def decode_access_token(token: str, settings: Settings) -> int:
    """解析 token 并返回 user_id；任何异常都转成统一的 401。"""
    if not token:
        raise AppError(ErrorCode.UNAUTHORIZED)
    try:
        payload = jwt.decode(
            token, settings.token_secret, algorithms=[settings.token_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "登录状态已过期，重新进入一下小程序") from exc
    except jwt.PyJWTError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED) from exc

    subject = payload.get("sub")
    if not subject or not str(subject).isdigit():
        raise AppError(ErrorCode.UNAUTHORIZED)
    return int(subject)
