"""知识大纲与出题接口测试（PRD K1–K4）。"""

import json

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.services.llm.base import LLMBadFormatError
from httpx import ASGITransport, AsyncClient
from tests.fakes import ScriptedProvider, make_question_set, outline_payload

VALID_TEXT = "存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例，提高准备金率会减少可放贷资金。"


async def test_generate_outline_saves_source_and_outline(auth_client: AsyncClient, provider) -> None:  # noqa: ANN001
    provider.responses.append(outline_payload())

    response = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["outline_id"] > 0
    assert len(data["points"]) == 3
    assert data["title"] == "货币政策三大工具"


async def test_short_text_is_rejected_without_calling_model(auth_client: AsyncClient, provider) -> None:  # noqa: ANN001
    response = await auth_client.post("/api/knowledge/outline", json={"raw_text": "太短"})

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"
    assert provider.calls == []


async def test_llm_bad_format_maps_to_error_code(auth_client: AsyncClient, provider) -> None:  # noqa: ANN001
    provider.responses.extend([LLMBadFormatError("坏 JSON")] * 3)

    response = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})

    assert response.status_code == 502
    assert response.json()["code"] == "LLM_BAD_FORMAT"


async def test_daily_quota_is_enforced(settings: Settings, provider: ScriptedProvider) -> None:
    limited = settings.model_copy(update={"daily_outline_quota": 1})
    app = create_app(limited, provider=provider)
    from app.db.base import Base

    Base.metadata.create_all(app.state.db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post("/api/auth/login", json={"code": "dev_quota_user"})
        client.headers["Authorization"] = f"Bearer {login.json()['data']['token']}"
        provider.responses.append(outline_payload())
        first = await client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
        provider.responses.append(outline_payload())
        second = await client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == "QUOTA_EXCEEDED"


async def test_save_outline_points(auth_client: AsyncClient, provider: ScriptedProvider) -> None:
    provider.responses.append(outline_payload())
    first = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
    outline_id = first.json()["data"]["outline_id"]

    response = await auth_client.put(
        f"/api/knowledge/outline/{outline_id}",
        json={
            "points": [
                {"id": "kp1", "title": "改过的标题", "summary": "说明一"},
                {"id": "kp2", "title": "第二个知识点", "summary": "说明二"},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["ok"] is True
    detail = await auth_client.get(f"/api/knowledge/outline/{outline_id}")
    assert detail.json()["data"]["points"][0]["title"] == "改过的标题"


async def test_save_outline_requires_at_least_two_points(
    auth_client: AsyncClient, provider: ScriptedProvider
) -> None:
    provider.responses.append(outline_payload())
    first = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
    outline_id = first.json()["data"]["outline_id"]

    response = await auth_client.put(
        f"/api/knowledge/outline/{outline_id}",
        json={"points": [{"id": "kp1", "title": "只剩一个", "summary": "说明"}]},
    )

    assert response.status_code == 400


async def test_other_users_outline_is_not_visible(
    auth_client: AsyncClient, client: AsyncClient, provider: ScriptedProvider
) -> None:
    provider.responses.append(outline_payload())
    first = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
    outline_id = first.json()["data"]["outline_id"]
    login = await client.post("/api/auth/login", json={"code": "dev_another_user"})
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

    response = await client.get(f"/api/knowledge/outline/{outline_id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "OUTLINE_NOT_FOUND"


async def test_generate_levels_returns_15_questions_without_answers(
    auth_client: AsyncClient, provider: ScriptedProvider
) -> None:
    provider.responses.append(outline_payload())
    created = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
    outline_id = created.json()["data"]["outline_id"]
    provider.responses.append(make_question_set())

    response = await auth_client.post("/api/knowledge/levels", json={"outline_id": outline_id})

    assert response.status_code == 200
    levels = response.json()["data"]["levels"]
    assert [level["seq"] for level in levels] == [1, 2, 3]
    assert [level["question_count"] for level in levels] == [5, 5, 5]
    raw = json.dumps(response.json(), ensure_ascii=False)
    assert "answer" not in raw
    assert "explanation" not in raw
    assert "正确答案" not in raw


async def test_regenerating_levels_does_not_duplicate_questions(
    auth_client: AsyncClient, provider: ScriptedProvider
) -> None:
    provider.responses.append(outline_payload())
    created = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
    outline_id = created.json()["data"]["outline_id"]
    provider.responses.extend([make_question_set(), make_question_set()])

    await auth_client.post("/api/knowledge/levels", json={"outline_id": outline_id})
    second = await auth_client.post("/api/knowledge/levels", json={"outline_id": outline_id})
    detail = await auth_client.get(f"/api/knowledge/outline/{outline_id}")

    assert second.status_code == 200
    levels = detail.json()["data"]["levels"]
    assert len(levels) == 3
    assert sum(level["question_count"] for level in levels) == 15


async def test_levels_for_unknown_outline_returns_404(auth_client: AsyncClient) -> None:
    response = await auth_client.post("/api/knowledge/levels", json={"outline_id": 99999})

    assert response.status_code == 404
