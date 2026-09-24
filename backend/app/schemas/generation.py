"""LLM 结构化输出的数据模型（也是 quality 校验的输入结构）。

字段与 `quality_check.py` 里已验证的输出契约保持一致：
{"outline": [{id,title,summary}], "questions": [{...}]}
这里额外加了 level_seq（MVP 是 3 关 × 5 题）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

QuestionType = Literal["single", "multiple", "judge"]

#: 模型偶尔会用中文或别名写题型，这里统一归一化（归一化不了才丢弃该题）
TYPE_ALIASES: dict[str, str] = {
    "single": "single",
    "single_choice": "single",
    "singlechoice": "single",
    "单选": "single",
    "单选题": "single",
    "multiple": "multiple",
    "multi": "multiple",
    "multi_choice": "multiple",
    "多选": "multiple",
    "多选题": "multiple",
    "judge": "judge",
    "true_false": "judge",
    "boolean": "judge",
    "判断": "judge",
    "判断题": "judge",
}


def normalize_question_type(value: Any) -> str:
    return TYPE_ALIASES.get(str(value or "").strip().lower(), str(value or "").strip().lower())


def clamp_difficulty(value: Any) -> int:
    """难度越界（0、6、或写成字符串）时夹到 1–5，而不是把整份题目判废。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 3
    return min(5, max(1, number))


class OutlinePoint(BaseModel):
    id: str = Field(description="知识点 id，从 kp1 开始连续编号")
    title: str = Field(description="知识点名称，不超过 30 字")
    summary: str = Field(description="一句话说明，不超过 40 字")


class OutlinePayload(BaseModel):
    title: str = Field(default="", description="用不超过 20 字概括这段内容的主题")
    points: list[OutlinePoint] = Field(min_length=3, max_length=5)
    # ↓ 与「是否需要联网取资料」有关：模型顺手给出的判断，用来决定要不要检索
    needs_external_reference: bool = Field(
        default=False, description="这段内容是否需要最新资料才能讲准"
    )
    search_queries: list[str] = Field(
        default_factory=list, description="建议的检索关键词（最多 3 个）"
    )
    complexity: Literal["simple", "complex"] = Field(
        default="simple", description="知识复杂度：simple / complex"
    )
    timeliness: Literal["stable", "time_sensitive"] = Field(
        default="stable", description="时效性：stable / time_sensitive"
    )


class GeneratedOption(BaseModel):
    key: str = Field(description="选项 key，从 A 开始连续编号")
    text: str


class GeneratedHint(BaseModel):
    """苏格拉底式引导问题（L3，V0.5 使用；MVP 允许为 null）。"""

    stem: str
    options: list[GeneratedOption]
    answer: list[str]


class GeneratedQuestion(BaseModel):
    id: str
    # 刻意不做范围校验：出题服务本来就按题目顺序重新分配关卡（assign_levels），
    # 模型把 level_seq 写成 4 或漏掉，都不该让整份 15 题作废。
    level_seq: int | None = None
    knowledge_point_id: str
    type: str
    difficulty: int = 3
    stem: str
    options: list[GeneratedOption]
    answer: list[str]
    explanation: str
    hint: GeneratedHint | None = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: Any) -> str:
        normalized = normalize_question_type(value)
        if normalized not in ("single", "multiple", "judge"):
            raise ValueError(f"未知题型：{value!r}")
        return normalized

    @field_validator("difficulty", mode="before")
    @classmethod
    def _validate_difficulty(cls, value: Any) -> int:
        return clamp_difficulty(value)


class GeneratedQuestionSet(BaseModel):
    outline: list[OutlinePoint] = Field(default_factory=list)
    questions: list[GeneratedQuestion] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _salvage_questions(cls, data: Any) -> Any:
        """逐题校验：不合格的题直接丢掉，剩下的照常返回（缺口由出题服务补题）。

        这样「一道题写坏了」不会升级成「整份 15 题重试」——
        重试一次的成本是 40 秒 + 约 0.05 元。
        """
        if isinstance(data, dict) and isinstance(data.get("questions"), list):
            return {**data, "questions": salvage_questions(data["questions"])}
        return data

    def to_payload(self) -> dict:
        """转成 quality_check.py 使用的原始 dict 结构，便于与脚本做一致性校验。"""
        return self.model_dump(mode="json")


def salvage_questions(raw_items: list[Any]) -> list[GeneratedQuestion]:
    """尽量把原始题目列表转成模型对象，坏的单题丢掉。"""
    kept: list[GeneratedQuestion] = []
    for item in raw_items:
        try:
            kept.append(GeneratedQuestion.model_validate(item))
        except Exception:  # noqa: BLE001 - 单题不合法不影响整批
            continue
    return kept
