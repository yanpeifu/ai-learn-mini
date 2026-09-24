"""M1-01 验收：GET /api/health 返回 200 + 统一响应体。"""

from httpx import AsyncClient


async def test_health_returns_ok_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["message"] == "ok"
    assert body["data"]["status"] == "ok"
    assert body["data"]["version"]
    assert body["data"]["env"] == "test"
    assert body["data"]["llm_provider"] == "mock"


async def test_health_sets_trace_id_header(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.headers.get("X-Trace-Id")


async def test_trace_id_header_is_propagated(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Trace-Id": "trace-abc-123"})

    assert response.headers["X-Trace-Id"] == "trace-abc-123"


async def test_unknown_path_uses_unified_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert "data" in body


async def test_cors_headers_are_returned_for_h5_preview(client: AsyncClient) -> None:
    """本地 H5 预览（127.0.0.1:8100）需要跨域访问后端。"""
    response = await client.get("/api/health", headers={"Origin": "http://127.0.0.1:8100"})

    assert response.headers.get("access-control-allow-origin") == "*"
