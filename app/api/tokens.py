"""
Token 计数接口路由
"""
import logging
from fastapi import APIRouter, Request, HTTPException

from app.models import TokenCountRequest, TokenCountResponse, MessagesRequest
from app.services import convert_anthropic_to_litellm
from app.services.model_manager import model_manager
from app.services.tokenizer import tokenizer_service
from app.utils import (
    classify_local_model_error,
    log_request_beautifully,
    log_tool_names,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/v1/messages/count_tokens")
async def count_tokens(request: TokenCountRequest, raw_request: Request):
    """Token 计数接口"""
    model_route = None
    try:
        # 创建临时请求用于转换
        temp_request = MessagesRequest(
            model=request.model,
            max_tokens=1,
            messages=request.messages,
            system=request.system,
            tools=request.tools,
            tool_choice=request.tool_choice,
            thinking=request.thinking,
        )
        
        num_tools = len(request.tools) if request.tools else 0
        log_tool_names(logger, raw_request.url.path, request.tools)
        litellm_data = convert_anthropic_to_litellm(temp_request, num_tools)
        model_route = model_manager.get_model_route(temp_request.model)
        litellm_data["model"] = f"openai/{model_route.model_name}"
        
        # 记录请求日志
        log_request_beautifully(
            "POST", raw_request.url.path,
            request.original_model or request.model,
            litellm_data.get('model'),
            len(litellm_data['messages']), num_tools, 200
        )

        if tokenizer_service.is_custom(litellm_data["model"]):
            logger.info(f"use model tokenizer: {litellm_data['model']}")
        else:
            logger.info(f"use default tokenizer: {litellm_data['model']}")

        # 计算 token
        token_count = tokenizer_service.count_litellm_request_tokens(litellm_data)
        
        return TokenCountResponse(input_tokens=token_count)

    except Exception as e:
        logger.error(f"Error counting tokens: {str(e)}")
        error_msg = classify_local_model_error(
            str(e),
            base_url=model_route.base_url if model_route else None,
        )
        raise HTTPException(status_code=500, detail=f"Error counting tokens: {error_msg}")
