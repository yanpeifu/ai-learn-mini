"""所有业务路由的统一注册点。"""

from fastapi import APIRouter

from app.api import health

api_router = APIRouter()
api_router.include_router(health.router)
