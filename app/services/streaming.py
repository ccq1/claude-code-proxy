"""
流式响应处理服务
"""
import json
import asyncio
import logging
import litellm

from app.constants import Constants
from .converter import validate_todowrite_tool_call

logger = logging.getLogger(__name__)


async def handle_streaming_with_recovery(response_generator, original_request, input_tokens: int):
    """增强的流式处理器，带有错误恢复机制"""
    logger.info(f"stream解析开始")
    message_id = f"msg_{__import__('uuid').uuid4().hex[:24]}"
    
    # 发送初始 SSE 事件
    yield f"event: {Constants.EVENT_MESSAGE_START}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_START, 'message': {'id': message_id, 'type': 'message', 'role': Constants.ROLE_ASSISTANT, 'model': original_request.original_model or original_request.model, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': input_tokens, 'output_tokens': 0}}})}\n\n"
    
    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': 0, 'content_block': {'type': Constants.CONTENT_TEXT, 'text': ''}})}\n\n"
    
    yield f"event: {Constants.EVENT_PING}\ndata: {json.dumps({'type': Constants.EVENT_PING})}\n\n"

    # 流式状态管理
    all_chunks = []
    accumulated_text = ""
    text_block_index = 0
    tool_block_counter = 0
    current_tool_calls = {}
    output_tokens = 0
    final_stop_reason = Constants.STOP_END_TURN
    
    # 错误恢复追踪
    consecutive_errors = 0
    max_consecutive_errors = 10
    stream_terminated_early = False
    malformed_chunks_count = 0
    max_malformed_chunks = 20
    
    chunk_buffer = ""
    
    def is_malformed_chunk(chunk_str: str) -> bool:
        """检测畸形的 chunk"""
        if not chunk_str or not isinstance(chunk_str, str):
            return True
            
        chunk_stripped = chunk_str.strip()
        
        if not chunk_stripped:
            return True
            
        malformed_singles = ["{", "}", "[", "]", ",", ":", '"', "'"]
        if chunk_stripped in malformed_singles:
            return True
            
        malformed_patterns = [
            '{"', '"}', "[{", "}]", "{}", "[]", 
            "null", '""', "''", " ", "",
            "{,", ",}", "[,", ",]"
        ]
        if chunk_stripped in malformed_patterns:
            return True
            
        if chunk_stripped.startswith('{') and not chunk_stripped.endswith('}'):
            if len(chunk_stripped) < 15:
                return True
                
        if chunk_stripped.startswith('[') and not chunk_stripped.endswith(']'):
            if len(chunk_stripped) < 10:
                return True
        
        if chunk_stripped.count('{') != chunk_stripped.count('}'):
            if len(chunk_stripped) < 20:
                return True
                
        if chunk_stripped.count('[') != chunk_stripped.count(']'):
            if len(chunk_stripped) < 20:
                return True
        
        return False
    
    def try_parse_buffered_chunk(buffer: str) -> tuple:
        """尝试解析缓冲的 chunk"""
        if not buffer.strip():
            return None, ""
            
        brace_count = 0
        start_pos = -1
        
        for i, char in enumerate(buffer):
            if char == '{':
                if start_pos == -1:
                    start_pos = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_pos != -1:
                    json_str = buffer[start_pos:i+1]
                    try:
                        parsed = json.loads(json_str)
                        remaining_buffer = buffer[i+1:]
                        return parsed, remaining_buffer
                    except json.JSONDecodeError:
                        continue
        
        return None, buffer
    
    try:
        stream_iterator = aiter(response_generator)
        
        while True:
            try:
                try:
                    chunk = await asyncio.wait_for(anext(stream_iterator), timeout=90.0)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.warning("Streaming timeout, terminating")
                    stream_terminated_early = True
                    break
                
                consecutive_errors = 0
                all_chunks.append(chunk)
                
                if isinstance(chunk, str):
                    if chunk.strip() == "[DONE]":
                        break
                    
                    if is_malformed_chunk(chunk):
                        malformed_chunks_count += 1
                        logger.debug(f"Skipping malformed chunk #{malformed_chunks_count}: '{chunk[:50]}{'...' if len(chunk) > 50 else ''}'")
                        
                        if malformed_chunks_count > max_malformed_chunks:
                            logger.error(f"Too many malformed chunks ({malformed_chunks_count}), terminating stream")
                            stream_terminated_early = True
                            break
                        continue
                    
                    chunk_buffer += chunk
                    parsed_chunk, chunk_buffer = try_parse_buffered_chunk(chunk_buffer)
                    
                    if parsed_chunk is None:
                        if len(chunk_buffer) > 10000:
                            logger.warning("Chunk buffer too large, clearing")
                            chunk_buffer = ""
                        continue
                    
                    chunk = parsed_chunk
                
                if isinstance(chunk, dict):
                    pass
                elif hasattr(chunk, 'choices'):
                    pass
                else:
                    try:
                        if isinstance(chunk, str):
                            chunk = json.loads(chunk)
                        else:
                            logger.debug(f"Skipping unprocessable chunk type: {type(chunk)}")
                            continue
                    except json.JSONDecodeError as parse_error:
                        logger.debug(f"Failed to parse chunk as JSON: {parse_error}")
                        continue

                delta_content_text = None
                delta_tool_calls = None
                chunk_finish_reason = None

                if hasattr(chunk, 'choices') and chunk.choices:
                    choice = chunk.choices[0]
                    if hasattr(choice, 'delta') and choice.delta:
                        delta = choice.delta
                        delta_content_text = getattr(delta, 'content', None)
                        if hasattr(delta, 'tool_calls'):
                            delta_tool_calls = delta.tool_calls
                    chunk_finish_reason = getattr(choice, 'finish_reason', None)
                elif isinstance(chunk, dict):
                    choices = chunk.get("choices", [])
                    if choices:
                        choice = choices[0]
                        delta = choice.get("delta", {})
                        delta_content_text = delta.get("content")
                        delta_tool_calls = delta.get("tool_calls")
                        chunk_finish_reason = choice.get("finish_reason")

                if hasattr(chunk, 'usage') and chunk.usage:
                    input_tokens = getattr(chunk.usage, 'prompt_tokens', 0)
                    output_tokens = getattr(chunk.usage, 'completion_tokens', 0)
                elif isinstance(chunk, dict) and "usage" in chunk:
                    usage = chunk["usage"]
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)

                if delta_content_text:
                    accumulated_text += delta_content_text
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': text_block_index, 'delta': {'type': Constants.DELTA_TEXT, 'text': delta_content_text}})}\n\n"

                if delta_tool_calls:
                    logger.debug(f"🔨 接收到工具调用delta: {len(delta_tool_calls)} 个")
                    for tc_chunk in delta_tool_calls:
                        tc_id = getattr(tc_chunk, 'id', None)
                        tc_function = getattr(tc_chunk, 'function', None)
                        
                        if (hasattr(tc_chunk, 'function') and tc_chunk.function and 
                           hasattr(tc_chunk.function, 'name') and tc_chunk.function.name and
                           tc_chunk.id):
                            tool_call_id = tc_chunk.id
                            
                            if tool_call_id not in current_tool_calls:
                                tool_block_counter += 1
                                tool_index = text_block_index + tool_block_counter
                                
                                current_tool_calls[tool_call_id] = {
                                    "index": tool_index,
                                    "name": tc_chunk.function.name or "",
                                    "args_buffer": tc_chunk.function.arguments or ""
                                }
                                
                                logger.info(f"🔨 开始新工具调用: {tc_chunk.function.name} (ID: {tool_call_id})")
                                
                                yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': tool_index, 'content_block': {'type': Constants.CONTENT_TOOL_USE, 'id': tool_call_id, 'name': current_tool_calls[tool_call_id]['name'], 'input': {}}})}\n\n"
                            
                            if tc_chunk.function.arguments:
                                current_tool_calls[tool_call_id]["args_buffer"] += tc_chunk.function.arguments
                                yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': current_tool_calls[tool_call_id]['index'], 'delta': {'type': Constants.DELTA_INPUT_JSON, 'partial_json': tc_chunk.function.arguments}})}\n\n"
                                
                        elif (hasattr(tc_chunk, 'function') and tc_chunk.function and 
                              hasattr(tc_chunk.function, 'arguments') and tc_chunk.function.arguments):
                            if current_tool_calls:
                                latest_tool_id = list(current_tool_calls.keys())[-1]
                                latest_tool_data = current_tool_calls[latest_tool_id]
                                
                                latest_tool_data["args_buffer"] += tc_chunk.function.arguments
                                yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': latest_tool_data['index'], 'delta': {'type': Constants.DELTA_INPUT_JSON, 'partial_json': tc_chunk.function.arguments}})}\n\n"
                            else:
                                logger.warning(f"⚠️ 收到工具参数片段，但没有活跃的工具调用")
                        else:
                            continue

                if chunk_finish_reason:
                    if chunk_finish_reason == "length":
                        final_stop_reason = Constants.STOP_MAX_TOKENS
                    elif chunk_finish_reason == "tool_calls":
                        final_stop_reason = Constants.STOP_TOOL_USE
                    elif chunk_finish_reason == "stop":
                        final_stop_reason = Constants.STOP_END_TURN
                    else:
                        final_stop_reason = Constants.STOP_END_TURN
                    break
                        
            except (json.JSONDecodeError, ValueError) as parse_error:
                consecutive_errors += 1
                logger.debug(f"JSON parsing error (attempt {consecutive_errors}/{max_consecutive_errors}): {parse_error}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive parsing errors ({consecutive_errors}), terminating stream")
                    stream_terminated_early = True
                    break
                continue
                
            except (litellm.exceptions.APIConnectionError, RuntimeError) as api_error:
                consecutive_errors += 1
                error_msg = str(api_error)
                
                if ("Error parsing chunk" in error_msg and 
                    "Expecting property name enclosed in double quotes" in error_msg):
                    
                    logger.warning(f"Qwen malformed chunk error (attempt {consecutive_errors}/{max_consecutive_errors})")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"Too many consecutive API errors ({consecutive_errors}), terminating stream")
                        stream_terminated_early = True
                        
                        error_text = f"\n⚠️ Qwen streaming encountered repeated malformed chunks. This is a known API issue.\n"
                        yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': text_block_index, 'delta': {'type': Constants.DELTA_TEXT, 'text': error_text}})}\n\n"
                        break
                    
                    await asyncio.sleep(0.1)
                    continue
                else:
                    logger.error(f"API error: {api_error}")
                    stream_terminated_early = True
                    break
                    
            except Exception as general_error:
                consecutive_errors += 1
                logger.error(f"Unexpected streaming error (attempt {consecutive_errors}/{max_consecutive_errors}): {general_error}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), terminating stream")
                    stream_terminated_early = True
                    break
                
                await asyncio.sleep(0.1)
                continue

    except Exception as outer_error:
        logger.error(f"Fatal streaming error: {outer_error}")
        stream_terminated_early = True

    # 发送最终事件
    try:
        if current_tool_calls:
            logger.info(f"🔧 流式传输完成，校验 {len(current_tool_calls)} 个工具调用")
            for tool_id, tool_data in current_tool_calls.items():
                tool_name = tool_data.get('name', '')
                if tool_name:
                    try:
                        args_buffer = tool_data.get('args_buffer', '{}')
                        if args_buffer:
                            try:
                                args_dict = json.loads(args_buffer)
                                validated_args = validate_todowrite_tool_call(tool_name, args_dict)
                                current_tool_calls[tool_id]['validated_args'] = validated_args
                                logger.info(f"✅ 工具 {tool_name} 参数校验完成")
                            except json.JSONDecodeError as parse_error:
                                logger.warning(f"⚠️ 工具 {tool_name} 参数解析失败: {parse_error}")
                        else:
                            logger.warning(f"⚠️ 工具 {tool_name} 参数为空")
                    except Exception as validation_error:
                        logger.warning(f"⚠️ 工具 {tool_name} 校验失败: {validation_error}")
        
        yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': text_block_index})}\n\n"
        
        for tool_data in current_tool_calls.values():
            yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': tool_data['index']})}\n\n"
        
        if stream_terminated_early and final_stop_reason == Constants.STOP_END_TURN:
            final_stop_reason = Constants.STOP_ERROR

        final_response = litellm.stream_chunk_builder(all_chunks)
        if final_response and hasattr(final_response, 'usage'):
            output_tokens = getattr(final_response.usage, "completion_tokens", 0)
        
        usage_data = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        yield f"event: {Constants.EVENT_MESSAGE_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_DELTA, 'delta': {'stop_reason': final_stop_reason, 'stop_sequence': None}, 'usage': usage_data})}\n\n"
        yield f"event: {Constants.EVENT_MESSAGE_STOP}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_STOP})}\n\n"
        
        # 记录日志
        try:
            logger.info(f"📤 流式模型响应结果:")
            logger.info(f"   模型: {original_request.original_model or original_request.model}")
            logger.info(f"   停止原因: {final_stop_reason}")
            logger.info(f"   输入令牌: {input_tokens}")
            logger.info(f"   输出令牌: {output_tokens}")
            logger.info(f"   流式块数量: {len(all_chunks)}")
            
            if accumulated_text:
                display_text = accumulated_text[:500] + "..." if len(accumulated_text) > 500 else accumulated_text
                logger.info(f"   累积文本内容: {display_text}")
            
            if current_tool_calls:
                logger.info(f"   工具调用: {len(current_tool_calls)} 个工具")
                for i, (tool_id, tool_data) in enumerate(current_tool_calls.items()):
                    logger.info(f"     工具 {i+1}: {tool_data['name']} (ID: {tool_id})")
                    try:
                        args_dict = json.loads(tool_data['args_buffer'])
                        args_str = json.dumps(args_dict, ensure_ascii=False)
                        display_args = args_str[:200] + "..." if len(args_str) > 200 else args_str
                        logger.info(f"     参数: {display_args}")
                    except:
                        display_args = tool_data['args_buffer'][:200] + "..." if len(tool_data['args_buffer']) > 200 else tool_data['args_buffer']
                        logger.info(f"     参数(原始): {display_args}")
            
            if stream_terminated_early:
                logger.warning(f"   流式传输提前终止")
                
        except Exception as log_error:
            logger.warning(f"记录流式响应日志时出错: {log_error}")
        
        if malformed_chunks_count > 0:
            logger.info(f"Stream completed with {malformed_chunks_count} malformed chunks handled")
            
    except Exception as final_error:
        logger.error(f"Error sending final SSE events: {final_error}")

