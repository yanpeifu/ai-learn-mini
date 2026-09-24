"""FastAPI 依赖：数据库会话、当前用户、模型 provider、配置。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth import decode_access_token
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.models import User
from app.repositories import UserRepository
from app.services.llm.base import LLMProvider
from app.services.search.base import SearchProvider

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider


def get_search_provider(request: Request) -> SearchProvider:
    return request.app.state.search_provider


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """从 Bearer token 解出 user_id 再取用户；**不接受前端传 user_id**（PRD 2.5）。"""
    if credentials is None or not credentials.credentials:
        raise AppError(ErrorCode.UNAUTHORIZED)
    settings = get_app_settings(request)
    user_id = decode_access_token(credentials.credentials, settings)
    user = UserRepository(db).get(user_id)
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
LlmProvider = Annotated[LLMProvider, Depends(get_llm_provider)]
SearchDep = Annotated[SearchProvider, Depends(get_search_provider)]
