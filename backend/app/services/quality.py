"""出题质量校验（MVP 的核心护城河）。

这段逻辑是从项目里已验证的 `quality_check.py`（20/20 样例、99.2 分）**逐项移植**的，
保证「线上拦截的标准」与「质检脚本的标准」完全一致（PRD F3 明确要求复用）。

三条刻意不检查（避免把好题误判成缺陷）：
1. 不检查选项之间是否高度相似（最小对照选项是好干扰项）；
2. 不把句式相同的并列出题当重复（题干相似 **且** 选项重合才算重复）；
3. 不把「解释错误选项」当答案不一致（故不选 D / 若选 B 则相反）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MIN_QUESTIONS = 15
MIN_QUESTIONS_PER_LEVEL = 5
MIN_EXPLANATION_CHARS = 40
MIN_STEM_CHARS = 6
MAX_STEM_CHARS = 150
DUPLICATE_STEM_RATIO = 0.90
DUPLICATE_OPTION_OVERLAP = 0.75
ANSWER_SKEW_RATIO = 0.60

LOW_QUALITY_OPTION_PATTERNS = [
    r"以上(都|均|全)(对|正确|是|错|不正确|不对)",
    r"以上选项(都|均)",
    r"^(都|均)不正确$",
    r"^(都|均)不对$",
    r"全部(都)?(正确|不正确|对|错)$",
]

JUDGE_OPTION_TEXTS = {"正确", "错误", "对", "错", "是", "否", "true", "false"}
VALID_TYPES = {"single", "multiple", "judge"}

# 选项字母后面不能紧跟其它字母或数字，
# 否则「正确选项是DNA的一条链」里的 D 会被误当成选项 D（中英混排陷阱）。
_OPT_LETTER = r"([A-D](?![A-Za-z0-9_])(?:\s*[、,，和及与]\s*[A-D](?![A-Za-z0-9_]))*)"
ANSWER_ASSERT_RE = re.compile(
    r"(?:正确选项|正确答案|参考答案|标准答案|本题答案|答案)\s*"
    r"(?:是|为|应为|应该是|：|:)?\s*" + _OPT_LETTER
)
CHOICE_RE = re.compile(r"选\s*([A-D](?![A-Za-z0-9_]))")
NEG_HEAD_RE = re.compile(r"(?:不|未|别|勿|排除|排除掉)$")
NEG_TAIL_RE = re.compile(
    r"^\s*(?:项)?\s*(?:错误|错的|错|不对|不正确|有误|不符合|不成立|相反|不合适|不恰当|无关)"
)
HYPOTHESIS_HEAD_RE = re.compile(r"(?:若|如果|假若|假如|倘若)$")

# PRD F3 质量校验表里的「致命」项：命中就该题重新生成
FATAL_CODES = {
    "answer_not_in_options",
    "option_key_gap",
    "option_key_dup",
    "option_text_dup",
    "judge_option_count",
    "single_option_count",
    "multiple_option_count",
    "option_low_quality",
    "stem_duplicate",
    "kp_ref_invalid",
    "answer_count_mismatch",
    "explanation_answer_mismatch",
    "field_missing",
    "options_missing",
    "answer_invalid",
    "type_invalid",
    "q_malformed",
    # 我们这套 15 题结构特有的致命项
    "level_question_count",
    "question_count",
}

# 只记日志、不阻塞的「警告」
WARNING_CODES = {
    "explanation_too_short",
    "answer_skew",
    "difficulty_flat",
    "kp_uncovered",
    "option_set_duplicate",
    "stem_too_short",
    "stem_too_long",
    "judge_option_text",
    "difficulty_invalid",
}


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warn"
    code: str
    message: str
    where: str = ""

    @property
    def fatal(self) -> bool:
        return self.severity == "error"


def norm_text(text: Any) -> str:
    """归一化：去空白、去标点，用于相似度与重复判断。"""
    s = str(text or "")
    return re.sub(r"[\s，。、；：？！,.;:?!\"'（）()【】\[\]「」…—-]+", "", s)


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return round(len(shorter) / len(longer), 3)
    common = sum(1 for ch in set(shorter) if ch in longer)
    return round(common / max(len(set(shorter)), 1), 3)


def set_overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return round(len(sa & sb) / max(len(sa), 1), 3)


def is_low_quality_option(text: str) -> bool:
    t = norm_text(text)
    return any(re.search(pattern, t) for pattern in LOW_QUALITY_OPTION_PATTERNS)


def extract_asserted_answers(explanation: str) -> list[str]:
    """抽取讲解中**断言为正确答案**的选项字母；刻意忽略否定与假设语境。"""
    asserted: list[str] = []
    for match in ANSWER_ASSERT_RE.finditer(explanation):
        asserted += re.findall(r"[A-D]", match.group(1))
    for match in CHOICE_RE.finditer(explanation):
        head = explanation[max(0, match.start() - 5) : match.start()]
        tail = explanation[match.end() : match.end() + 12]
        if NEG_HEAD_RE.search(head) or HYPOTHESIS_HEAD_RE.search(head):
            continue
        if NEG_TAIL_RE.match(tail):
            continue
        asserted.append(match.group(1))
    return asserted


def _expected_keys(count: int) -> list[str]:
    return [chr(ord("A") + i) for i in range(count)]


def audit_payload(payload: dict[str, Any]) -> list[Issue]:
    """与 `quality_check.py:audit_case` 等价的校验（同样的输入结构、同样的规则）。"""
    issues: list[Issue] = []

    def err(code: str, message: str, where: str = "") -> None:
        issues.append(Issue("error", code, message, where))

    def warn(code: str, message: str, where: str = "") -> None:
        issues.append(Issue("warn", code, message, where))

    outline = payload.get("outline")
    questions = payload.get("questions")
    if not isinstance(outline, list) or not outline:
        err("outline_missing", "缺少 outline 或 outline 为空")
        outline = []
    if not isinstance(questions, list) or not questions:
        err("questions_missing", "缺少 questions 或 questions 为空")
        return issues

    kp_ids: set[str] = set()
    for idx, kp in enumerate(outline, 1):
        if not isinstance(kp, dict):
            err("kp_malformed", f"第 {idx} 个知识点不是对象", f"kp{idx}")
            continue
        kid = str(kp.get("id", "")).strip()
        if not kid:
            err("kp_id_missing", f"第 {idx} 个知识点缺少 id", f"kp{idx}")
        else:
            if kid in kp_ids:
                err("kp_id_dup", f"知识点 id 重复：{kid}", f"kp{idx}")
            kp_ids.add(kid)
        if not str(kp.get("title", "")).strip():
            err("kp_title_missing", f"知识点 {kid or idx} 缺少 title", f"kp{idx}")

    if len(outline) < 3:
        warn("outline_too_few", f"知识点只有 {len(outline)} 个，建议 3-5 个")
    if len(outline) > 5:
        warn("outline_too_many", f"知识点有 {len(outline)} 个，建议 3-5 个")

    records: list[dict[str, Any]] = []
    single_answers: list[str] = []
    difficulties: list[int] = []
    used_kps: set[str] = set()

    for idx, question in enumerate(questions, 1):
        where = f"q{idx}"
        if not isinstance(question, dict):
            err("q_malformed", f"第 {idx} 题不是对象", where)
            continue
        for field_name in ("type", "stem", "options", "answer", "explanation"):
            if question.get(field_name) in (None, "", [], {}):
                err("field_missing", f"缺少必填字段 {field_name}", where)

        kp_ref = str(question.get("knowledge_point_id", "")).strip()
        if not kp_ref:
            err("kp_ref_missing", "未关联知识点 knowledge_point_id", where)
        elif kp_ref not in kp_ids:
            err("kp_ref_invalid", f"关联的知识点 {kp_ref} 不存在于 outline 中", where)
        else:
            used_kps.add(kp_ref)

        qtype = str(question.get("type", "")).strip().lower()
        if qtype not in VALID_TYPES:
            err("type_invalid", f"题型非法：{qtype!r}", where)

        difficulty = question.get("difficulty")
        if not isinstance(difficulty, int) or isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
            warn("difficulty_invalid", f"难度值非法或缺失：{difficulty!r}", where)
        else:
            difficulties.append(difficulty)

        stem = str(question.get("stem", "")).strip()
        stem_norm = norm_text(stem)
        if stem:
            if qtype != "judge" and len(stem) < MIN_STEM_CHARS:
                warn("stem_too_short", f"题干过短（{len(stem)} 字）", where)
            if len(stem) > MAX_STEM_CHARS:
                warn("stem_too_long", f"题干过长（{len(stem)} 字）", where)

        options = question.get("options")
        if not isinstance(options, list) or not options:
            err("options_missing", "options 缺失或为空", where)
            continue

        keys: list[str] = []
        texts: list[str] = []
        for opt_index, option in enumerate(options, 1):
            if not isinstance(option, dict):
                err("option_malformed", f"第 {opt_index} 个选项不是对象", where)
                continue
            key = str(option.get("key", "")).strip()
            text = str(option.get("text", "")).strip()
            if not key:
                err("option_key_missing", f"第 {opt_index} 个选项缺少 key", where)
            if not text:
                err("option_text_missing", f"选项 {key or opt_index} 的 text 为空", where)
            keys.append(key)
            texts.append(text)

        if len(set(keys)) != len(keys):
            err("option_key_dup", "选项 key 有重复", where)
        if keys and keys != _expected_keys(len(keys)):
            # 选项 key 必须从 A 开始连续编号（PRD F3 致命项：跳号/缺号）
            err("option_key_gap", f"选项 key 未从 A 开始连续编号：{keys}", where)
        if len(set(texts)) != len(texts):
            err("option_text_dup", "存在内容完全相同的选项", where)

        norm_texts = [norm_text(t) for t in texts if t]
        for text in texts:
            if is_low_quality_option(text):
                err("option_low_quality", f"使用了低质量选项（如「{text}」），教研上视为无效干扰项", where)

        if qtype == "single" and len(options) != 4:
            err("single_option_count", f"单选题应有 4 个选项，实际 {len(options)} 个", where)
        if qtype == "multiple" and len(options) < 4:
            err("multiple_option_count", f"多选题至少应有 4 个选项，实际 {len(options)} 个", where)
        if qtype == "judge":
            if len(options) != 2:
                err("judge_option_count", f"判断题应只有 2 个选项，实际 {len(options)} 个", where)
            elif {norm_text(t).lower() for t in texts} - {
                norm_text(t).lower() for t in JUDGE_OPTION_TEXTS
            }:
                warn("judge_option_text", "判断题选项文本建议为「正确/错误」", where)

        answer = question.get("answer")
        if not isinstance(answer, list) or not answer:
            err("answer_invalid", "answer 必须是非空数组", where)
        else:
            answer_keys = [str(a).strip() for a in answer]
            for key in answer_keys:
                if key not in keys:
                    err("answer_not_in_options", f"答案 {key} 不在选项 {keys} 中", where)
            if qtype in ("single", "judge") and len(answer_keys) != 1:
                err("answer_count_mismatch", f"{qtype} 题型应只有 1 个正确答案，实际 {len(answer_keys)} 个", where)
            if qtype == "multiple" and len(answer_keys) < 2:
                err("answer_count_mismatch", f"多选题至少应有 2 个正确答案，实际 {len(answer_keys)} 个", where)
            if qtype == "single" and len(answer_keys) == 1:
                single_answers.append(answer_keys[0])

        explanation = str(question.get("explanation", "")).strip()
        if not explanation:
            err("explanation_missing", "缺少讲解", where)
        elif len(explanation) < 20:
            err("explanation_too_short", f"讲解极短（{len(explanation)} 字），几乎没有教学价值", where)
        elif len(explanation) < MIN_EXPLANATION_CHARS:
            warn("explanation_too_short", f"讲解过短（{len(explanation)} 字，建议不少于 {MIN_EXPLANATION_CHARS} 字）", where)

        if explanation and isinstance(answer, list) and answer:
            asserted = extract_asserted_answers(explanation)
            answer_set = {str(a).strip() for a in answer}
            wrong = sorted({k for k in asserted if k not in answer_set})
            if wrong:
                err(
                    "explanation_answer_mismatch",
                    f"讲解中断言答案为 {'、'.join(wrong)}，但 answer 字段是 {'、'.join(sorted(answer_set))}，两者不一致",
                    where,
                )

        records.append({"where": where, "stem": stem_norm, "opts": norm_texts, "type": qtype})

    # 跨题重复：题干相似 **且** 选项重合才算重复
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            ra, rb = records[i], records[j]
            if not ra["stem"] or not rb["stem"]:
                continue
            stem_ratio = similarity(ra["stem"], rb["stem"])
            if stem_ratio < DUPLICATE_STEM_RATIO:
                continue
            if set_overlap(ra["opts"], rb["opts"]) >= DUPLICATE_OPTION_OVERLAP:
                err("stem_duplicate", f"{ra['where']} 与 {rb['where']}：题干高度重复且选项重合", rb["where"])

    option_group: dict[tuple[str, ...], list[str]] = {}
    for record in records:
        if record["type"] == "judge" or not record["opts"]:
            continue
        option_group.setdefault(tuple(record["opts"]), []).append(record["where"])
    for _group, wheres in option_group.items():
        if len(wheres) >= 3:
            warn("option_set_duplicate", f"{'、'.join(wheres)} 这 {len(wheres)} 道题使用了完全相同的选项组", wheres[-1])

    if len(single_answers) >= 4:
        counts: dict[str, int] = {}
        for answer in single_answers:
            counts[answer] = counts.get(answer, 0) + 1
        top_key, top_n = max(counts.items(), key=lambda kv: kv[1])
        ratio = top_n / len(single_answers)
        if ratio > ANSWER_SKEW_RATIO:
            warn("answer_skew", f"单选题答案分布不均：选项 {top_key} 占比 {ratio:.0%}")

    if difficulties and len(set(difficulties)) == 1:
        warn("difficulty_flat", f"所有题目难度相同（均为 {difficulties[0]}），缺少梯度")

    uncovered = kp_ids - used_kps
    if uncovered:
        warn("kp_uncovered", f"以下知识点没有任何题目覆盖：{', '.join(sorted(uncovered))}")

    return issues


def audit_question_set(
    payload: dict[str, Any],
    *,
    total_levels: int = 3,
    per_level: int = 5,
) -> list[Issue]:
    """在我们自己的 15 题结构上追加结构性校验（关卡数、每关题数）。"""
    issues = list(audit_payload(payload))
    questions = payload.get("questions") or []
    if not isinstance(questions, list):
        return issues

    expected_total = total_levels * per_level
    if len(questions) != expected_total:
        issues.append(
            Issue("error", "question_count", f"应有 {expected_total} 道题，实际 {len(questions)} 道")
        )

    by_level: dict[int | None, int] = {}
    for question in questions:
        if not isinstance(question, dict):
            continue
        level = question.get("level_seq")
        by_level[level] = by_level.get(level, 0) + 1
    for level in range(1, total_levels + 1):
        actual = by_level.get(level, 0)
        if actual != per_level:
            issues.append(
                Issue("error", "level_question_count", f"第 {level} 关应有 {per_level} 题，实际 {actual} 题", f"level{level}")
            )
    return issues


def group_fatal_issues(issues: list[Issue]) -> dict[str, list[Issue]]:
    """按题目（where）归类致命问题，供「单题重新生成」使用。"""
    grouped: dict[str, list[Issue]] = {}
    for issue in issues:
        if issue.fatal and issue.where.startswith("q"):
            grouped.setdefault(issue.where, []).append(issue)
    return grouped


def fatal_issues(issues: list[Issue]) -> list[Issue]:
    return [issue for issue in issues if issue.fatal]


def warning_issues(issues: list[Issue]) -> list[Issue]:
    return [issue for issue in issues if not issue.fatal]
