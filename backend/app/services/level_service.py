"""关卡落库与出题后台任务。"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.models import KnowledgeOutline
from app.repositories import (
    KnowledgeOutlineRepository,
    LevelRepository,
    QuestionRepository,
)
from app.schemas.generation import GeneratedQuestionSet, OutlinePoint
from app.services.llm.base import LLMProvider
from app.services.question_service import generate_question_set
from app.services.search.base import SearchProvider
from app.services.search.grounding import gather_references
from app.services.search.profiles import KnowledgeTraits
from app.services.serializers import build_public_levels
from app.services.task_registry import (
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    TaskRegistry,
)

logger = logging.getLogger("app.level")


def persist_levels(db: Session, outline: KnowledgeOutline, question_set: GeneratedQuestionSet) -> None:
    """把关卡与题目写入数据库（重新出题时先清掉旧的，避免题目翻倍）。"""
    level_repo = LevelRepository(db)
    question_repo = QuestionRepository(db)
    level_repo.delete_by_outline(outline.id)

    point_titles = {point["id"]: point["title"] for point in outline.outline_json}
    grouped: dict[int, list] = {}
    for question in question_set.questions:
        grouped.setdefault(question.level_seq or 1, []).append(question)

    for seq in sorted(grouped):
        questions = grouped[seq]
        dominant_kp = Counter(q.knowledge_point_id for q in questions).most_common(1)[0][0]
        kp_title = point_titles.get(dominant_kp, dominant_kp)
        level = level_repo.create(
            outline_id=outline.id,
            seq=seq,
            title=f"第 {seq} 关 · {kp_title}"[:64],
            knowledge_point=kp_title[:128],
            question_count=len(questions),
        )
        for index, question in enumerate(questions, 1):
            question_repo.create(
                level_id=level.id,
                outline_id=outline.id,
                seq=index,
                type=question.type,
                difficulty=question.difficulty,
                stem=question.stem,
                options=[option.model_dump() for option in question.options],
                answer=list(question.answer),
                explanation=question.explanation,
                hint=question.hint.model_dump() if question.hint else None,
            )


def start_levels_task(
    *,
    registry: TaskRegistry,
    session_factory: Any,
    provider: LLMProvider,
    search_provider: SearchProvider,
    settings: Settings,
    outline_id: int,
    user_id: int,
) -> tuple[str, bool]:
    """提交出题任务：已有进行中的同类任务就直接复用（幂等）。

    返回 (task_id, reused)。
    """
    existing = registry.find_active(kind="levels", outline_id=outline_id, user_id=user_id)
    if existing is not None:
        return existing.id, True

    task = registry.create(kind="levels", outline_id=outline_id, user_id=user_id)
    thread = threading.Thread(
        target=_run_levels_task,
        kwargs={
            "registry": registry,
            "session_factory": session_factory,
            "provider": provider,
            "search_provider": search_provider,
            "settings": settings,
            "task_id": task.id,
            "outline_id": outline_id,
            "user_id": user_id,
        },
        name=f"levels-task-{task.id}",
        daemon=True,
    )
    thread.start()
    return task.id, False


def _run_levels_task(
    *,
    registry: TaskRegistry,
    session_factory: Any,
    provider: LLMProvider,
    search_provider: SearchProvider,
    settings: Settings,
    task_id: str,
    outline_id: int,
    user_id: int,
) -> None:
    """后台线程里真正干活的函数：出题 → 校验 → 落库 → 写回结果。"""
    db: Session = session_factory()
    try:
        registry.update(task_id, status=STATUS_RUNNING, stage="calling_llm")
        outline = KnowledgeOutlineRepository(db).get(outline_id)
        if outline is None:
            raise AppError(ErrorCode.OUTLINE_NOT_FOUND)

        points = [OutlinePoint(**item) for item in outline.outline_json]
        references = _gather_question_references(
            search_provider, points, settings=settings, user_id=user_id
        )
        result = generate_question_set(provider, points, settings, references=references)

        registry.update(task_id, stage="saving")
        persist_levels(db, outline, result.payload)
        db.commit()

        levels = build_public_levels(db, outline.id)
        registry.update(
            task_id,
            status=STATUS_SUCCEEDED,
            stage="done",
            result={
                "outline_id": outline.id,
                "levels": levels,
                "stats": {
                    "regenerated": result.regenerated,
                    "dropped": result.dropped,
                    "backfilled": result.backfilled,
                    "warnings": len(result.issues),
                },
            },
        )
        logger.info(
            f"出题任务完成：生成 {len(levels)} 个关卡、共 "
            f"{sum(level['question_count'] for level in levels)} 道题（题目已保存）",
            extra={"task_id": task_id, "outline_id": outline_id, "stage": "done"},
        )
    except AppError as exc:
        db.rollback()
        logger.warning(
            f"出题任务失败：{exc.message}（用户会看到对应提示，可以让 TA 重试）",
            extra={"task_id": task_id, "code": exc.code, "stage": "failed"},
        )
        registry.update(
            task_id,
            status=STATUS_FAILED,
            stage="failed",
            error_code=exc.code,
            error_message=exc.message,
        )
    except Exception as exc:  # noqa: BLE001 - 后台任务必须兜住所有异常，不能静默死掉
        db.rollback()
        logger.exception(
            "出题任务异常中断（错误已被兜住，服务继续正常运行）",
            extra={"task_id": task_id, "code": "INTERNAL_ERROR"},
        )
        registry.update(
            task_id,
            status=STATUS_FAILED,
            stage="failed",
            error_code=ErrorCode.INTERNAL_ERROR,
            error_message=f"{type(exc).__name__}",
        )
    finally:
        db.close()


def _gather_question_references(
    search_provider: SearchProvider,
    points: list[OutlinePoint],
    *,
    settings: Settings,
    user_id: int,
) -> tuple:
    """出题阶段再取一次资料。

    检索结果不落库（design.md D6），所以这里按大纲的知识点重新检索一次：
    代价是每次学习可能消耗两次检索额度，换来的是不用加表、不用数据迁移。
    取不到资料不影响出题，只是题目失去资料依据。
    """
    queries = [point.title for point in points][: settings.search_max_queries]
    grounding = gather_references(
        search_provider,
        queries=queries,
        # 出题要覆盖 15 道题，比大纲更依赖正文细节，所以固定按「复杂知识」取资料
        traits=KnowledgeTraits(complexity="complex"),
        settings=settings,
        user_id=user_id,
        purpose="levels",
    )
    return grounding.references
