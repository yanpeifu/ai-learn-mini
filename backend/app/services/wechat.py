"""微信静默登录：code → openid。"""

from __future__ import annotations

import hashlib
import logging

import httpx

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import validate_raw_text  # noqa: F401  (保持模块内可读性)

logger = logging.getLogger("app.wechat")

CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
DEV_CODE_PREFIX = "dev_"


def is_dev_code(code: str) -> bool:
    return code.startswith(DEV_CODE_PREFIX)


def dev_openid(code: str) -> str:
    """本地开发用：同一个 code 永远映射到同一个 openid，便于反复调试同一账号。"""
    digest = hashlib.sha1(code.encode("utf-8")).hexdigest()[:16]
    return f"dev_{digest}"


def resolve_openid(code: str | None, settings: Settings) -> str:
    if not code:
        raise AppError(ErrorCode.INVALID_INPUT, "缺少登录凭证，重新进入一下小程序")

    if is_dev_code(code):
        if not settings.dev_login_enabled:
            logger.warning(
                "收到 dev_ 假登录请求，但 DEV_LOGIN_ENABLED 未开启",
                extra={"hint": "在启动后端前设置 $env:DEV_LOGIN_ENABLED='true'"},
            )
            raise AppError(ErrorCode.LOGIN_UNAVAILABLE)
        return dev_openid(code)

    if not settings.wechat_appid or not settings.wechat_secret:
        logger.warning(
            "收到真实登录 code，但 WECHAT_APPID / WECHAT_SECRET 未配置",
            extra={
                "hint": "要么在 .env 里配置 AppID/Secret，要么把前端 TARO_APP_DEV_LOGIN 设为 true 走假登录"
            },
        )
        raise AppError(ErrorCode.LOGIN_UNAVAILABLE)

    try:
        response = httpx.get(
            CODE2SESSION_URL,
            params={
                "appid": settings.wechat_appid,
                "secret": settings.wechat_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001 - 网络/协议错误统一成登录不可用
        logger.warning("code2session 请求失败", extra={"reason": type(exc).__name__})
        raise AppError(ErrorCode.LOGIN_UNAVAILABLE) from exc

    openid = data.get("openid")
    if not openid:
        logger.warning("code2session 未返回 openid", extra={"errcode": data.get("errcode")})
        raise AppError(ErrorCode.LOGIN_UNAVAILABLE)
    return str(openid)
