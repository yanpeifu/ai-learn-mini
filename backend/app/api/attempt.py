"""闯关接口：开始 / 作答 / 结算 / 记录（PRD Q1–Q6）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.core.errors import AppError, ErrorCode
from app.core.response import ok
from app.models import Attempt, Question
from app.repositories import (
    AttemptRepository,
    KnowledgeOutlineRepository,
    QuestionRepository,
)
from app.schemas.attempt import AnswerRequest, AttemptStartRequest
from app.services.attempt_service import (
    build_attempt_result,
    finish_attempt,
    get_ongoing,
    list_history,
    start_attempt,
    submit_answer,
)
from app.services.serializers import build_public_levels

router = APIRouter(tags=["attempt"])


def _get_owned_attempt(db: DbSession, attempt_id: int, user_id: int) -> Attempt:
    attempt = AttemptRepository(db).get(attempt_id)
    if attempt is None or attempt.user_id != user_id:
        raise AppError(ErrorCode.ATTEMPT_NOT_FOUND)
    return attempt


@router.post("/attempt/start")
def start(
    payload: AttemptStartRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    outline = KnowledgeOutlineRepository(db).get(payload.outline_id)
    if outline is None or outline.user_id != user.id:
        raise AppError(ErrorCode.OUTLINE_NOT_FOUND)
    attempt = start_attempt(db, user_id=user.id, outline_id=outline.id)
    return ok(
        {
            "attempt_id": attempt.id,
            "status": attempt.status,
            "total_count": attempt.total_count,
            "levels": build_public_levels(db, outline.id),
        }
    )


@router.post("/attempt/{attempt_id}/answer")
def answer(
    attempt_id: int,
    payload: AnswerRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    attempt = _get_owned_attempt(db, attempt_id, user.id)
    if attempt.status != "ongoing":
        raise AppError(ErrorCode.ATTEMPT_FINISHED)

    question = QuestionRepository(db).get(payload.question_id)
    if question is None or question.outline_id != attempt.outline_id or question.disabled_at:
        raise AppError(ErrorCode.QUESTION_NOT_FOUND)

    judgment = submit_answer(
        db,
        user_id=user.id,
        attempt=attempt,
        question=question,
        answer=payload.answer,
        elapsed_ms=payload.elapsed_ms,
    )
    return ok(
        {
            "is_correct": judgment.is_correct,
            "correct_answer": judgment.correct_answer,
            "explanation": judgment.explanation,
            "correct_count": judgment.correct_count,
            "answered_count": judgment.answered_count,
            "combo": judgment.combo,
            "already_answered": judgment.already_answered,
        }
    )


@router.post("/attempt/{attempt_id}/finish")
def finish(
    attempt_id: int, db: DbSession, user: CurrentUser, settings: AppSettings
) -> dict:
    attempt = _get_owned_attempt(db, attempt_id, user.id)
    settlement = finish_attempt(db, attempt=attempt, settings=settings)
    return ok(
        {
            **settlement.model_dump(),
            "attempt_id": attempt.id,
            "status": attempt.status,
        }
    )


@router.get("/attempt/ongoing")
def ongoing(db: DbSession, user: CurrentUser) -> dict:
    return ok({"attempt": get_ongoing(db, user_id=user.id)})


@router.get("/attempts")
def history(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
) -> dict:
    items, total = list_history(db, user_id=user.id, page=page, size=size)
    return ok(
        {
            "list": items,
            "total": total,
            "page": page,
            "size": size,
            "has_more": page * size < total,
        }
    )


@router.get("/attempt/{attempt_id}")
def detail(
    attempt_id: int, db: DbSession, user: CurrentUser, settings: AppSettings
) -> dict:
    attempt = _get_owned_attempt(db, attempt_id, user.id)
    return ok(build_attempt_result(db, attempt=attempt, settings=settings))
