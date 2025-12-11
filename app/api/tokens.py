"""
Token 计数接口路由
"""
import logging
from fastapi import APIRouter, Request, HTTPException
import litellm

from app.models import TokenCountRequest, TokenCountResponse, MessagesRequest
from app.services import convert_anthropic_to_litellm
from app.services.tokenizer import tokenizer_service
from app.utils import classify_local_model_error, log_request_beautifully

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/v1/messages/count_tokens")
async def count_tokens(request: TokenCountRequest, raw_request: Request):
    """Token 计数接口"""
    try:
        # 创建临时请求用于转换
        temp_request = MessagesRequest(
            model=request.model,
            max_tokens=1,
            messages=request.messages,
            system=request.system,
            tools=request.tools,
        )
        
        litellm_data = convert_anthropic_to_litellm(temp_request,0)
        
        # 记录请求日志
        num_tools = len(request.tools) if request.tools else 0
        log_request_beautifully(
            "POST", raw_request.url.path,
            request.original_model or request.model,
            litellm_data.get('model'),
            len(litellm_data['messages']), num_tools, 200
        )

        custom_tokenizer = tokenizer_service.get_tokenizer()
        if custom_tokenizer is not None:
            logger.info(f"use custom_tokenizer")
        else:
            logger.info(f"use default tokenizer")

        # 计算 token
        token_count = litellm.token_counter(
            model=litellm_data["model"],
            custom_tokenizer=custom_tokenizer,
            messages=litellm_data["messages"],
        )
        
        return TokenCountResponse(input_tokens=token_count)

    except Exception as e:
        logger.error(f"Error counting tokens: {str(e)}")
        error_msg = classify_local_model_error(str(e))
        raise HTTPException(status_code=500, detail=f"Error counting tokens: {error_msg}")

