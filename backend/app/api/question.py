"""题目反馈与人工处理（PRD M3-06 / L8 第四层兜底）。"""

from __future__ import annotations

from fastapi import APIRouter, Header

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.core.errors import AppError, ErrorCode
from app.core.response import ok
from app.repositories import (
    AttemptRepository,
    QuestionReportRepository,
    QuestionRepository,
)
from app.schemas.report import QuestionReportRequest

router = APIRouter(tags=["question"])


def _require_seen_question(db: DbSession, question_id: int, user_id: int):
    """只有真正见过这道题（有对应闯关记录）的用户才能举报它。"""
    question = QuestionRepository(db).get(question_id)
    if question is None:
        raise AppError(ErrorCode.QUESTION_NOT_FOUND)
    attempts = AttemptRepository(db).list(user_id=user_id, outline_id=question.outline_id)
    if not attempts:
        raise AppError(ErrorCode.QUESTION_NOT_FOUND)
    return question


@router.post("/questions/{question_id}/report")
def report_question(
    question_id: int,
    payload: QuestionReportRequest,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> dict:
    question = _require_seen_question(db, question_id, user.id)
    report_repo = QuestionReportRepository(db)
    report_count = report_repo.create(
        question_id=question_id,
        user_id=user.id,
        reason=payload.reason,
        detail=payload.detail,
    )
    disabled = False
    threshold = settings.report_flag_threshold
    if report_repo.is_flagged(question_id, threshold=threshold):
        # 被 ≥ N 个不同用户反馈：先下架复核，避免继续影响其他用户
        QuestionRepository(db).set_disabled(question_id, disabled=True)
        disabled = True
    return ok(
        {
            "ok": True,
            "report_count": report_count,
            "reporters": report_repo.count_pending_reporters(question_id),
            "disabled": disabled,
            "threshold": threshold,
            "question_id": question.id,
        }
    )


def _check_admin(settings: AppSettings, admin_token: str | None) -> None:
    """人工处理接口需要管理令牌；未配置 ADMIN_TOKEN 时这两个接口不暴露。"""
    if not settings.admin_token:
        raise AppError(ErrorCode.NOT_FOUND)
    if admin_token != settings.admin_token:
        raise AppError(ErrorCode.UNAUTHORIZED, "没有权限做这个操作")


@router.post("/questions/{question_id}/disable")
def disable_question(
    question_id: int,
    db: DbSession,
    settings: AppSettings,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    _check_admin(settings, x_admin_token)
    question = QuestionRepository(db).set_disabled(question_id, disabled=True)
    if question is None:
        raise AppError(ErrorCode.QUESTION_NOT_FOUND)
    QuestionReportRepository(db).mark_all_reviewed(question_id)
    return ok({"question_id": question_id, "disabled": True})


@router.post("/questions/{question_id}/enable")
def enable_question(
    question_id: int,
    db: DbSession,
    settings: AppSettings,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    _check_admin(settings, x_admin_token)
    question = QuestionRepository(db).set_disabled(question_id, disabled=False)
    if question is None:
        raise AppError(ErrorCode.QUESTION_NOT_FOUND)
    QuestionReportRepository(db).mark_all_reviewed(question_id)
    return ok({"question_id": question_id, "disabled": False})
