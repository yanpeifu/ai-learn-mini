"""跨数据库的自定义类型。

UTCDateTime：SQLite 不保存时区，PostgreSQL 保存。这里统一成「写进去是 UTC、读出来带 UTC 时区」，
避免开发期（SQLite）与生产（PostgreSQL）行为不一致导致的时间比较 bug。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:  # noqa: ARG002
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Any, dialect: Any) -> Any:  # noqa: ARG002
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    """业务代码统一用它取当前时间（带 UTC 时区）。"""
    return datetime.now(timezone.utc)


# 开发期 SQLite 用 JSON，生产 PostgreSQL 自动升级为 JSONB
JSONVariant = JSON().with_variant(JSONB(), "postgresql")
