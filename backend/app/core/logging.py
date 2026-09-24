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

#: 级别 → 中文
LEVEL_LABELS = {
    "DEBUG": "调试",
    "INFO": "信息",
    "WARNING": "警告",
    "ERROR": "错误",
    "CRITICAL": "严重",
}

#: 字段名 → 中文（日志里出现的字段都有中文名，非技术同事也能看懂）
FIELD_LABELS = {
    "trace_id": "追踪号",
    "method": "请求方法",
    "path": "接口",
    "status": "状态码",
    "latency_ms": "耗时(毫秒)",
    "env": "环境",
    "version": "版本",
    "llm_provider": "模型供应商",
    "database": "数据库",
    "provider": "模型供应商",
    "model": "模型",
    "purpose": "用途",
    "prompt_tokens": "输入token",
    "completion_tokens": "输出token",
    "total_tokens": "总token",
    "estimated_cost": "预计花费(元)",
    "success": "是否成功",
    "error": "错误",
    "error_type": "错误类型",
    "attempt": "第几次尝试",
    "max_attempts": "最多尝试次数",
    "code": "错误码",
    "reason": "原因",
    "hint": "提示",
    "task_id": "任务号",
    "outline_id": "大纲ID",
    "user_id": "用户ID",
    "stage": "阶段",
    "dropped": "丢弃题数",
    "kept": "保留题数",
    "regenerated": "重生成题数",
    "backfilled": "补题数",
    "knowledge_point": "知识点",
    "victim_question": "被替换的题目",
    "question_id": "题目ID",
    "attempt_id": "闯关ID",
    "codes": "问题类型",
}

#: 用途 → 中文
PURPOSE_LABELS = {
    "outline": "生成知识大纲",
    "levels": "生成关卡与题目",
    "repair": "重写不合格的题目",
    "backfill": "补足缺的题目",
    "smoke": "链路冒烟测试",
    "chat": "普通对话",
    "chat_json": "结构化输出",
}

#: 错误码 → 中文解释
CODE_LABELS = {
    "INVALID_INPUT": "输入内容不合法（字数或敏感词）",
    "UNAUTHORIZED": "登录状态已失效",
    "NOT_FOUND": "没找到对应的内容",
    "OUTLINE_NOT_FOUND": "找不到这个知识大纲",
    "ATTEMPT_NOT_FOUND": "找不到这次闯关记录",
    "ATTEMPT_FINISHED": "这次闯关已经结算过了",
    "QUESTION_NOT_FOUND": "找不到这道题",
    "QUOTA_EXCEEDED": "今天的使用次数已用完",
    "LLM_TIMEOUT": "模型响应太慢（超时）",
    "LLM_UNAVAILABLE": "模型服务不可用（通常是密钥或余额问题）",
    "LLM_BAD_FORMAT": "模型返回的格式不对",
    "LLM_TRANSIENT": "模型服务临时波动",
    "LLM_ERROR": "模型调用出错",
    "GENERATION_FAILED": "生成失败",
    "LOGIN_UNAVAILABLE": "登录服务不可用（未配置 AppID 或微信侧报错）",
    "INTERNAL_ERROR": "服务器内部错误",
}


def _translate(field: str, value: Any) -> Any:
    """把字段值里能翻译的翻成中文（用途、阶段、错误码）。"""
    if field == "purpose":
        return PURPOSE_LABELS.get(str(value), value)
    if field in ("code", "error_code", "codes"):
        if isinstance(value, (list, tuple)):
            return [CODE_LABELS.get(str(item), item) for item in value]
        return CODE_LABELS.get(str(value), value)
    if field == "stage":
        return {
            "calling_llm": "正在调用大模型出题",
            "saving": "正在保存关卡与题目",
            "done": "已完成",
            "failed": "已失败",
        }.get(str(value), value)
    if field == "success":
        return "成功" if value else "失败"
    if field == "error_type":
        return {
            "LLMBadFormatError": "模型返回的格式不对",
            "LLMTimeoutError": "模型响应太慢",
            "LLMTransientError": "模型服务临时波动",
            "LLMUnavailableError": "模型服务不可用",
            "AppError": "业务异常",
        }.get(str(value), value)
    return value


class HumanFormatter(logging.Formatter):
    """中文可读格式：`[时间] [级别] 消息｜字段=值｜…`（默认使用这个）"""

    def format(self, record: logging.LogRecord) -> str:
        moment = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        level = LEVEL_LABELS.get(record.levelname, record.levelname)
        head = f"[{moment}] [{level}] {record.getMessage()}"

        pieces: list[str] = []
        trace_id = getattr(record, "trace_id", None) or trace_id_var.get()
        if trace_id:
            pieces.append(f"追踪号={trace_id}")
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_") or value is None:
                continue
            pieces.append(f"{FIELD_LABELS.get(key, key)}={_translate(key, value)}")

        line = "｜".join([head, *pieces]) if pieces else head
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line

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


def configure_logging(level: str = "INFO", log_format: str = "text") -> None:
    handler = logging.StreamHandler(sys.stdout)
    # 默认中文可读格式；把 .env 的 LOG_FORMAT 设成 json 可切成机器可读格式
    handler.setFormatter(JsonFormatter() if log_format == "json" else HumanFormatter())
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
        method = scope.get("method")
        path = scope.get("path")
        self.logger.info(
            f"收到请求：{method} {path}",
            extra={"trace_id": trace_id, "method": method, "path": path},
        )

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
            if status_code < 400:
                message = f"请求处理完成：{method} {path} → {status_code}"
                level = logging.INFO
            elif status_code < 500:
                message = f"请求被拒绝：{method} {path} → {status_code}（多为参数或权限问题）"
                level = logging.WARNING
            else:
                message = f"请求处理失败：{method} {path} → {status_code}（服务端出错）"
                level = logging.ERROR
            self.logger.log(
                level,
                message,
                extra={
                    "trace_id": trace_id,
                    "method": method,
                    "path": path,
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
    purpose_cn = PURPOSE_LABELS.get(purpose, purpose)
    logger.info(
        f"大模型调用{'成功' if success else '失败'}（{purpose_cn}）",
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
