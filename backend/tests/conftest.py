"""pytest 全局夹具：所有测试都用独立的临时 SQLite 库与 mock LLM，不联网、不花钱。"""

from pathlib import Path

import pytest
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_engine_from_settings, create_session_factory
from app.main import create_app
from app.repositories import (
    KnowledgeOutlineRepository,
    KnowledgeSourceRepository,
    LevelRepository,
    QuestionRepository,
    UserRepository,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session
from tests.fakes import ScriptedProvider, make_question_set, outline_points


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
def provider() -> ScriptedProvider:
    """假模型：测试里往 provider.responses 里塞数据即可（零网络零成本）。"""
    return ScriptedProvider([])


@pytest.fixture()
def app(settings: Settings, provider: ScriptedProvider):
    application = create_app(settings, provider=provider)
    # 生产用 alembic 迁移建表；测试里直接按 metadata 建表更快
    Base.metadata.create_all(application.state.db_engine)
    return application


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture()
async def auth_client(client: AsyncClient) -> AsyncClient:
    """已登录的客户端：带 Authorization 头。"""
    response = await client.post("/api/auth/login", json={"code": "dev_conftest_user"})
    assert response.status_code == 200, response.text
    token = response.json()["data"]["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


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


@pytest.fixture()
def quiz_setup(db_session: Session):
    """建一个用户 + 大纲 + 3 关 × 5 题，返回各类 id，供答题类测试直接使用。"""
    user = UserRepository(db_session).get_or_create_by_openid("quiz-user")
    source = KnowledgeSourceRepository(db_session).create(
        user_id=user.id,
        raw_text="存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例。" * 2,
        title="货币政策",
    )
    outline = KnowledgeOutlineRepository(db_session).create(
        source_id=source.id,
        user_id=user.id,
        title="货币政策三大工具",
        points=outline_points(),
    )
    payload = make_question_set()
    level_repo = LevelRepository(db_session)
    question_repo = QuestionRepository(db_session)
    levels: list[tuple] = []
    for seq in range(1, 4):
        level = level_repo.create(
            outline_id=outline.id, seq=seq, title=f"第 {seq} 关", knowledge_point="货币政策"
        )
        questions = []
        for item in payload["questions"][(seq - 1) * 5 : seq * 5]:
            questions.append(
                question_repo.create(
                    level_id=level.id,
                    outline_id=outline.id,
                    seq=int(item["id"][1:]),
                    type=item["type"],
                    difficulty=item["difficulty"],
                    stem=item["stem"],
                    options=item["options"],
                    answer=item["answer"],
                    explanation=item["explanation"],
                )
            )
        levels.append((level, questions))
    return {"user": user, "outline": outline, "levels": levels}
