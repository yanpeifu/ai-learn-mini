"""结构化日志（JSON 行）+ trace id 中间件 + LLM 调用日志。"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

TRACE_ID_HEADER = "X-Trace-Id"
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)

_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "taskName",
    "message", "asctime", "trace_id",
}


class JsonFormatter(logging.Formatter):
    """一行一个 JSON，方便以后接日志平台；trace_id 自动带上。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created))
            + f".{int(record.msecs):03d}",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None) or trace_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn 默认的 access 日志与我们的请求日志重复，关掉
    logging.getLogger("uvicorn.access").disabled = True


class TraceIdMiddleware:
    """给每个请求一个 trace id（可用 X-Trace-Id 传入），并记录一条访问日志。"""

    def __init__(self, app: ASGIApp, header_name: str = TRACE_ID_HEADER) -> None:
        self.app = app
        self.header_name = header_name
        self.logger = logging.getLogger("app.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or [])
        trace_id = (incoming.get(self.header_name.lower().encode()) or b"").decode() or uuid.uuid4().hex
        token = trace_id_var.set(trace_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers.append(self.header_name, trace_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            self.logger.info(
                "request finished",
                extra={
                    "trace_id": trace_id,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_code,
                    "latency_ms": latency_ms,
                },
            )
            trace_id_var.reset(token)


def log_llm_call(
    *,
    provider: str,
    model: str,
    purpose: str,
    latency_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    estimated_cost: float | None = None,
    trace_id: str | None = None,
    success: bool = True,
    error: str | None = None,
) -> None:
    """每次大模型调用都记一条：provider / model / 耗时 / token / 估算成本。"""
    logger = logging.getLogger("app.llm")
    total = None
    if prompt_tokens is not None and completion_tokens is not None:
        total = prompt_tokens + completion_tokens
    logger.info(
        "llm call finished" if success else "llm call failed",
        extra={
            "trace_id": trace_id or trace_id_var.get(),
            "provider": provider,
            "model": model,
            "purpose": purpose,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total,
            "estimated_cost": estimated_cost,
            "success": success,
            "error": error,
        },
    )


LogHandler = Callable[..., Awaitable[None]]
