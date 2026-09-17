"""举报与「我的」页接口测试（PRD M3-06 / F6）。"""

from app.core.config import Settings
from app.main import create_app
from app.repositories import QuestionReportRepository, QuestionRepository, UserRepository
from httpx import ASGITransport, AsyncClient
from tests.fakes import ScriptedProvider, make_question_set, outline_payload

VALID_TEXT = "存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例，提高准备金率会减少可放贷资金。"


async def _prepare_attempt(auth_client: AsyncClient, provider: ScriptedProvider) -> dict:
    provider.responses.append(outline_payload())
    created = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
    outline_id = created.json()["data"]["outline_id"]
    provider.responses.append(make_question_set())
    await auth_client.post("/api/knowledge/levels", json={"outline_id": outline_id})
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    return start.json()["data"]


async def test_report_question_records_feedback(
    auth_client: AsyncClient, provider: ScriptedProvider
) -> None:
    attempt = await _prepare_attempt(auth_client, provider)
    question_id = attempt["levels"][0]["questions"][0]["id"]

    response = await auth_client.post(
        f"/api/questions/{question_id}/report",
        json={"reason": "wrong_answer", "detail": "答案好像不对"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is True
    assert data["report_count"] == 1
    assert data["disabled"] is False
    assert data["threshold"] == 3


async def test_report_requires_having_seen_the_question(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    attempt = await _prepare_attempt(auth_client, provider)
    question_id = attempt["levels"][0]["questions"][0]["id"]
    # 把举报人换成另一个用户：他没做过这套题，不允许举报
    other = UserRepository(db_session).get_or_create_by_openid("never-seen-user")

    from app.api.question import _require_seen_question
    from app.core.errors import AppError

    try:
        _require_seen_question(db_session, question_id, other.id)
    except AppError as exc:
        assert exc.code == "QUESTION_NOT_FOUND"
    else:  # pragma: no cover
        raise AssertionError("未见过题目的用户不应该能举报")


async def test_invalid_reason_is_rejected(auth_client: AsyncClient, provider: ScriptedProvider) -> None:
    attempt = await _prepare_attempt(auth_client, provider)
    question_id = attempt["levels"][0]["questions"][0]["id"]

    response = await auth_client.post(
        f"/api/questions/{question_id}/report", json={"reason": "not-a-reason"}
    )

    assert response.status_code == 400


async def test_question_is_disabled_after_enough_distinct_reporters(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    """MVP 里每套题只属于生成它的用户，所以这里用仓储层补足「其他举报人」来验证阈值逻辑。"""
    attempt = await _prepare_attempt(auth_client, provider)
    question_id = attempt["levels"][0]["questions"][0]["id"]
    report_repo = QuestionReportRepository(db_session)
    for index in range(2):
        reporter = UserRepository(db_session).get_or_create_by_openid(f"reporter-{index}")
        report_repo.create(question_id=question_id, user_id=reporter.id, reason="unclear")
    db_session.commit()

    response = await auth_client.post(
        f"/api/questions/{question_id}/report", json={"reason": "unclear"}
    )
    detail = await auth_client.get(f"/api/attempt/{attempt['attempt_id']}")

    assert response.json()["data"]["disabled"] is True
    assert response.json()["data"]["reporters"] == 3
    # 下线后的题不再下发
    served_ids = [
        question["id"]
        for level in detail.json()["data"]["levels"]
        for question in level["questions"]
    ]
    assert question_id not in served_ids


async def test_admin_can_disable_and_enable_question(db_session, provider: ScriptedProvider) -> None:  # noqa: ANN001
    settings = Settings(
        _env_file=None,
        env="test",
        log_level="WARNING",
        database_url="sqlite:///:memory:",
        llm_provider="mock",
        dev_login_enabled=True,
        admin_token="admin-secret",
    )
    from app.db.base import Base

    app = create_app(settings, provider=provider)
    Base.metadata.create_all(app.state.db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post("/api/auth/login", json={"code": "dev_admin_case"})
        client.headers["Authorization"] = f"Bearer {login.json()['data']['token']}"
        attempt = await _prepare_attempt(client, provider)
        question_id = attempt["levels"][0]["questions"][0]["id"]

        forbidden = await client.post(f"/api/questions/{question_id}/disable")
        disabled = await client.post(
            f"/api/questions/{question_id}/disable", headers={"X-Admin-Token": "admin-secret"}
        )
        enabled = await client.post(
            f"/api/questions/{question_id}/enable", headers={"X-Admin-Token": "admin-secret"}
        )

    assert forbidden.status_code == 401
    assert disabled.status_code == 200
    assert enabled.json()["data"]["disabled"] is False


async def test_admin_endpoints_are_hidden_without_token(auth_client: AsyncClient) -> None:
    response = await auth_client.post("/api/questions/1/disable")

    assert response.status_code == 404


async def test_user_stats_starts_at_zero(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/user/stats")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["study_count"] == 0
    assert data["answered_count"] == 0
    assert data["avg_accuracy"] == 0.0
    assert data["study_days"] == 0
    assert data["streak_days"] == 0


async def test_user_stats_after_finishing_a_run(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    attempt = await _prepare_attempt(auth_client, provider)
    for level in attempt["levels"]:
        for item in level["questions"]:
            question = QuestionRepository(db_session).get(item["id"])
            await auth_client.post(
                f"/api/attempt/{attempt['attempt_id']}/answer",
                json={
                    "question_id": question.id,
                    "answer": list(question.answer_json),
                    "elapsed_ms": 2000,
                },
            )
    await auth_client.post(f"/api/attempt/{attempt['attempt_id']}/finish")

    response = await auth_client.get("/api/user/stats")

    data = response.json()["data"]
    assert data["study_count"] == 1
    assert data["answered_count"] == 15
    assert data["avg_accuracy"] == 100.0
    assert data["study_days"] == 1
    assert data["streak_days"] == 1
