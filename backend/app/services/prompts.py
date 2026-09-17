"""提示词。

出题提示词的骨架与 13 条硬性约束**沿用 `quality_check.py` 里已验证过的版本**
（该版本在 20 个跨领域样例上拿到 99.2 分），只做三处必要扩展：
1. 题量从 8–12 道改为「3 关 × 5 题 = 15 道」；
2. 新增「每个知识点至少被 1 道题覆盖」；
3. 新增「每关内部难度要有梯度」。

大纲提示词是新增的（质检脚本原本是同一次调用里出大纲 + 出题）。
"""

from __future__ import annotations

from typing import Sequence

from app.schemas.generation import OutlinePoint
from app.services.quality import MIN_EXPLANATION_CHARS

OUTLINE_SYSTEM_PROMPT = (
    "你是一位资深教研专家，擅长把任意知识内容拆解为结构化、可判分、有教学价值的学习大纲。"
    "你只输出严格的 json，不输出任何解释、说明或 Markdown 代码块标记。"
)

QUESTION_SYSTEM_PROMPT = (
    "你是一位资深教研专家，擅长把任意知识内容拆解为结构化、可判分、有教学价值的客观题。"
    "你只输出严格的 json，不输出任何解释、说明或 Markdown 代码块标记。"
)

OUTLINE_USER_TEMPLATE = """请把下面这段知识内容拆成 3-5 个知识点，供后续出题使用。

【知识内容】
{text}

【输出要求】
严格输出 json，不要输出任何解释性文字，不要使用 Markdown 代码块包裹。
json 结构如下：
{{
  "title": "用不超过 20 字概括这段内容的主题",
  "points": [
    {{"id": "kp1", "title": "知识点名称", "summary": "一句话说明该知识点的核心"}}
  ]
}}

【硬性约束】
1. points 必须是 3-5 个，id 从 kp1 开始连续编号（kp1、kp2、kp3……）。
2. 每个知识点的 title 不超过 30 字，summary 不超过 40 字。
3. 知识点必须是这段内容里真实讲到的，不得引入外部知识或编造。
4. 知识点之间不要重叠，要能看出学习的先后顺序。
5. 所有文本中禁止使用英文双引号，需要引用时一律使用中文引号「」。
6. 输出必须是完整闭合的合法 json，不要在结尾被截断。
"""

QUESTION_USER_TEMPLATE = """请基于下面已确认的知识大纲，生成一套闯关题库。

【知识大纲】
{outline}

【输出要求】
严格输出 json，不要输出任何解释性文字，不要使用 Markdown 代码块包裹。
json 结构如下：
{{
  "outline": [
    {{"id": "kp1", "title": "知识点名称", "summary": "一句话说明"}}
  ],
  "questions": [
    {{
      "id": "q1",
      "level_seq": 1,
      "knowledge_point_id": "kp1",
      "type": "single",
      "difficulty": 2,
      "stem": "题干",
      "options": [{{"key": "A", "text": "选项内容"}}],
      "answer": ["A"],
      "explanation": "解释为什么这个答案正确，并说明其他选项错在哪里",
      "hint": null
    }}
  ]
}}

【硬性约束】
1. questions 必须是 {total} 道题，level_seq 为 1、2、3 的各有 {per_level} 道，一道不多一道不少。
2. 每个知识点至少被 1 道题覆盖（knowledge_point_id 必须出现在上面的大纲里）。
3. type 只能是 single（单选）、multiple（多选）、judge（判断）。
4. single 必须有 4 个选项且只有 1 个正确答案；multiple 必须有 4 个选项且至少 2 个正确答案；
   judge 固定 2 个选项（key 为 A、B），选项文本必须分别是"正确"和"错误"。
5. 严禁使用"以上都对""以上都不对"这类选项。
6. 每道题的 explanation 不少于 {min_explain} 个汉字，必须解释正确选项为什么正确。
7. difficulty 取 1-5 的整数；每一关内部的难度要有梯度，不要全部相同。
8. 正确答案的分布要尽量均匀，不要全部集中在同一个选项。
9. 所有内容必须严格来自给定的知识大纲，不得引入外部知识或编造事实。
10. 所有文本中禁止使用英文双引号，需要引用时一律使用中文引号「」，
    以免破坏 json 结构导致整份结果无法解析。
11. 输出必须是完整闭合的合法 json，不要在结尾被截断。
12. options 的 key 必须从 A 开始连续编号（A、B、C、D），不允许跳号或缺号；
    answer 只能引用已经给出的选项 key，绝不能引用不存在的选项。
    输出前请逐一自检：每个 answer 里的字母都能在该题的 options 中找到。
13. 语义不同的题目不要复用同一套选项，避免用户产生"又是这道题"的感觉。
14. hint 字段固定输出 null（MVP 阶段不使用引导问题）；请勿省略该字段。
"""

