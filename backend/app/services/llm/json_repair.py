"""从模型返回里稳健地抽取 JSON。

大模型输出的 JSON 经常有瑕疵：被 ```json 包裹、前后有说明文字、结尾多逗号、
内容过长被截断。这里逐级降级修复，尽量避免「明明生成了内容却报解析失败」。

这段逻辑是从项目里已验证的 `quality_check.py`（20/20 样例、99.2 分）原样移植的，
保证线上出题与质检脚本使用同一套解析标准（PRD M3-03）。
"""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("模型返回为空")
    cleaned = text.strip()

    # 去掉 ```json ... ``` 包裹
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()

    # 第 1 级：直接解析 / 去掉尾逗号后解析
    for candidate in (cleaned, strip_trailing_commas(cleaned)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data

    # 第 2 级：截取第一个 { 到最后一个 }
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(strip_trailing_commas(cleaned[start : end + 1]))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return data

    # 第 3 级：截断修复（在最后一个完整的元素边界处闭合括号）
    repaired = repair_json(cleaned)
    if repaired is not None:
        return repaired

    raise ValueError("无法从返回内容中解析出 JSON")


def strip_trailing_commas(text: str) -> str:
    """去掉对象/数组结尾多余逗号：{"a":1,} -> {"a":1}"""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def balance_and_close(text: str) -> str | None:
    """在字符串状态正常的前提下，为未闭合的括号补上结尾。

    如果扫描结束时正处于字符串内部，说明是「截断在半个字符串里」，
    无法安全修复，返回 None。
    """
    stack: list[str] = []
    in_str = False
    escaped = False
    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            if not stack:
                return None
            stack.pop()
    if in_str:
        return None
    return text + "".join("]" if c == "[" else "}" for c in reversed(stack))


def repair_json(text: str) -> dict[str, Any] | None:
    """尝试修复被截断的 JSON：从后往前找最后一个元素边界，补齐括号。"""
    start = text.find("{")
    if start == -1:
        return None
    body = text[start:]

    positions = [m.end() for m in re.finditer(r"[}\]]", body)]
    for pos in reversed(positions[-150:]):
        closed = balance_and_close(strip_trailing_commas(body[:pos]))
        if not closed:
            continue
        try:
            data = json.loads(closed)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None
