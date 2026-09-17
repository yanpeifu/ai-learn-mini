"""pytest 全局夹具：所有测试都用独立的临时 SQLite 库与 mock LLM，不联网、不花钱。"""

from pathlib import Path

import pytest
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_engine_from_settings, create_session_factory
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """测试用配置：不读 .env（避免受真实 Key 影响），数据库落在 tmp_path。"""
    return Settings(
        _env_file=None,
        env="test",
        debug=True,
        log_level="WARNING",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        llm_provider="mock",
        dev_login_enabled=True,
    )


@pytest.fixture()
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture()
def db_engine(settings: Settings):
    """每个测试一个独立的 SQLite 文件库（不用内存库，保证与迁移脚本行为一致）。"""
    engine = create_engine_from_settings(settings)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Session:
    session_factory = create_session_factory(db_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
