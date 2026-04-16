"""
健康检查接口路由
"""
import logging
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import litellm

from app.config import config
from app.services.model_manager import model_manager
from app.utils import classify_local_model_error

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查接口"""
    try:
        default_route = config.model_route_list[0]
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.5.0",
            "local_api_configured": bool(config.model_route_list),
            "api_key_valid": config.validate_api_key(),
            "default_base_url": default_route.base_url,
            "model_routes": [
                {
                    "model_name": route.model_name,
                    "base_url": route.base_url,
                    "auth_token_configured": bool(route.auth_token),
                    "tokenizer_file": route.tokenizer_file,
                }
                for route in config.model_route_list
            ],
            "streaming_config": {
                "force_disabled": config.force_disable_streaming,
                "emergency_disabled": config.emergency_disable_streaming,
                "max_retries": config.max_streaming_retries
            }
        }
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": "Health check failed"
            }
        )


@router.get("/test-connection")
async def test_connection():
    """测试 API 连接"""
    model_route = None
    try:
        model_route = config.model_route_list[0]
        test_response = await litellm.acompletion(
            model=f"openai/{model_route.model_name}",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5,
            api_key=model_route.auth_token,
            base_url=model_route.base_url
        )
        
        return {
            "status": "success",
            "message": "Successfully connected to Local Model API",
            "base_url": model_route.base_url,
            "model_used": model_route.model_name,
            "timestamp": datetime.now().isoformat(),
            "response_id": getattr(test_response, 'id', 'unknown')
        }
        
    except litellm.exceptions.APIError as e:
        logger.error(f"API connectivity test failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "failed",
                "error_type": "API Error",
                "message": classify_local_model_error(str(e), base_url=model_route.base_url),
                "timestamp": datetime.now().isoformat(),
                "suggestions": [
                    "Check your API_KEY is valid for your local model service",
                    "Verify your local model service is running",
                    f"Check if {model_route.base_url} is accessible"
                ]
            }
        )
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "failed",
                "error_type": "Connection Error", 
                "message": classify_local_model_error(
                    str(e),
                    base_url=model_route.base_url if model_route else None,
                ),
                "timestamp": datetime.now().isoformat(),
                "suggestions": [
                    "Check your internet connection",
                    "Verify your local model service is running and accessible",
                    f"Check if {model_route.base_url if model_route else 'the configured model route base_url'} is the correct URL",
                    "Try again in a few moments"
                ]
            }
        )


@router.get("/")
async def root():
    """根路由"""
    return {
        "message": f"Enhanced Local-Model-to-Claude API Proxy v2.5.0",
        "status": "running",
        "config": {
            "default_base_url": config.model_route_list[0].base_url,
            "default_model": config.model_route_list[0].model_name,
            "available_models": model_manager.local_models[:5],
            "max_tokens_limit": config.max_tokens_limit,
            "api_key_configured": config.validate_api_key(),
            "model_routes": [
                {
                    "model_name": route.model_name,
                    "base_url": route.base_url,
                    "auth_token_configured": bool(route.auth_token),
                    "tokenizer_file": route.tokenizer_file,
                }
                for route in config.model_route_list
            ],
            "streaming": {
                "force_disabled": config.force_disable_streaming,
                "emergency_disabled": config.emergency_disable_streaming,
                "max_retries": config.max_streaming_retries
            }
        },
        "endpoints": {
            "messages": "/v1/messages",
            "count_tokens": "/v1/messages/count_tokens",
            "models": "/models",
            "event_logging_batch": "/api/event_logging/batch",
            "health": "/health",
            "test_connection": "/test-connection"
        }
    }
