"""每日生成次数限制测试。"""

import pytest
from app.core.config import Settings
from app.core.errors import AppError
from app.repositories import (
    KnowledgeOutlineRepository,
    KnowledgeSourceRepository,
    LevelRepository,
)
from app.services.quota import ensure_levels_quota, ensure_outline_quota, today_start
from sqlalchemy.orm import Session


def _user_id(db_session: Session) -> int:
    from app.repositories import UserRepository

    return UserRepository(db_session).get_or_create_by_openid("quota-user").id


def test_outline_quota_allows_up_to_the_limit(db_session: Session, settings: Settings) -> None:
    limited = settings.model_copy(update={"daily_outline_quota": 2})
    user_id = _user_id(db_session)
    repo = KnowledgeSourceRepository(db_session)

    ensure_outline_quota(db_session, user_id, limited)
    repo.create(user_id=user_id, raw_text="知" * 30, title="第一次")
    ensure_outline_quota(db_session, user_id, limited)
    repo.create(user_id=user_id, raw_text="知" * 30, title="第二次")

    with pytest.raises(AppError) as excinfo:
        ensure_outline_quota(db_session, user_id, limited)

    assert excinfo.value.code == "QUOTA_EXCEEDED"
    assert "2 次" in excinfo.value.message


def test_levels_quota_counts_outlines_with_levels(db_session: Session, settings: Settings) -> None:
    limited = settings.model_copy(update={"daily_level_quota": 1})
    user_id = _user_id(db_session)
    source = KnowledgeSourceRepository(db_session).create(
        user_id=user_id, raw_text="知" * 30, title="大纲"
    )
    outline = KnowledgeOutlineRepository(db_session).create(
        source_id=source.id, user_id=user_id, title="大纲", points=[]
    )
    LevelRepository(db_session).create(
        outline_id=outline.id, seq=1, title="第 1 关", knowledge_point="kp1"
    )

    with pytest.raises(AppError) as excinfo:
        ensure_levels_quota(db_session, user_id, limited)

    assert excinfo.value.code == "QUOTA_EXCEEDED"


def test_today_start_is_midnight_utc(db_session: Session) -> None:  # noqa: ARG001
    start = today_start()

    assert start.hour == 0 and start.minute == 0 and start.second == 0
