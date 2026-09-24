"""进程内的生成任务表（后台任务 + 前端轮询机制）。

为什么需要它：出题要等大模型 40 秒左右，如果把这 40 秒压在 HTTP 请求里，
一旦链路不稳定（本地联调的内网穿透隧道会周期性重置、手机切后台、iOS 杀后台请求）
请求就断了，而钱已经花了。改成「提交 → 立即返回任务号 → 前端每秒查进度」后：
- 每个请求都是毫秒级，隧道/超时/切后台都打不断真正的生成过程；
- 同一个大纲重复点「开始闯关」会复用同一个任务，不会重复扣费。

注意：任务表在进程内存里（MVP 够用）。服务重启后未完成的任务会丢失，
用户重新点一次即可；要跨重启恢复就得落库，那是 V0.5 的事。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.db.types import utcnow

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

TERMINAL_STATUSES = {STATUS_SUCCEEDED, STATUS_FAILED}
MAX_KEPT_TASKS = 200


@dataclass
class GenerationTask:
    id: str
    kind: str  # "levels"
    outline_id: int
    user_id: int
    status: str = STATUS_QUEUED
    stage: str = ""
    error_code: str | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def to_payload(self) -> dict[str, Any]:
        return {
            "task_id": self.id,
            "kind": self.kind,
            "outline_id": self.outline_id,
            "status": self.status,
            "stage": self.stage,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "result": self.result,
        }


class TaskRegistry:
    """线程安全的任务表（出题跑在后台线程里）。"""

    def __init__(self) -> None:
        self._tasks: dict[str, GenerationTask] = {}
        self._lock = threading.Lock()

    def create(self, *, kind: str, outline_id: int, user_id: int) -> GenerationTask:
        task = GenerationTask(
            id=uuid.uuid4().hex[:16], kind=kind, outline_id=outline_id, user_id=user_id
        )
        with self._lock:
            self._tasks[task.id] = task
            self._prune_locked()
        return task

    def get(self, task_id: str) -> GenerationTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def find_active(self, *, kind: str, outline_id: int, user_id: int) -> GenerationTask | None:
        """找一个仍在进行中的同类任务（用于幂等：重复点击不会重复扣费）。"""
        with self._lock:
            for task in self._tasks.values():
                if (
                    task.kind == kind
                    and task.outline_id == outline_id
                    and task.user_id == user_id
                    and task.status not in TERMINAL_STATUSES
                ):
                    return task
        return None

    def update(self, task_id: str, **fields: Any) -> GenerationTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            for key, value in fields.items():
                setattr(task, key, value)
            task.updated_at = utcnow()
            return task

    def _prune_locked(self) -> None:
        if len(self._tasks) <= MAX_KEPT_TASKS:
            return
        finished = sorted(
            (task for task in self._tasks.values() if task.status in TERMINAL_STATUSES),
            key=lambda task: task.updated_at,
        )
        for task in finished[: len(self._tasks) - MAX_KEPT_TASKS]:
            self._tasks.pop(task.id, None)
