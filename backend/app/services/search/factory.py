"""按配置装配 SearchProvider：未配置 Key 或有人手动关掉时，装配不联网的空实现。"""

from __future__ import annotations

from app.core.config import Settings
from app.services.search.base import SearchProvider
from app.services.search.mock import NoopSearchProvider


def build_search_provider(settings: Settings) -> SearchProvider:
    """检索没配好就退化成空实现 —— 与改动前的行为完全一致，且不会发起任何请求。"""
    if not settings.search_enabled:
        return NoopSearchProvider()

    # 延迟 import：让「不用检索」的部署完全不会加载 langchain_tavily
    from app.services.search.tavily import TavilySearchProvider

    return TavilySearchProvider(settings)
