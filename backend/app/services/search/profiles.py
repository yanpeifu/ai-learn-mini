"""检索画像决策：把「知识复杂度 + 时效性 + 用户地区」映射成参数组合。

这是**纯函数**模块（tasks 2.2 要求表驱动单测）：同样输入永远得到同样输出，
不碰网络、不碰数据库。为什么参数要分创建期/调用期两层，见 ``base.SearchProfile``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.services.search.base import SearchProfile

Complexity = Literal["simple", "complex"]
Timeliness = Literal["stable", "time_sensitive"]
Locale = Literal["zh", "other"]


@dataclass(frozen=True)
class KnowledgeTraits:
    """对本次知识内容的判断结果（由大纲那次结构化输出给出）。"""

    complexity: Complexity = "simple"
    timeliness: Timeliness = "stable"
    locale: Locale = "zh"


def build_profile(traits: KnowledgeTraits, settings: Settings) -> SearchProfile:
    """按知识特征挑参数。

    口径：
    - 复杂/很新的知识 → 检索更深、结果更多、并且要整页正文（这些是创建期参数）；
    - 强时效内容 → topic 用 news、限制近一月（这些是调用期参数）；
    - 中文/国内用户 → 优先来源站点白名单 + 可选国家偏置；其它语言不加偏置。
    """
    complex_knowledge = traits.complexity == "complex"
    time_sensitive = traits.timeliness == "time_sensitive"
    topic: Literal["general", "news", "finance"] = "news" if time_sensitive else "general"
    is_zh = traits.locale == "zh"

    return SearchProfile(
        # ---- 创建期参数（建工具时定死）----
        include_raw_content=complex_knowledge,
        max_results=(
            settings.search_max_results_max
            if complex_knowledge
            else settings.search_max_results_min
        ),
        # country 只在 topic=general 时合法；且只在中文/国内场景才施加，避免给英文用户带去中文偏置
        country=settings.search_country if (topic == "general" and is_zh) else None,
        # ---- 调用期参数（每次传）----
        search_depth="advanced" if complex_knowledge else "basic",
        topic=topic,
        time_range="month" if time_sensitive else None,
        include_domains=tuple(settings.preferred_search_domains) if is_zh else (),
        extract_depth="advanced" if complex_knowledge else "basic",
    )
