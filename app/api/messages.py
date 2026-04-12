"""
消息接口路由
"""
import time
import json
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import litellm

from app.config import config
from app.constants import Constants
from app.models import MessagesRequest
from app.services import (
    convert_litellm_to_anthropic,
    convert_anthropic_to_litellm,
    handle_streaming_with_recovery,
)
from app.services.tokenizer import tokenizer_service
from app.utils import (
    classify_local_model_error,
    log_request_beautifully,
    log_tool_names,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/v1/messages")
async def create_message(request: MessagesRequest, raw_request: Request):
    """创建消息接口"""
    try:
        
        request_start_time = time.time()
        raw_request.state.start_time = request_start_time
        logger.info(f"🕒 请求接收时间: {datetime.now().isoformat()} (timestamp={request_start_time})")
        logger.info(f"📥 Received model param: {request.original_model}")
        logger.info(f"📊 Processing request: Original={request.original_model}, Effective={request.model}, Stream={request.stream}")
        
        if request.stream and (
            config.force_disable_streaming or config.emergency_disable_streaming
        ):
            disabled_by = (
                "EMERGENCY_DISABLE_STREAMING"
                if config.emergency_disable_streaming
                else "FORCE_DISABLE_STREAMING"
            )
            logger.warning(f"Streaming disabled via {disabled_by}")
            request.stream = False

        # 转换请求
        num_tools = len(request.tools) if request.tools else 0
        log_tool_names(logger, raw_request.url.path, request.tools)
        litellm_request = convert_anthropic_to_litellm(request,num_tools)
        litellm_request["api_key"] = config.api_key
        litellm_request["base_url"] = config.base_url
        
        # 记录请求日志
        log_request_beautifully(
            "POST", raw_request.url.path,
            request.original_model or request.model,
            litellm_request.get('model'),
            len(litellm_request['messages']),
            num_tools, 200
        )

        # 计算输入 token
        try:
            if tokenizer_service.is_custom():
                logger.info("request, use singleton_tokenizer")
            else:
                logger.info("request, use default tokenizer")

            input_tokens = tokenizer_service.count_litellm_request_tokens(litellm_request)
            logger.info(f"input_tokens: {input_tokens}")
        except Exception as token_error:
            logger.warning(
                f"Failed to precompute input_tokens for model {litellm_request.get('model')}: {token_error}"
            )
            input_tokens = 0

        # 流式处理
        if request.stream:
            streaming_retry_count = 0
            max_retries = config.max_streaming_retries
            
            while streaming_retry_count <= max_retries:
                try:
                    logger.debug(f"Attempting streaming (attempt {streaming_retry_count + 1}/{max_retries + 1})")
                    
                    if streaming_retry_count > 0:
                        delay = min(0.5 * (2 ** streaming_retry_count), 2.0)
                        logger.debug(f"Waiting {delay}s before retry...")
                        await asyncio.sleep(delay)

                    response_generator = await litellm.acompletion(**litellm_request)
                    
                    return StreamingResponse(
                        handle_streaming_with_recovery(response_generator, request, input_tokens),
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "X-Accel-Buffering": "no",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                    
                except (litellm.exceptions.APIConnectionError, RuntimeError) as streaming_error:
                    streaming_retry_count += 1
                    error_msg = str(streaming_error)
                    
                    if ("Error parsing chunk" in error_msg and 
                        "Expecting property name enclosed in double quotes" in error_msg):
                        
                        if streaming_retry_count <= max_retries:
                            logger.warning(f"Streaming chunk parsing error (attempt {streaming_retry_count}/{max_retries + 1}), retrying...")
                            continue
                        else:
                            logger.error(f"Streaming failed after {max_retries + 1} attempts due to malformed chunks, falling back to non-streaming")
                            break
                    else:
                        if streaming_retry_count <= max_retries:
                            logger.warning(f"Streaming error (attempt {streaming_retry_count}/{max_retries + 1}): {error_msg}")
                            continue
                        else:
                            logger.error(f"Streaming failed after {max_retries + 1} attempts, falling back to non-streaming")
                            break
                            
                except Exception as unexpected_error:
                    streaming_retry_count += 1
                    logger.error(f"Unexpected streaming error (attempt {streaming_retry_count}/{max_retries + 1}): {unexpected_error}")
                    
                    if streaming_retry_count <= max_retries:
                        continue
                    else:
                        logger.error(f"Streaming failed after {max_retries + 1} attempts due to unexpected errors, falling back to non-streaming")
                        break
            
            logger.info("Falling back to non-streaming mode")
            litellm_request["stream"] = False
        
        # 非流式处理
        if not request.stream or litellm_request.get("stream") == False:
            start_time = time.time()
            logger.info("start non-streaming")

            litellm_response = await litellm.acompletion(**litellm_request)
            logger.info(f"✅ Response received: Model={litellm_request.get('model')}, Time={time.time() - start_time:.2f}s")
            try:
                prompt_tokens = None
                completion_tokens = None
                total_tokens = None

                if hasattr(litellm_response, "usage") and litellm_response.usage:
                    usage = litellm_response.usage
                    prompt_tokens = getattr(usage, "prompt_tokens", None)
                    completion_tokens = getattr(usage, "completion_tokens", None)
                    total_tokens = getattr(usage, "total_tokens", None)
                elif isinstance(litellm_response, dict):
                    usage = litellm_response.get("usage", {}) or {}
                    prompt_tokens = usage.get("prompt_tokens")
                    completion_tokens = usage.get("completion_tokens")
                    total_tokens = usage.get("total_tokens")

                if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
                    total_tokens = prompt_tokens + completion_tokens

                logger.info(
                    "📊 模型端 usage(非流式): "
                    f"prompt_tokens={prompt_tokens}, "
                    f"completion_tokens={completion_tokens}, "
                    f"total_tokens={total_tokens}"
                )
            except Exception as usage_log_error:
                logger.warning(f"记录模型端 usage(非流式) 失败: {usage_log_error}")

            anthropic_response = convert_litellm_to_anthropic(litellm_response, request)
            
            # 记录响应日志
            try:
                if anthropic_response and anthropic_response.content:
                    text_content = ""
                    tool_calls = []
                    
                    for content_block in anthropic_response.content:
                        if content_block.type == Constants.CONTENT_TEXT:
                            text_content = content_block.text
                        elif content_block.type == Constants.CONTENT_TOOL_USE:
                            tool_calls.append({
                                "name": content_block.name,
                                "id": content_block.id,
                                "input": content_block.input
                            })
                    
                    logger.info(f"📤 模型响应结果:")
                    logger.info(f"   模型: {anthropic_response.model}")
                    logger.info(f"   停止原因: {anthropic_response.stop_reason}")
                    logger.info(f"   输入令牌: {anthropic_response.usage.input_tokens}")
                    logger.info(f"   输出令牌: {anthropic_response.usage.output_tokens}")
                    logger.info(f"   总令牌: {anthropic_response.usage.input_tokens + anthropic_response.usage.output_tokens}")
                    
                    if text_content:
                        if config.log_response_details:
                            display_text = text_content[:500] + "..." if len(text_content) > 500 else text_content
                            logger.info(f"   文本内容: {display_text}")
                        else:
                            logger.info(f"   文本长度: {len(text_content)} 字符")
                    
                    if tool_calls:
                        logger.info(f"   工具调用: {len(tool_calls)} 个工具")
                        if config.log_response_details:
                            for i, tool_call in enumerate(tool_calls):
                                logger.info(f"     工具 {i+1}: {tool_call['name']} (ID: {tool_call['id']})")
                                args_str = json.dumps(tool_call['input'], ensure_ascii=False)
                                display_args = args_str[:200] + "..." if len(args_str) > 200 else args_str
                                logger.info(f"     参数: {display_args}")
                
            except Exception as log_error:
                logger.warning(f"记录响应日志时出错: {log_error}")
            
            return anthropic_response

    except litellm.exceptions.APIError as e:
        logger.error(f"LiteLLM API Error: {e}")
        error_msg = classify_local_model_error(str(e))
        raise HTTPException(status_code=getattr(e, 'status_code', 500), detail=error_msg)
    except ConnectionError as e:
        logger.error(f"Connection Error: {e}")
        raise HTTPException(status_code=503, detail="Connection error. Please check your internet connection.")
    except TimeoutError as e:
        logger.error(f"Timeout Error: {e}")
        raise HTTPException(status_code=504, detail="Request timeout. Please try again.")
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        error_msg = classify_local_model_error(str(e))
        raise HTTPException(status_code=500, detail=error_msg)
