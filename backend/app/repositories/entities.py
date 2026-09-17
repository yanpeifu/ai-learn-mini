"""九张表的具体数据访问对象。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select

from app.db.types import utcnow
from app.models import (
    AnswerRecord,
    Attempt,
    KnowledgeOutline,
    KnowledgeSource,
    Level,
    Mistake,
    Question,
    QuestionReport,
    User,
)
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_openid(self, openid: str) -> User | None:
        return self.session.execute(
            select(User).where(User.openid == openid)
        ).scalar_one_or_none()

    def get_or_create_by_openid(self, openid: str, nickname: str = "学习者") -> User:
        """登录时调用：没有就建号，有就刷新最近登录时间（静默登录，用户无感知）。"""
        user = self.get_by_openid(openid)
        now = utcnow()
        if user is None:
            return self.add(User(openid=openid, nickname=nickname, last_login_at=now))
        user.last_login_at = now
        self.session.flush()
        return user


class KnowledgeSourceRepository(BaseRepository[KnowledgeSource]):
    model = KnowledgeSource

    def create(
        self,
        *,
        user_id: int,
        raw_text: str,
        title: str | None = None,
        input_type: str = "text",
    ) -> KnowledgeSource:
        return self.add(
            KnowledgeSource(
                user_id=user_id,
                input_type=input_type,
                raw_text=raw_text,
                title=(title or raw_text[:20]),
                char_count=len(raw_text),
            )
        )

    def count_since(self, user_id: int, since: datetime) -> int:
        return int(
            self.session.execute(
                select(func.count())
                .select_from(KnowledgeSource)
                .where(
                    KnowledgeSource.user_id == user_id,
                    KnowledgeSource.created_at >= since,
                )
            ).scalar_one()
        )


class KnowledgeOutlineRepository(BaseRepository[KnowledgeOutline]):
    model = KnowledgeOutline

    def create(
        self,
        *,
        source_id: int,
        user_id: int,
        title: str,
        points: list[dict[str, Any]],
        status: str = "ready",
    ) -> KnowledgeOutline:
        return self.add(
            KnowledgeOutline(
                source_id=source_id,
                user_id=user_id,
                title=title,
                outline_json=points,
                status=status,
            )
        )

    def update_points(
        self, outline_id: int, *, points: list[dict[str, Any]]
    ) -> KnowledgeOutline | None:
        outline = self.get(outline_id)
        if outline is None:
            return None
        outline.outline_json = points
        outline.status = "ready"
        self.session.flush()
        return outline

    def mark_failed(self, outline_id: int) -> None:
        outline = self.get(outline_id)
        if outline is not None:
            outline.status = "failed"
            self.session.flush()

    def count_with_levels_since(self, user_id: int, since: datetime) -> int:
        """统计「今天真正出过题的大纲数量」，用于每日出题次数限制。"""
        return int(
            self.session.execute(
                select(func.count(func.distinct(Level.outline_id)))
                .select_from(Level)
                .join(KnowledgeOutline, KnowledgeOutline.id == Level.outline_id)
                .where(
                    KnowledgeOutline.user_id == user_id,
                    KnowledgeOutline.created_at >= since,
                )
            ).scalar_one()
        )


class LevelRepository(BaseRepository[Level]):
    model = Level

    def create(
        self,
        *,
        outline_id: int,
        seq: int,
        title: str,
        knowledge_point: str,
        question_count: int = 5,
    ) -> Level:
        return self.add(
            Level(
                outline_id=outline_id,
                seq=seq,
                title=title,
                knowledge_point=knowledge_point,
                question_count=question_count,
            )
        )

    def list_by_outline(self, outline_id: int) -> Sequence[Level]:
        return self.list(order_by=Level.seq, outline_id=outline_id)

    def count_by_outline(self, outline_id: int) -> int:
        return self.count(outline_id=outline_id)

    def delete_by_outline(self, outline_id: int) -> int:
        """重新出题前清掉旧关卡（连同题目），避免题目翻倍。"""
        level_ids = [level.id for level in self.list_by_outline(outline_id)]
        if not level_ids:
            return 0
        self.session.execute(delete(Question).where(Question.level_id.in_(level_ids)))
        self.session.execute(delete(Level).where(Level.id.in_(level_ids)))
        self.session.flush()
        return len(level_ids)


class QuestionRepository(BaseRepository[Question]):
    model = Question

    def create(
        self,
        *,
        level_id: int,
        outline_id: int,
        seq: int,
        type: str,
        difficulty: int,
        stem: str,
        options: list[dict[str, Any]],
        answer: list[str],
        explanation: str,
        hint: dict[str, Any] | None = None,
        quality_score: int | None = None,
    ) -> Question:
        return self.add(
            Question(
                level_id=level_id,
                outline_id=outline_id,
                seq=seq,
                type=type,
                difficulty=difficulty,
                stem=stem,
                options_json=options,
                answer_json=answer,
                explanation=explanation,
                hint_json=hint,
                quality_score=quality_score,
            )
        )

    def list_by_level(self, level_id: int) -> Sequence[Question]:
        return self.list(order_by=Question.seq, level_id=level_id)

    def list_by_outline(self, outline_id: int) -> Sequence[Question]:
        return self.list(order_by=Question.id, outline_id=outline_id)

    def count_by_level(self, level_id: int) -> int:
        return self.count(level_id=level_id)

    def ids_by_outline(self, outline_id: int) -> list[int]:
        return list(
            self.session.execute(
                select(Question.id).where(Question.outline_id == outline_id)
            ).scalars()
        )

    def set_disabled(self, question_id: int, *, disabled: bool = True) -> Question | None:
        question = self.get(question_id)
        if question is None:
            return None
        question.disabled_at = utcnow() if disabled else None
        self.session.flush()
        return question

    def replace_level_questions(
        self, level_id: int, questions: Sequence[Question]
    ) -> list[Question]:
        """出题引擎用：只保留给定的题（丢弃质量不合格的题），其余删除。"""
        keep_ids = {q.id for q in questions}
        for existing in self.list_by_level(level_id):
            if existing.id not in keep_ids:
                self.session.delete(existing)
        self.session.flush()
        return sorted(questions, key=lambda q: q.seq)


class AttemptRepository(BaseRepository[Attempt]):
    model = Attempt

    def create(self, *, user_id: int, outline_id: int, total_count: int) -> Attempt:
        return self.add(
            Attempt(
                user_id=user_id,
                outline_id=outline_id,
                status="ongoing",
                total_count=total_count,
                correct_count=0,
            )
        )

    def get_ongoing(self, user_id: int) -> Attempt | None:
        return self.session.execute(
            select(Attempt)
            .where(Attempt.user_id == user_id, Attempt.status == "ongoing")
            .order_by(Attempt.started_at.desc(), Attempt.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def abandon_others(self, user_id: int, keep_id: int) -> int:
        """开始新闯关时，把该用户其它未完成的闯关标记为 abandoned（避免首页出现多条继续学习）。"""
        changed = 0
        for attempt in self.list(user_id=user_id, status="ongoing"):
            if attempt.id != keep_id:
                attempt.status = "abandoned"
                changed += 1
        self.session.flush()
        return changed

    def finish(
        self,
        attempt_id: int,
        *,
        correct_count: int,
        accuracy: Decimal,
        duration_ms: int,
        star: int,
    ) -> Attempt | None:
        attempt = self.get(attempt_id)
        if attempt is None:
            return None
        attempt.status = "finished"
        attempt.correct_count = correct_count
        attempt.accuracy = accuracy
        attempt.duration_ms = duration_ms
        attempt.star = star
        attempt.finished_at = utcnow()
        self.session.flush()
        return attempt

    def list_by_user(
        self,
        user_id: int,
        *,
        status: str = "finished",
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Attempt]:
        return self.list(
            order_by=Attempt.started_at.desc(),
            limit=limit,
            offset=offset,
            user_id=user_id,
            status=status,
        )


class AnswerRecordRepository(BaseRepository[AnswerRecord]):
    model = AnswerRecord

    def create(
        self,
        *,
        attempt_id: int,
        question_id: int,
        user_id: int,
        answer: list[str],
        is_correct: bool,
        elapsed_ms: int,
    ) -> AnswerRecord:
        return self.add(
            AnswerRecord(
                attempt_id=attempt_id,
                question_id=question_id,
                user_id=user_id,
                user_answer_json=answer,
                is_correct=is_correct,
                elapsed_ms=elapsed_ms,
            )
        )

    def list_by_attempt(self, attempt_id: int) -> Sequence[AnswerRecord]:
        return self.list(order_by=AnswerRecord.id, attempt_id=attempt_id)

    def count_by_attempt(self, attempt_id: int) -> int:
        return self.count(attempt_id=attempt_id)

    def has_answered(self, attempt_id: int, question_id: int) -> bool:
        return (
            self.session.execute(
                select(func.count())
                .select_from(AnswerRecord)
                .where(
                    AnswerRecord.attempt_id == attempt_id,
                    AnswerRecord.question_id == question_id,
                )
            ).scalar_one()
            > 0
        )

    def get_by_attempt_question(
        self, attempt_id: int, question_id: int
    ) -> AnswerRecord | None:
        return self.session.execute(
            select(AnswerRecord)
            .where(
                AnswerRecord.attempt_id == attempt_id,
                AnswerRecord.question_id == question_id,
            )
            .limit(1)
        ).scalar_one_or_none()


class MistakeRepository(BaseRepository[Mistake]):
    model = Mistake

    def get_by_user_question(self, user_id: int, question_id: int) -> Mistake | None:
        return self.session.execute(
            select(Mistake)
            .where(Mistake.user_id == user_id, Mistake.question_id == question_id)
            .limit(1)
        ).scalar_one_or_none()

    def record_wrong(self, user_id: int, question_id: int, *, interval_days: int = 1) -> Mistake:
        """答错：次数 +1、掌握度清零、复习时间重置到 1 天后（间隔重复的起点）。"""
        mistake = self.get_by_user_question(user_id, question_id)
        now = utcnow()
        if mistake is None:
            return self.add(
                Mistake(
                    user_id=user_id,
                    question_id=question_id,
                    wrong_count=1,
                    mastery=0,
                    next_review_at=now + timedelta(days=interval_days),
                )
            )
        mistake.wrong_count += 1
        mistake.mastery = 0
        mistake.next_review_at = now + timedelta(days=interval_days)
        mistake.updated_at = now
        self.session.flush()
        return mistake

    def count_due(self, user_id: int, *, at: datetime | None = None) -> int:
        moment = at or utcnow()
        return int(
            self.session.execute(
                select(func.count())
                .select_from(Mistake)
                .where(Mistake.user_id == user_id, Mistake.next_review_at <= moment)
            ).scalar_one()
        )

    def list_due(
        self, user_id: int, *, limit: int = 20, at: datetime | None = None
    ) -> Sequence[Mistake]:
        moment = at or utcnow()
        return list(
            self.session.execute(
                select(Mistake)
                .where(Mistake.user_id == user_id, Mistake.next_review_at <= moment)
                .order_by(Mistake.next_review_at)
                .limit(limit)
            ).scalars()
        )


class QuestionReportRepository(BaseRepository[QuestionReport]):
    model = QuestionReport

    def create(
        self,
        *,
        question_id: int,
        user_id: int,
        reason: str,
        detail: str | None = None,
        status: str = "pending",
    ) -> int:
        """写入举报，返回该题当前的待处理举报数（用于判断是否下架）。"""
        self.add(
            QuestionReport(
                question_id=question_id,
                user_id=user_id,
                reason=reason,
                detail=detail,
                status=status,
            )
        )
        return self.count_pending(question_id)

    def count_pending(self, question_id: int) -> int:
        return self.count(question_id=question_id, status="pending")

    def is_flagged(self, question_id: int, *, threshold: int = 3) -> bool:
        return self.count_pending(question_id) >= threshold