REPAIR_USER_TEMPLATE = """下面这些题存在质量问题，请重写它们。

【知识大纲】
{outline}

【需要重写的题目与问题】
{problems}

【输出要求】
严格输出 json，只包含重写后的题目，结构如下：
{{
  "questions": [
    {{
      "id": "与原题相同的 id",
      "level_seq": 原题的 level_seq,
      "knowledge_point_id": 原题的 knowledge_point_id,
      "type": "single",
      "difficulty": 3,
      "stem": "题干",
      "options": [{{"key": "A", "text": "选项内容"}}],
      "answer": ["A"],
      "explanation": "不少于 {min_explain} 字的讲解，必须说明正确选项为什么正确",
      "hint": null
    }}
  ]
}}

【硬性约束】
1. 保持每道题的 id、level_seq、knowledge_point_id 与原来完全一致。
2. 题型、选项数量、答案数量的规则与原来一致：
   single 四个选项一个答案；multiple 四个选项至少两个答案；judge 两个选项（A=正确、B=错误）。
3. 严禁使用"以上都对""以上都不对"这类选项。
4. options 的 key 必须从 A 开始连续编号，answer 只能引用已给出的 key。
5. 讲解不少于 {min_explain} 个汉字，必须解释正确选项为什么正确。
6. 所有文本中禁止使用英文双引号，需要引用时使用中文引号「」。
7. 只输出 json，不要输出解释文字。
"""

BACKFILL_USER_TEMPLATE = """下面的题库还缺题，请补足。

【知识大纲】
{outline}

【缺口说明】
{gaps}

【输出要求】
严格输出 json，只包含新补充的题目，结构如下：
{{
  "questions": [
    {{
      "id": "新题的 id，例如 q101",
      "level_seq": 需要补题的关卡序号,
      "knowledge_point_id": 该关对应的知识点 id,
      "type": "single",
      "difficulty": 3,
      "stem": "题干",
      "options": [{{"key": "A", "text": "选项内容"}}],
      "answer": ["A"],
      "explanation": "不少于 {min_explain} 字的讲解",
      "hint": null
    }}
  ]
}}

【硬性约束】
1. 只补充缺口说明里要求的题目数量与关卡。
2. 与已有题目不要重复（题干、选项都要有明显区别）。
3. 题型、选项与答案规则：single 四选一；multiple 四个选项至少两个答案；judge 两个选项（A=正确、B=错误）。
4. options 的 key 从 A 开始连续编号，answer 只能引用已给出的 key。
5. 讲解不少于 {min_explain} 个汉字。
6. 所有文本中禁止使用英文双引号。
7. 只输出 json，不要输出解释文字。
"""


def format_outline(points: Sequence[OutlinePoint]) -> str:
    """把大纲渲染成提示词里可读的文本。"""
    lines = [f"- {p.id}｜{p.title}：{p.summary}" for p in points]
    return "\n".join(lines)


def build_outline_prompt(text: str) -> str:
    return OUTLINE_USER_TEMPLATE.format(text=text.strip())


def build_questions_prompt(points: Sequence[OutlinePoint], *, total: int, per_level: int) -> str:
    return QUESTION_USER_TEMPLATE.format(
        outline=format_outline(points),
        total=total,
        per_level=per_level,
        min_explain=MIN_EXPLANATION_CHARS,
    )


def build_repair_prompt(
    points: Sequence[OutlinePoint], problems: Sequence[tuple[str, Sequence[str]]]
) -> str:
    lines: list[str] = []
    for where, messages in problems:
        lines.append(f"- {where}：{'；'.join(messages)}")
    return REPAIR_USER_TEMPLATE.format(
        outline=format_outline(points),
        problems="\n".join(lines),
        min_explain=MIN_EXPLANATION_CHARS,
    )


def build_backfill_prompt(points: Sequence[OutlinePoint], gaps: Sequence[str]) -> str:
    return BACKFILL_USER_TEMPLATE.format(
        outline=format_outline(points),
        gaps="\n".join(f"- {gap}" for gap in gaps),
        min_explain=MIN_EXPLANATION_CHARS,
    )
