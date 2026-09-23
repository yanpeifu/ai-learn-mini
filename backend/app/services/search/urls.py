"""从用户输入里识别网址（供「按网址抽取正文」用）。"""

from __future__ import annotations

import re

# 明确带协议的网址，以及常见的不带协议的 www. 开头网址
_URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"'，。；、）)】\]]+", re.IGNORECASE)
# 中文标点一般不是网址的一部分，但英文句末的标点常被一起粘进来
_TRAILING = ".,;:!?、。；：！？"


def extract_urls(text: str) -> list[str]:
    """按出现顺序返回去重后的网址；``www.`` 开头会自动补上 https。"""
    urls: list[str] = []
    for match in _URL_PATTERN.findall(text or ""):
        url = match.rstrip(_TRAILING)
        if url.lower().startswith("www."):
            url = f"https://{url}"
        if url not in urls:
            urls.append(url)
    return urls


def has_url(text: str) -> bool:
    return bool(extract_urls(text))
