"""答题判定、结算与学习记录（PRD F4 / F5 / F6）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.models import AnswerRecord, Attempt, Level, Question
from app.repositories import (
    AnswerRecordRepository,
    AttemptRepository,
    KnowledgeOutlineRepository,
    LevelRepository,
    MistakeRepository,
    QuestionRepository,
)
from app.schemas.attempt import LevelScore, Settlement
from app.services.serializers import to_public_question

logger = logging.getLogger("app.attempt")

STAR_THREE = 90.0
STAR_TWO = 70.0
STAR_ONE = 50.0


@dataclass
class Judgment:
    is_correct: bool
    correct_answer: list[str]
    explanation: str
    correct_count: int
    answered_count: int
    combo: int
    already_answered: bool = False


def normalize_answer(keys: list[str]) -> set[str]:
    return {str(key).strip().upper() for key in keys if str(key).strip()}


def judge(question: Question, answer: list[str]) -> bool:
    """单选 / 判断：完全一致；多选：**全对才算对，不设部分得分**（PRD F4）。"""
    return normalize_answer(answer) == normalize_answer(question.answer_json or [])


def star_for(accuracy: float) -> int:
    """星级规则（PRD F5）：≥90 三星 / 70–89 两星 / 50–69 一星 / <50 零星。"""
    if accuracy >= STAR_THREE:
        return 3
    if accuracy >= STAR_TWO:
        return 2
    if accuracy >= STAR_ONE:
        return 1
    return 0


def start_attempt(db: Session, *, user_id: int, outline_id: int) -> Attempt:
    """开始一次闯关；同一用户其它未完成的闯关会被标记为 abandoned。"""
    question_ids = [
        question.id
        for question in QuestionRepository(db).list_by_outline(outline_id)
        if question.disabled_at is None
    ]
    if not question_ids:
        raise AppError(ErrorCode.GENERATION_FAILED, "这个大纲还没有题目，先出题吧")
    attempt = AttemptRepository(db).create(
        user_id=user_id, outline_id=outline_id, total_count=len(question_ids)
    )
    AttemptRepository(db).abandon_others(user_id, attempt.id)
    return attempt


def submit_answer(
    db: Session,
    *,
    user_id: int,
    attempt: Attempt,
    question: Question,
    answer: list[str],
    elapsed_ms: int,
) -> Judgment:
    """提交单题作答。幂等：同一题重复提交返回首次判定，不重复计数、不覆盖记录。"""
    record_repo = AnswerRecordRepository(db)
    existing = record_repo.get_by_attempt_question(attempt.id, question.id)
    if existing is not None:
        logger.info(
            "duplicated answer ignored",
            extra={"attempt_id": attempt.id, "question_id": question.id},
        )
        return Judgment(
            is_correct=existing.is_correct,
            correct_answer=list(question.answer_json or []),
            explanation=question.explanation,
            correct_count=attempt.correct_count,
            answered_count=record_repo.count_by_attempt(attempt.id),
            combo=_trailing_combo(db, attempt.id),
            already_answered=True,
        )

    is_correct = judge(question, answer)
    record_repo.create(
        attempt_id=attempt.id,
        question_id=question.id,
        user_id=user_id,
        answer=list(answer),
        is_correct=is_correct,
        elapsed_ms=elapsed_ms,
    )
    if is_correct:
        attempt.correct_count += 1
    else:
        # 答错的题进错题池（MVP 只落库，界面在 V0.5）
        MistakeRepository(db).record_wrong(user_id, question.id)
    db.flush()

    return Judgment(
        is_correct=is_correct,
        correct_answer=list(question.answer_json or []),
        explanation=question.explanation,
        correct_count=attempt.correct_count,
        answered_count=record_repo.count_by_attempt(attempt.id),
        combo=_trailing_combo(db, attempt.id),
    )


def _trailing_combo(db: Session, attempt_id: int) -> int:
    """末尾连续答对的题数（用于前端「连对 3 题」的即时反馈）。"""
    combo = 0
    for record in reversed(list(AnswerRecordRepository(db).list_by_attempt(attempt_id))):
        if not record.is_correct:
            break
        combo += 1
    return combo


def finish_attempt(db: Session, *, attempt: Attempt, settings: Settings) -> Settlement:
    """结算：正确率、星级、各知识点表现、薄弱点与建议（幂等）。"""
    settlement = build_settlement(db, attempt=attempt, settings=settings)
    if attempt.status != "finished":
        AttemptRepository(db).finish(
            attempt.id,
            correct_count=settlement.correct_count,
            accuracy=Decimal(str(settlement.accuracy)),
            duration_ms=settlement.duration_ms,
            star=settlement.star,
        )
    return settlement


def build_settlement(db: Session, *, attempt: Attempt, settings: Settings) -> Settlement:
    records = AnswerRecordRepository(db).list_by_attempt(attempt.id)
    questions = {
        question.id: question
        for question in QuestionRepository(db).list_by_outline(attempt.outline_id)
    }
    levels = LevelRepository(db).list_by_outline(attempt.outline_id)
    answered_ids = {record.question_id for record in records}
    correct_ids = {record.question_id for record in records if record.is_correct}

    total_count = attempt.total_count or len(questions)
    correct_count = sum(1 for record in records if record.is_correct)
    accuracy = _round_accuracy(correct_count, total_count)
    duration_ms = sum(record.elapsed_ms or 0 for record in records)

    points = _level_scores(levels, questions, answered_ids, correct_ids)
    weak_points = [
        point for point in points if point.total and point.accuracy < settings.weak_point_threshold
    ][:3]

    return Settlement(
        accuracy=accuracy,
        star=star_for(accuracy),
        duration_ms=duration_ms,
        correct_count=correct_count,
        total_count=total_count,
        points=points,
        weak_points=weak_points,
        advice=build_advice(
            accuracy=accuracy,
            correct_count=correct_count,
            total_count=total_count,
            weak_points=weak_points,
        ),
    )


def _round_accuracy(correct: int, total: int) -> float:
    if total <= 0:
        return 0.0
    value = Decimal(correct) / Decimal(total) * 100
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _level_scores(
    levels: list[Level],
    questions: dict[int, Question],
    answered_ids: set[int],
    correct_ids: set[int],
) -> list[LevelScore]:
    scores: list[LevelScore] = []
    for level in levels:
        level_questions = [q for q in questions.values() if q.level_id == level.id]
        total = len(level_questions)
        answered = [q for q in level_questions if q.id in answered_ids]
        correct = [q for q in answered if q.id in correct_ids]
        scores.append(
            LevelScore(
                level_seq=level.seq,
                title=level.title,
                knowledge_point=level.knowledge_point,
                total=total,
                correct=len(correct),
                accuracy=_round_accuracy(len(correct), len(answered) or total),
            )
        )
    return scores


def build_advice(
    *,
    accuracy: float,
    correct_count: int,
    total_count: int,
    weak_points: list[LevelScore],
) -> str:
    """PRD F5 的文案要求：不只给数字，要给一句有指向性的建议。"""
    # 低分（0 星）先安抚，把落点引向错题（原型 P4-2 的文案语气）
    if accuracy < STAR_ONE:
        return (
            f"这块内容本来就不好啃，你已经答对了 {correct_count} / {total_count} 道，"
            "先看看错题再学一遍"
        )
    if weak_points:
        weakest = weak_points[0]
        return (
            f"你在「{weakest.knowledge_point}」上正确率 {weakest.accuracy:g}%，"
            "建议重点复习这一块"
        )
    if accuracy >= STAR_THREE:
        return "这次表现很棒，这块内容你已经掌握了，可以试试更难的知识点"
    if accuracy >= STAR_TWO:
        return "整体不错，把错的几道题再过一遍就更稳了"
    return "再把这几个知识点过一遍，下一次会更好"


def build_attempt_result(
    db: Session, *, attempt: Attempt, settings: Settings
) -> dict:
    """只读回看用：结算数据 + 每道题用户的选择（含讲解）。"""
    settlement = build_settlement(db, attempt=attempt, settings=settings)
    records = {
        record.question_id: record
        for record in AnswerRecordRepository(db).list_by_attempt(attempt.id)
    }
    # 只有「已作答的题」或「已结算的闯关」才返回答案与讲解：
    # 否则用户抓包就能拿到未作答题目 的正确答案（PRD 2.5 接口设计要求第 3 条）。
    reveal_all = attempt.status == "finished"
    levels = build_public_levels_with_answers(
        db, attempt.outline_id, records, reveal_all=reveal_all
    )
    outline = KnowledgeOutlineRepository(db).get(attempt.outline_id)
    return {
        "attempt": {
            "id": attempt.id,
            "outline_id": attempt.outline_id,
            "title": outline.title if outline else "",
            "status": attempt.status,
            "started_at": attempt.started_at.isoformat(),
            "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
        },
        "settlement": settlement.model_dump(),
        "levels": levels,
    }


def build_public_levels_with_answers(
    db: Session,
    outline_id: int,
    records: dict[int, AnswerRecord],
    *,
    reveal_all: bool = True,
) -> list[dict]:
    levels = LevelRepository(db).list_by_outline(outline_id)
    question_repo = QuestionRepository(db)
    payload: list[dict] = []
    for level in levels:
        questions = [
            question
            for question in question_repo.list_by_level(level.id)
            if question.disabled_at is None
        ]
        items = []
        for question in questions:
            record = records.get(question.id)
            item = to_public_question(question)
            answered = record is not None
            reveal = answered or reveal_all
            item.update(
                {
                    "user_answer": list(record.user_answer_json) if record else [],
                    "is_correct": bool(record.is_correct) if record else None,
                    "answered": answered,
                    "correct_answer": list(question.answer_json or []) if reveal else [],
                    "explanation": question.explanation if reveal else "",
                }
            )
            items.append(item)
        payload.append(
            {
                "id": level.id,
                "seq": level.seq,
                "title": level.title,
                "knowledge_point": level.knowledge_point,
                "question_count": len(items),
                "questions": items,
            }
        )
    return payload


def list_history(
    db: Session, *, user_id: int, page: int = 1, size: int = 20
) -> tuple[list[dict], int]:
    attempt_repo = AttemptRepository(db)
    total = attempt_repo.count(user_id=user_id, status="finished")
    offset = max(0, (page - 1) * size)
    attempts = attempt_repo.list_by_user(user_id, limit=size, offset=offset)
    outline_repo = KnowledgeOutlineRepository(db)
    items: list[dict] = []
    for attempt in attempts:
        outline = outline_repo.get(attempt.outline_id)
        items.append(
            {
                "attempt_id": attempt.id,
                "outline_id": attempt.outline_id,
                "title": outline.title if outline else "",
                "accuracy": float(attempt.accuracy) if attempt.accuracy is not None else 0.0,
                "star": attempt.star or 0,
                "correct_count": attempt.correct_count,
                "total_count": attempt.total_count,
                "duration_ms": attempt.duration_ms or 0,
                "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
            }
        )
    return items, total


def get_ongoing(db: Session, *, user_id: int) -> dict | None:
    attempt = AttemptRepository(db).get_ongoing(user_id)
    if attempt is None:
        return None
    outline = KnowledgeOutlineRepository(db).get(attempt.outline_id)
    records = AnswerRecordRepository(db).list_by_attempt(attempt.id)
    answered_ids = [record.question_id for record in records]
    questions = [
        question
        for level in LevelRepository(db).list_by_outline(attempt.outline_id)
        for question in QuestionRepository(db).list_by_level(level.id)
        if question.disabled_at is None
    ]
    ordered_ids = [question.id for question in questions]
    answered_count = len([qid for qid in ordered_ids if qid in answered_ids])
    next_question_id = next((qid for qid in ordered_ids if qid not in answered_ids), None)
    return {
        "attempt_id": attempt.id,
        "outline_id": attempt.outline_id,
        "title": outline.title if outline else "",
        "total_count": attempt.total_count,
        "answered_count": answered_count,
        "next_question_id": next_question_id,
    }
