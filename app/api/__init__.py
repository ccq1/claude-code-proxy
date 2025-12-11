"""
API 路由模块
"""
from fastapi import APIRouter

from .messages import router as messages_router
from .tokens import router as tokens_router
from .health import router as health_router
from .event_logging import router as event_logging_router

# 创建主路由
api_router = APIRouter()

# 注册子路由
api_router.include_router(messages_router)
api_router.include_router(tokens_router)
api_router.include_router(health_router)
api_router.include_router(event_logging_router)

__all__ = ["api_router"]

