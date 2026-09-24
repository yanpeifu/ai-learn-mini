"""JWT 签发与校验测试。"""

import pytest
from app.core.auth import create_access_token, decode_access_token
from app.core.config import Settings
from app.core.errors import AppError


def test_token_roundtrip_returns_user_id(settings: Settings) -> None:
    token = create_access_token(42, settings)

    assert decode_access_token(token, settings) == 42


def test_expired_token_is_rejected(settings: Settings) -> None:
    expired_settings = settings.model_copy(update={"token_expire_hours": -1})
    token = create_access_token(7, expired_settings)

    with pytest.raises(AppError) as excinfo:
        decode_access_token(token, settings)

    assert excinfo.value.code == "UNAUTHORIZED"
    assert "过期" in excinfo.value.message


def test_token_signed_with_another_secret_is_rejected(settings: Settings) -> None:
    forged_settings = settings.model_copy(
        update={"token_secret": "attacker-secret-with-enough-length-32bytes"}
    )
    token = create_access_token(7, forged_settings)

    with pytest.raises(AppError) as excinfo:
        decode_access_token(token, settings)

    assert excinfo.value.code == "UNAUTHORIZED"


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
def test_garbage_tokens_are_rejected(settings: Settings, token: str) -> None:
    with pytest.raises(AppError) as excinfo:
        decode_access_token(token, settings)

    assert excinfo.value.code == "UNAUTHORIZED"


def test_token_without_subject_is_rejected(settings: Settings) -> None:
    import jwt
    from datetime import datetime, timedelta, timezone

    token = jwt.encode(
        {
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "sub": "abc",
        },
        settings.token_secret,
        algorithm=settings.token_algorithm,
    )

    with pytest.raises(AppError):
        decode_access_token(token, settings)
