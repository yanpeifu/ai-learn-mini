"""登录接口测试（PRD F7 / M4-01）。"""

from httpx import AsyncClient


async def test_dev_login_creates_user_and_returns_token(client: AsyncClient) -> None:
    response = await client.post("/api/auth/login", json={"code": "dev_player_one"})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["data"]["token"]
    assert body["data"]["user"]["nickname"] == "学习者"


async def test_same_code_maps_to_same_user(client: AsyncClient) -> None:
    first = await client.post("/api/auth/login", json={"code": "dev_same"})
    second = await client.post("/api/auth/login", json={"code": "dev_same"})
    other = await client.post("/api/auth/login", json={"code": "dev_other"})

    assert first.json()["data"]["user"]["id"] == second.json()["data"]["user"]["id"]
    assert first.json()["data"]["user"]["id"] != other.json()["data"]["user"]["id"]


async def test_login_with_empty_code_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/auth/login", json={"code": ""})

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


async def test_write_api_requires_login(client: AsyncClient) -> None:
    response = await client.post("/api/knowledge/outline", json={"raw_text": "知" * 30})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_forged_token_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/knowledge/outline",
        json={"raw_text": "知" * 30},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


async def test_templates_are_public(client: AsyncClient) -> None:
    response = await client.get("/api/templates")

    assert response.status_code == 200
    templates = response.json()["data"]["templates"]
    assert len(templates) == 6
    assert [t["name"] for t in templates][0] == "行测·资料分析"
    # 除「自定义」外，预填文案都要能直接通过 20–2000 字校验
    for template in templates[:-1]:
        assert 20 <= len(template["prefill"]) <= 2000
    assert templates[-1]["prefill"] == ""
