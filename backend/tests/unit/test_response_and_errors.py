"""统一响应体与错误码测试。"""

import pytest
from app.core.errors import AppError, ErrorCode, error_envelope
from app.core.response import fail, ok


def test_ok_envelope_shape() -> None:
    body = ok({"status": "ok"})

    assert body == {"code": "OK", "message": "ok", "data": {"status": "ok"}}


def test_ok_envelope_allows_none_data() -> None:
    assert ok() == {"code": "OK", "message": "ok", "data": None}


def test_fail_envelope_shape() -> None:
    body = fail("INVALID_INPUT", "内容太短啦，再多描述一点（至少 20 字）")

    assert body["code"] == "INVALID_INPUT"
    assert body["message"].startswith("内容太短")
    assert body["data"] is None


def test_app_error_carries_http_status_and_code() -> None:
    error = AppError(ErrorCode.UNAUTHORIZED, "登录状态已过期，请重新进入")

    assert error.code == "UNAUTHORIZED"
    assert error.status_code == 401
    assert error_envelope(error) == {
        "code": "UNAUTHORIZED",
        "message": "登录状态已过期，请重新进入",
        "data": None,
    }


def test_user_facing_message_never_leaks_technical_detail() -> None:
    """401/402/403 这类技术细节不能出现在用户可见文案里。"""
    error = AppError(ErrorCode.LLM_UNAVAILABLE, "服务暂时不可用，请稍后再试")

    assert error.code == "LLM_UNAVAILABLE"
    assert error.status_code == 503
    assert "401" not in error.message
    assert "HTTP" not in error.message


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (ErrorCode.INVALID_INPUT, 400),
        (ErrorCode.UNAUTHORIZED, 401),
        (ErrorCode.NOT_FOUND, 404),
        (ErrorCode.QUOTA_EXCEEDED, 429),
        (ErrorCode.LLM_TIMEOUT, 504),
        (ErrorCode.LLM_UNAVAILABLE, 503),
        (ErrorCode.GENERATION_FAILED, 502),
        (ErrorCode.INTERNAL_ERROR, 500),
    ],
)
def test_error_code_http_status_mapping(code: ErrorCode, status: int) -> None:
    assert AppError(code).status_code == status
