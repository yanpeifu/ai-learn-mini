"""外部资料检索（Tavily）：门面见 base.py，业务代码只依赖它，不直接碰框架。"""

from app.services.search.base import (
    ExtractOutcome,
    SearchHit,
    SearchOutcome,
    SearchProfile,
    SearchProvider,
)
from app.services.search.factory import build_search_provider
from app.services.search.grounding import GroundingResult, gather_references
from app.services.search.profiles import KnowledgeTraits, build_profile
from app.services.search.urls import extract_urls, has_url

__all__ = [
    "ExtractOutcome",
    "GroundingResult",
    "KnowledgeTraits",
    "SearchHit",
    "SearchOutcome",
    "SearchProfile",
    "SearchProvider",
    "build_profile",
    "build_search_provider",
    "extract_urls",
    "gather_references",
    "has_url",
]
