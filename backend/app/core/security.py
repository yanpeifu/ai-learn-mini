"""输入安全校验：字数、敏感词（PRD F1 校验规则 / M8-02 内容安全）。

注意：这里的词表是**最小可用清单**，M8 阶段会替换为微信内容安全接口或完整词库。
校验文案与小程序端保持完全一致（前端也用它做实时提示）。
"""

from __future__ import annotations

from app.core.errors import AppError, ErrorCode

# 最小可用敏感词表（按内容安全类别示例，非完整词库）
MINIMAL_SENSITIVE_WORDS: tuple[str, ...] = (
    "赌博",
    "毒品",
    "枪支",
    "色情",
    "暴力恐怖",
    "爆炸物",
    "代考",
    "作弊神器",
    "办假证",
)

TEXT_TOO_SHORT_MESSAGE = "内容太短啦，再多描述一点（至少 20 字）"
TEXT_TOO_LONG_MESSAGE = "内容太长，建议精简到 2000 字以内"
TEXT_SENSITIVE_MESSAGE = "内容包含不适宜的内容，请修改后重试"


def find_sensitive_word(text: str) -> str | None:
    for word in MINIMAL_SENSITIVE_WORDS:
        if word in text:
            return word
    return None


def validate_raw_text(
    text: str | None, *, min_chars: int = 20, max_chars: int = 2000
) -> str:
    """校验并返回去除首尾空白后的知识文本；不合法直接抛 AppError(INVALID_INPUT)。"""
    cleaned = (text or "").strip()
    if not cleaned:
        raise AppError(ErrorCode.INVALID_INPUT, TEXT_TOO_SHORT_MESSAGE)
    if len(cleaned) < min_chars:
        raise AppError(ErrorCode.INVALID_INPUT, TEXT_TOO_SHORT_MESSAGE)
    if len(cleaned) > max_chars:
        raise AppError(ErrorCode.INVALID_INPUT, TEXT_TOO_LONG_MESSAGE)
    if find_sensitive_word(cleaned):
        raise AppError(ErrorCode.INVALID_INPUT, TEXT_SENSITIVE_MESSAGE)
    return cleaned
