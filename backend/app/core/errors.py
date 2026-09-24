"""错误码枚举 + AppError + 全局异常处理器。"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.response import fail

logger = logging.getLogger("app.error")


class ErrorCode(StrEnum):
    OK = "OK"
    INVALID_INPUT = "INVALID_INPUT"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_FOUND = "NOT_FOUND"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    OUTLINE_NOT_FOUND = "OUTLINE_NOT_FOUND"
    ATTEMPT_NOT_FOUND = "ATTEMPT_NOT_FOUND"
    ATTEMPT_FINISHED = "ATTEMPT_FINISHED"
    QUESTION_NOT_FOUND = "QUESTION_NOT_FOUND"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_BAD_FORMAT = "LLM_BAD_FORMAT"
    GENERATION_FAILED = "GENERATION_FAILED"
    LOGIN_UNAVAILABLE = "LOGIN_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_STATUS_BY_CODE: dict[str, int] = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.OUTLINE_NOT_FOUND: 404,
    ErrorCode.ATTEMPT_NOT_FOUND: 404,
    ErrorCode.QUESTION_NOT_FOUND: 404,
    ErrorCode.ATTEMPT_FINISHED: 409,
    ErrorCode.QUOTA_EXCEEDED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.GENERATION_FAILED: 502,
    ErrorCode.LOGIN_UNAVAILABLE: 503,
    ErrorCode.LLM_UNAVAILABLE: 503,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.LLM_BAD_FORMAT: 502,
}


class AppError(Exception):
    """业务异常：带上错误码与用户可见文案，技术细节只写日志。"""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str | None = None,
        *,
        data: Any = None,
        status_code: int | None = None,
    ) -> None:
        self.code = str(code)
        self.message = message or DEFAULT_MESSAGES.get(self.code, "服务开小差了，稍后再试试")
        self.data = data
        self.status_code = status_code or _STATUS_BY_CODE.get(self.code, 400)
        super().__init__(self.message)


DEFAULT_MESSAGES: dict[str, str] = {
    ErrorCode.INVALID_INPUT: "内容格式不太对，检查一下再试试",
    ErrorCode.UNAUTHORIZED: "登录状态已过期，重新进入一下小程序",
    ErrorCode.NOT_FOUND: "没有找到这个内容",
    ErrorCode.QUOTA_EXCEEDED: "今天的生成次数用完啦，明天再来",
    ErrorCode.OUTLINE_NOT_FOUND: "这个知识大纲不见了，重新生成一个吧",
    ErrorCode.ATTEMPT_NOT_FOUND: "这次闯关记录找不到了",
    ErrorCode.ATTEMPT_FINISHED: "这次闯关已经结算过啦",
    ErrorCode.QUESTION_NOT_FOUND: "这道题不见了",
    ErrorCode.LLM_TIMEOUT: "想得有点久，要不再试一次？",
    ErrorCode.LLM_UNAVAILABLE: "服务暂时不可用，请稍后再试",
    ErrorCode.LLM_BAD_FORMAT: "这次没生成成功，再试一次？",
    ErrorCode.GENERATION_FAILED: "这次没生成成功，再试一次？",
    ErrorCode.LOGIN_UNAVAILABLE: "登录服务暂时不可用，请稍后再试",
    ErrorCode.INTERNAL_ERROR: "服务开小差了，稍后再试试",
}


def error_envelope(error: AppError) -> dict[str, Any]:
    return fail(error.code, error.message, error.data)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            f"业务处理失败：{request.method} {request.url.path} → {exc.code}",
            extra={"code": exc.code, "path": request.url.path, "reason": exc.message},
        )
        return JSONResponse(status_code=exc.status_code, content=error_envelope(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.info(
            f"请求参数不符合要求：{request.method} {request.url.path}（已提示用户检查输入）",
            extra={"path": request.url.path, "codes": ["INVALID_INPUT"]},
        )
        return JSONResponse(
            status_code=400,
            content=fail(
                ErrorCode.INVALID_INPUT,
                DEFAULT_MESSAGES[ErrorCode.INVALID_INPUT],
                {"fields": [err.get("loc") for err in exc.errors()]},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = {
            401: ErrorCode.UNAUTHORIZED,
            404: ErrorCode.NOT_FOUND,
        }.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = DEFAULT_MESSAGES[code] if isinstance(code, ErrorCode) else "请求失败"
        return JSONResponse(
            status_code=exc.status_code, content=fail(code, message)
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            f"服务端未预期的错误：{request.method} {request.url.path}"
            "（已给用户友好提示，技术细节见下方堆栈）",
            extra={"path": request.url.path, "code": "INTERNAL_ERROR"},
        )
        return JSONResponse(
            status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR])
        )
