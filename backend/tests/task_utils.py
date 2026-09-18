"""生成任务的测试辅助：提交后轮询到终态。"""

from __future__ import annotations

import asyncio
import time
from typing import Any


async def wait_for_task(client: Any, task_id: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        response = await client.get(f"/api/generation/tasks/{task_id}")
        assert response.status_code == 200, response.text
        last = response.json()["data"]
        if last["status"] in ("succeeded", "failed"):
            return last
        await asyncio.sleep(0.02)
    raise AssertionError(f"任务在 {timeout}s 内未完成：{last}")


async def enqueue_levels(client: Any, outline_id: int) -> dict:
    """提交出题任务并等到终态，返回任务数据（含 result）。"""
    response = await client.post("/api/knowledge/levels", json={"outline_id": outline_id})
    assert response.status_code == 200, response.text
    return await wait_for_task(client, response.json()["data"]["task_id"])
