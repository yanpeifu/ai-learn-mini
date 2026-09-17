"""引擎与会话管理。

- 开发期 SQLite（单文件），生产 PostgreSQL，切换只改 DATABASE_URL；
- SQLite 打开外键约束（默认是关的，很容易埋坑）；
- FastAPI 依赖 get_db 负责「成功提交、异常回滚、最后关闭」。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:  # noqa: ARG001
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine_from_settings(settings: Settings) -> Engine:
    url = settings.database_url
    kwargs: dict[str, Any] = {"echo": settings.db_echo, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI 依赖：请求成功则提交，抛异常则回滚，最后一定关闭。"""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
