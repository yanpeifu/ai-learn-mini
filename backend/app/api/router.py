"""所有业务路由的统一注册点。"""

from fastapi import APIRouter

from app.api import attempt, auth, health, knowledge, templates

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(knowledge.router)
api_router.include_router(attempt.router)
api_router.include_router(templates.router)
