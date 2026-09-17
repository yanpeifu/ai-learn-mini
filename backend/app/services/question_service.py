"""关卡与题目生成（PRD F3 / M3-03、M3-04）。

流程：
    1 次生成 → 逐题质量校验 → 有致命缺陷的题重新生成 → 仍不合格就丢弃 →
    补题调用补足到每关 5 题 → 最终结构校验（15 题 / 3 关 / 知识点覆盖）。

任何一步都无法达标时抛 GENERATION_FAILED，**绝不把不合格的题返回给用户**
（对应 PRD「整份生成失败：提示用户重试，不产生脏数据」）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.schemas.generation import GeneratedQuestion, GeneratedQuestionSet, OutlinePoint
from app.schemas.repair import QuestionListPayload
from app.services.generation import GenerationCall, invoke_json
from app.services.llm.base import ChatMessage, LLMProvider
from app.services.prompts import (
    QUESTION_SYSTEM_PROMPT,
    build_backfill_prompt,
    build_questions_prompt,
    build_repair_prompt,
)
from app.services.quality import (
    Issue,
    audit_question_set,
    fatal_issues,
    group_fatal_issues,
    warning_issues,
)

logger = logging.getLogger("app.question")


@dataclass
class QuestionSetResult:
    payload: GeneratedQuestionSet
    call: GenerationCall[GeneratedQuestionSet]
    issues: list[Issue] = field(default_factory=list)
    regenerated: int = 0
    dropped: int = 0
    backfilled: int = 0


def generate_question_set(
    provider: LLMProvider, points: list[OutlinePoint], settings: Settings
) -> QuestionSetResult:
    total_levels = settings.total_level_count
    per_level = settings.questions_per_level
    messages = [
        ChatMessage.system(QUESTION_SYSTEM_PROMPT),
        ChatMessage.user(
            build_questions_prompt(points, total=total_levels * per_level, per_level=per_level)
        ),
    ]
    call = invoke_json(
        provider, messages, GeneratedQuestionSet, purpose="levels", settings=settings
    )
    payload = assign_levels(call.payload, total_levels=total_levels, per_level=per_level)

    payload, regenerated = _repair_defects(
        provider, points, payload, settings, total_levels=total_levels, per_level=per_level
    )
    payload, dropped = _drop_defective(
        payload, total_levels=total_levels, per_level=per_level
    )
    payload, freed = _free_slots_for_uncovered_points(payload, points)
    dropped += freed
    payload, backfilled, dropped_more = _backfill_gaps(
        provider, points, payload, settings, total_levels=total_levels, per_level=per_level
    )
    dropped += dropped_more

    final_issues = audit_question_set(
        payload.to_payload(), total_levels=total_levels, per_level=per_level
    )
    remaining_fatal = fatal_issues(final_issues)
    if remaining_fatal:
        logger.warning(
            "question set still invalid after repair",
            extra={
                "codes": sorted({issue.code for issue in remaining_fatal}),
                "regenerated": regenerated,
                "dropped": dropped,
                "backfilled": backfilled,
            },
        )
        raise AppError(ErrorCode.GENERATION_FAILED)

    return QuestionSetResult(
        payload=payload,
        call=call,
        issues=warning_issues(final_issues),
        regenerated=regenerated,
        dropped=dropped,
        backfilled=backfilled,
    )


# --------------------------------------------------------------------------- #
# 内部步骤
# --------------------------------------------------------------------------- #


def assign_levels(
    payload: GeneratedQuestionSet, *, total_levels: int, per_level: int
) -> GeneratedQuestionSet:
    """关卡归属按题目顺序强制分配（前 5 题第 1 关……）。

    刻意不信任模型填的 level_seq：模型很容易把 15 道题的关卡序号写错，
    而结构错乱会导致「每关 5 题」这条硬要求直接失败。
    """
    questions: list[GeneratedQuestion] = []
    for index, question in enumerate(payload.questions):
        level_seq = min(index // per_level + 1, total_levels)
        questions.append(question.model_copy(update={"level_seq": level_seq}))
    return payload.model_copy(update={"questions": questions})


def _repair_defects(
    provider: LLMProvider,
    points: list[OutlinePoint],
    payload: GeneratedQuestionSet,
    settings: Settings,
    *,
    total_levels: int,
    per_level: int,
) -> tuple[GeneratedQuestionSet, int]:
    regenerated = 0
    for _round in range(max(1, settings.llm_max_retries)):
        defects = group_fatal_issues(
            audit_question_set(
                payload.to_payload(), total_levels=total_levels, per_level=per_level
            )
        )
        if not defects:
            return payload, regenerated

        messages = [
            ChatMessage.system(QUESTION_SYSTEM_PROMPT),
            ChatMessage.user(build_repair_prompt(points, _problem_messages(payload, defects))),
        ]
        try:
            repaired = invoke_json(
                provider,
                messages,
                QuestionListPayload,
                purpose="repair",
                settings=settings,
                max_retries=0,
            )
        except AppError as exc:
            # 单题重生成失败不能拖垮整份生成（PRD：丢弃该题，从其它题补足）
            if exc.code == ErrorCode.LLM_UNAVAILABLE:
                raise
            logger.info("repair call failed, will drop defective questions")
            return payload, regenerated

        payload = merge_questions(
            payload,
            repaired.payload.questions,
            total_levels=total_levels,
            per_level=per_level,
        )
        regenerated += len(repaired.payload.questions)
    return payload, regenerated


def _drop_defective(
    payload: GeneratedQuestionSet, *, total_levels: int, per_level: int
) -> tuple[GeneratedQuestionSet, int]:
    issues = audit_question_set(
        payload.to_payload(), total_levels=total_levels, per_level=per_level
    )
    bad_indices = {
        int(issue.where[1:]) - 1
        for issue in issues
        if issue.fatal and issue.where.startswith("q") and issue.where[1:].isdigit()
    }
    if not bad_indices:
        return payload, 0
    kept = [q for index, q in enumerate(payload.questions) if index not in bad_indices]
    logger.info(
        "dropped defective questions",
        extra={"dropped": len(bad_indices), "kept": len(kept)},
    )
    return payload.model_copy(update={"questions": kept}), len(bad_indices)


def _backfill_gaps(
    provider: LLMProvider,
    points: list[OutlinePoint],
    payload: GeneratedQuestionSet,
    settings: Settings,
    *,
    total_levels: int,
    per_level: int,
) -> tuple[GeneratedQuestionSet, int, int]:
    backfilled = 0
    dropped = 0
    for _round in range(max(1, settings.llm_max_retries)):
        gaps = build_gaps(payload, points, total_levels=total_levels, per_level=per_level)
        if not gaps:
            return payload, backfilled, dropped
        messages = [
            ChatMessage.system(QUESTION_SYSTEM_PROMPT),
            ChatMessage.user(build_backfill_prompt(points, gaps)),
        ]
        try:
            extra = invoke_json(
                provider,
                messages,
                QuestionListPayload,
                purpose="backfill",
                settings=settings,
                max_retries=0,
            )
        except AppError as exc:
            if exc.code == ErrorCode.LLM_UNAVAILABLE:
                raise
            return payload, backfilled, dropped

        produced = len(extra.payload.questions)
        payload = merge_questions(
            payload,
            extra.payload.questions,
            total_levels=total_levels,
            per_level=per_level,
        )
        payload, dropped_here = _drop_defective(
            payload, total_levels=total_levels, per_level=per_level
        )
        backfilled += produced - dropped_here
        dropped += dropped_here
    return payload, backfilled, dropped


def merge_questions(
    payload: GeneratedQuestionSet,
    new_questions: list[GeneratedQuestion],
    *,
    total_levels: int,
    per_level: int,
) -> GeneratedQuestionSet:
    """按 id 覆盖式合并，并按关卡分组重新排布。

    关键点：修复/补题回来的题会带上目标 level_seq，必须先按关卡分组再按位置重排，
    否则补第 1 关的题会被追加到队尾、落到第 3 关去。
    """
    existing_by_id = {question.id: question for question in payload.questions}
    groups: dict[int, list[GeneratedQuestion]] = {
        level: [q for q in payload.questions if q.level_seq == level]
        for level in range(1, total_levels + 1)
    }
    placed_ids = {question.id for question in payload.questions}

    for question in new_questions:
        previous = existing_by_id.get(question.id)
        level = question.level_seq or (previous.level_seq if previous else None) or total_levels
        level = min(max(level, 1), total_levels)
        group = groups[level]
        if previous is not None:
            # 同一题的旧位置替换掉，避免重复计入
            group[:] = [question if q.id == previous.id else q for q in group]
            existing_by_id[question.id] = question
            continue
        group.append(question)
        existing_by_id[question.id] = question
        placed_ids.add(question.id)

    ordered: list[GeneratedQuestion] = []
    for level in range(1, total_levels + 1):
        for question in groups[level]:
            ordered.append(question.model_copy(update={"level_seq": level}))
    merged = payload.model_copy(update={"questions": ordered})
    normalized, _surplus = normalize_levels(
        merged, total_levels=total_levels, per_level=per_level
    )
    return normalized


def normalize_levels(
    payload: GeneratedQuestionSet, *, total_levels: int, per_level: int
) -> tuple[GeneratedQuestionSet, int]:
    """把关卡归位：每题放进它的目标关卡，超出的挪到还缺题的关卡，实在放不下就丢弃。

    模型的 level_seq 经常不准（甚至缺失），而「每关 5 题」是硬要求，
    所以合并之后必须做一次确定性的归位。
    """
    buckets: dict[int, list[GeneratedQuestion]] = {
        level: [] for level in range(1, total_levels + 1)
    }
    overflow: list[GeneratedQuestion] = []
    for question in payload.questions:
        level = min(max(question.level_seq or 1, 1), total_levels)
        if len(buckets[level]) < per_level:
            buckets[level].append(question.model_copy(update={"level_seq": level}))
        else:
            overflow.append(question)

    dropped = 0
    for question in overflow:
        target = next(
            (level for level in range(1, total_levels + 1) if len(buckets[level]) < per_level),
            None,
        )
        if target is None:
            dropped += 1
            continue
        buckets[target].append(question.model_copy(update={"level_seq": target}))

    ordered = [question for level in range(1, total_levels + 1) for question in buckets[level]]
    return payload.model_copy(update={"questions": ordered}), dropped


def _free_slots_for_uncovered_points(
    payload: GeneratedQuestionSet, points: list[OutlinePoint]
) -> tuple[GeneratedQuestionSet, int]:
    """有知识点完全没被覆盖时，腾出位置让补题调用去覆盖它。

    做法：从「被覆盖次数最多」的知识点里挑一道冗余题删掉，
    这样关卡题数会出现缺口，随后的补题调用就会针对缺口补上缺失的知识点。
    （对应 PRD F3 生成规则第 1 条：每个知识点至少被 1 道题覆盖）
    """
    counts: dict[str, int] = {}
    for question in payload.questions:
        counts[question.knowledge_point_id] = counts.get(question.knowledge_point_id, 0) + 1

    questions = list(payload.questions)
    freed = 0
    for point in points:
        if counts.get(point.id, 0) > 0:
            continue
        victim_index = _pick_redundant_index(questions, counts)
        if victim_index is None:
            break
        victim = questions.pop(victim_index)
        counts[victim.knowledge_point_id] = counts.get(victim.knowledge_point_id, 1) - 1
        freed += 1
        logger.info(
            "freed a slot for uncovered knowledge point",
            extra={"knowledge_point": point.id, "victim_question": victim.id},
        )
    return payload.model_copy(update={"questions": questions}), freed


def _pick_redundant_index(
    questions: list[GeneratedQuestion], counts: dict[str, int]
) -> int | None:
    """挑一道「最冗余」的题：其知识点被覆盖次数最多，且该知识点至少还有 2 道题。"""
    best_index: int | None = None
    best_count = 1
    for index, question in enumerate(questions):
        count = counts.get(question.knowledge_point_id, 0)
        if count > best_count:
            best_index = index
            best_count = count
    return best_index


def build_gaps(
    payload: GeneratedQuestionSet,
    points: list[OutlinePoint],
    *,
    total_levels: int,
    per_level: int,
) -> list[str]:
    gaps: list[str] = []
    covered = {question.knowledge_point_id for question in payload.questions}
    uncovered = [point for point in points if point.id not in covered]
    for level in range(1, total_levels + 1):
        count = sum(1 for q in payload.questions if q.level_seq == level)
        if count < per_level:
            missing = per_level - count
            # 有未覆盖的知识点时优先让它补进来，否则沿用该关原有知识点
            kp = (
                uncovered.pop(0).id
                if uncovered
                else (_dominant_knowledge_point(payload, level) or points[0].id)
            )
            gaps.append(f"第 {level} 关还缺 {missing} 题，knowledge_point_id 用 {kp}")

    for point in uncovered:
        gaps.append(f"知识点 {point.id}（{point.title}）还没有任何题目覆盖，请至少补 1 题")
    return gaps


def _problem_messages(
    payload: GeneratedQuestionSet, defects: dict[str, list[Issue]]
) -> list[tuple[str, list[str]]]:
    problems: list[tuple[str, list[str]]] = []
    for where, issues in sorted(defects.items(), key=lambda kv: int(kv[0][1:])):
        question = _question_at(payload, where)
        label = f"{where}（id={question.id if question else '未知'}）"
        problems.append((label, [issue.message for issue in issues]))
    return problems


def _question_at(payload: GeneratedQuestionSet, where: str) -> GeneratedQuestion | None:
    if not where.startswith("q") or not where[1:].isdigit():
        return None
    index = int(where[1:]) - 1
    if 0 <= index < len(payload.questions):
        return payload.questions[index]
    return None


def _dominant_knowledge_point(payload: GeneratedQuestionSet, level: int) -> str | None:
    for question in payload.questions:
        if question.level_seq == level:
            return question.knowledge_point_id
    return None
