"""FastAPI 应用装配。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import TraceIdMiddleware, configure_logging
from app.db.session import create_engine_from_settings, create_session_factory
from app.services.llm.base import LLMProvider
from app.services.llm.factory import build_provider
from app.services.task_registry import TaskRegistry

logger = logging.getLogger("app.main")


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "app starting",
            extra={
                "env": settings.env,
                "version": settings.app_version,
                "llm_provider": settings.llm_provider,
            },
        )
        try:
            yield
        finally:
            engine = app.state.db_engine
            engine.dispose()
            logger.info("app stopped", extra={"env": settings.env})

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings
    engine = create_engine_from_settings(settings)
    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)
    # 测试里注入假 provider（零网络零成本），线上按 .env 装配真实供应商
    app.state.llm_provider = provider or build_provider(settings)
    app.state.task_registry = TaskRegistry()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TraceIdMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
