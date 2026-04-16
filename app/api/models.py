"""
模型列表接口路由
"""
from fastapi import APIRouter

from app.config import config

router = APIRouter()


@router.get("/models")
async def get_models():
    """返回当前系统配置的模型列表"""
    models = []

    for index, route in enumerate(config.model_route_list, start=1):
        models.append(
            {
                "model": route.model_name,
                "description": route.description,
                "contextLength": route.context_length,
                "supportsImageAnalysis": route.supports_image_analysis,
                "default": index == 1,
            }
        )

    return {"models": models}
