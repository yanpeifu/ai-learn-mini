"""测试用假数据与假 provider（零网络、零成本、完全确定）。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.services.llm.base import ChatMessage, LLMResult, LLMUsage


class ScriptedProvider:
    """按脚本依次返回结果；脚本里放异常即可模拟失败。"""

    name = "scripted"

    def __init__(self, responses: Sequence[Any], *, model_id: str = "scripted-1") -> None:
        self.responses = list(responses)
        self.model_id = model_id
        self.calls: list[dict[str, Any]] = []

    def chat_json(
        self,
        messages: Sequence[ChatMessage],
        schema: type,
        *,
        purpose: str = "chat_json",
        **kwargs: Any,  # noqa: ARG002
    ):
        self.calls.append(
            {
                "schema": schema.__name__,
                "purpose": purpose,
                "text": "\n".join(m.content for m in messages),
            }
        )
        if not self.responses:
            raise AssertionError("ScriptedProvider 的响应脚本已用完")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return schema.model_validate(item), LLMResult(
            text="",
            provider=self.name,
            model=self.model_id,
            latency_ms=5,
            usage=LLMUsage(prompt_tokens=100, completion_tokens=200),
        )

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any):  # noqa: ANN201, ARG002
        raise NotImplementedError("测试里只用到 chat_json")

    def cost_estimate(self, usage: LLMUsage | None) -> float:
        return 0.0123 if usage else 0.0


def outline_points() -> list[dict[str, str]]:
    return [
        {"id": "kp1", "title": "存款准备金率", "summary": "缴存比例决定可放贷资金"},
        {"id": "kp2", "title": "再贴现率", "summary": "商业银行向央行借款的利率"},
        {"id": "kp3", "title": "公开市场操作", "summary": "买券投放、卖券回笼资金"},
    ]


def outline_payload() -> dict[str, Any]:
    return {"title": "货币政策三大工具", "points": outline_points()}


# 15 个彼此差异明显的主题词：避免测试数据因「题干模板化 + 选项重合」被判成重复题
TOPICS: tuple[str, ...] = (
    "准备金率上调的资金效果",
    "再贴现借款成本的传导",
    "公开市场买券的资金投放",
    "货币政策与财政政策分工",
    "准备金制度的缴存基数",
    "央行再贷款的支持范围",
    "央行票据的发行目的",
    "贷款市场报价利率改革",
    "流动性投放渠道的差异",
    "基础货币的构成口径",
    "货币乘数的决定因素",
    "超额准备金的需求动机",
    "货币政策时滞的类型",
    "数量型与价格型工具",
    "结构性工具的使用场景",
)

_OPTION_LABELS = ["甲", "乙", "丙", "丁"]


def make_question(
    index: int,
    *,
    knowledge_point_id: str = "kp1",
    qtype: str = "single",
    level_seq: int | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """造一道「质量合格」的题：题干唯一、选项不重复、讲解 ≥40 字且与答案一致。"""
    # 带上 index 后缀，保证「题干 + 选项」在任意两题之间都不相同
    # （否则相似度检查会把补题的题误判成旧题重复）
    topic = f"{TOPICS[(index - 1) % len(TOPICS)]}（第 {index} 组）"
    answer_key = chr(ord("A") + (index % 4))
    if qtype == "judge":
        options = [{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}]
        answer_key = "A" if index % 2 == 0 else "B"
    elif qtype == "multiple":
        options = [
            {"key": "A", "text": f"{topic}的关键结论一"},
            {"key": "B", "text": f"{topic}的关键结论二"},
            {"key": "C", "text": f"{topic}的关键结论三"},
            {"key": "D", "text": f"{topic}的常见误解"},
        ]
        answer_key = "A"
    else:
        options = [
            {"key": chr(ord("A") + i), "text": f"{topic}的{label}类结论"}
            for i, label in enumerate(_OPTION_LABELS)
        ]

    answer = ["A", "B"] if qtype == "multiple" else [answer_key]
    question: dict[str, Any] = {
        "id": f"q{index}",
        "level_seq": level_seq,
        "knowledge_point_id": knowledge_point_id,
        "type": qtype,
        "difficulty": (index % 5) + 1,
        "stem": f"围绕「{topic}」，下列说法中正确的是？",
        "options": options,
        "answer": answer,
        "explanation": (
            f"正确答案是 {'、'.join(answer)}。"
            f"第 {index} 题考查的是货币政策工具的传导机制，"
            "准备金率决定银行可放贷的资金规模，再贴现率影响银行向央行借款的成本，"
            "公开市场操作则用于日常微调流动性，三者作用强度与灵活性各不相同。"
        ),
        "hint": None,
    }
    question.update(overrides)
    return question


def make_question_set(
    *, points: list[dict[str, str]] | None = None, total: int = 15
) -> dict[str, Any]:
    """造一份完全合格的 15 题题库（3 关 × 5 题，每个知识点都被覆盖）。"""
    outline = points or outline_points()
    questions = []
    for index in range(1, total + 1):
        point = outline[(index - 1) % 3]
        qtype = "single"
        if index % 5 == 0:
            qtype = "multiple"
        elif index % 7 == 0:
            qtype = "judge"
        questions.append(
            make_question(index, knowledge_point_id=point["id"], qtype=qtype)
        )
    return {"outline": outline, "questions": questions}


def make_defective_question(index: int, **overrides: Any) -> dict[str, Any]:
    """造一道必然被拦截的题：答案 E 不在选项里。"""
    return make_question(index, answer=["E"], **overrides)
