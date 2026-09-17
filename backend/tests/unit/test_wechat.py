"""微信登录换取 openid 的测试（真实链路用 monkeypatch 打桩，不联网）。"""

import pytest
from app.core.config import Settings
from app.core.errors import AppError
from app.services.wechat import dev_openid, is_dev_code, resolve_openid


def test_dev_code_maps_to_stable_openid(settings: Settings) -> None:
    assert is_dev_code("dev_abc")
    first = resolve_openid("dev_abc", settings)
    second = resolve_openid("dev_abc", settings)

    assert first == second == dev_openid("dev_abc")
    assert first.startswith("dev_")


def test_dev_code_is_rejected_when_switch_is_off(settings: Settings) -> None:
    strict = settings.model_copy(update={"dev_login_enabled": False})

    with pytest.raises(AppError) as excinfo:
        resolve_openid("dev_abc", strict)

    assert excinfo.value.code == "LOGIN_UNAVAILABLE"


def test_missing_code_is_invalid_input(settings: Settings) -> None:
    with pytest.raises(AppError) as excinfo:
        resolve_openid(None, settings)

    assert excinfo.value.code == "INVALID_INPUT"


def test_real_code_without_appid_is_login_unavailable(settings: Settings) -> None:
    with pytest.raises(AppError) as excinfo:
        resolve_openid("real-code", settings)

    assert excinfo.value.code == "LOGIN_UNAVAILABLE"


def test_real_code_uses_code2session(settings: Settings, monkeypatch) -> None:
    configured = settings.model_copy(
        update={"wechat_appid": "wx-app", "wechat_secret": "wx-secret"}
    )

    class _Response:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"openid": "o-real-openid", "session_key": "sk"}

    captured: dict = {}

    def fake_get(url, params=None, timeout=None):  # noqa: ANN001, ARG001
        captured["url"] = url
        captured["params"] = params
        return _Response()

    monkeypatch.setattr("app.services.wechat.httpx.get", fake_get)

    assert resolve_openid("real-code", configured) == "o-real-openid"
    assert captured["params"]["js_code"] == "real-code"
    assert captured["params"]["appid"] == "wx-app"


def test_code2session_error_is_login_unavailable(settings: Settings, monkeypatch) -> None:
    configured = settings.model_copy(
        update={"wechat_appid": "wx-app", "wechat_secret": "wx-secret"}
    )

    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"errcode": 40029, "errmsg": "invalid code"}

    monkeypatch.setattr(
        "app.services.wechat.httpx.get", lambda *args, **kwargs: _Response()
    )

    with pytest.raises(AppError) as excinfo:
        resolve_openid("bad-code", configured)

    assert excinfo.value.code == "LOGIN_UNAVAILABLE"
