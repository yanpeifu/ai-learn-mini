"""首页快捷模板（PRD F1：6 个固定模板）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.constants.templates import TEMPLATES
from app.core.response import ok

router = APIRouter(tags=["templates"])


@router.get("/templates")
def list_templates() -> dict:
    return ok({"templates": TEMPLATES})
