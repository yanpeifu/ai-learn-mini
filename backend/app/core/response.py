"""统一响应体：{code, message, data}（PRD 2.5）。"""

from __future__ import annotations

from typing import Any

OK_CODE = "OK"


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": OK_CODE, "message": message, "data": data}


def fail(code: str, message: str, data: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data}
