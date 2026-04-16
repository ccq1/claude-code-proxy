"""
流式响应处理服务
"""
import json
import asyncio
import logging
import re
import litellm

from app.constants import Constants
from app.config import config
from .converter import (
    contains_text_tool_call_marker,
    extract_text_based_tool_calls,
    validate_todowrite_tool_call,
)

logger = logging.getLogger(__name__)
STREAMING_TEXT_TOOL_CALL_MARKERS = ("<tool_call>", "<function=")


def find_partial_tool_call_suffix_start(text: str) -> int | None:
    """找到文本末尾疑似工具调用起始片段的位置。"""
    if not text:
        return None

    lowered = text.lower()
    best_index = None
    for marker in STREAMING_TEXT_TOOL_CALL_MARKERS:
        marker_lower = marker.lower()
        max_prefix_len = len(marker_lower) - 1
        for prefix_len in range(max_prefix_len, 0, -1):
            prefix = marker_lower[:prefix_len]
            if lowered.endswith(prefix):
                candidate_index = len(text) - prefix_len
                if best_index is None or candidate_index < best_index:
                    best_index = candidate_index
                break
    return best_index


def split_text_for_tool_call_streaming(text: str) -> tuple[str, str]:
    """拆分可安全直发的文本和需要缓冲的疑似工具调用片段。"""
    if not text:
        return "", ""

    lowered = text.lower()
    marker_positions = [
        lowered.find(marker.lower())
        for marker in STREAMING_TEXT_TOOL_CALL_MARKERS
        if lowered.find(marker.lower()) != -1
    ]
    if marker_positions:
        marker_index = min(marker_positions)
        return text[:marker_index], text[marker_index:]

    partial_index = find_partial_tool_call_suffix_start(text)
    if partial_index is not None:
        return text[:partial_index], text[partial_index:]

    return text, ""


async def handle_streaming_with_recovery(response_generator, original_request, input_tokens: int):
    """增强的流式处理器，带有错误恢复机制"""
    logger.info(f"stream解析开始")
    message_id = f"msg_{__import__('uuid').uuid4().hex[:24]}"
    initial_input_tokens = input_tokens
    
    # 发送初始 SSE 事件
    yield f"event: {Constants.EVENT_MESSAGE_START}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_START, 'message': {'id': message_id, 'type': 'message', 'role': Constants.ROLE_ASSISTANT, 'model': original_request.original_model or original_request.model, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': input_tokens, 'output_tokens': 0}}})}\n\n"
    
    yield f"event: {Constants.EVENT_PING}\ndata: {json.dumps({'type': Constants.EVENT_PING})}\n\n"

    # 流式状态管理
    accumulated_text = ""
    pending_text_suffix = ""
    buffered_text_tool_call = ""
    accumulated_thinking = ""
    emitted_thinking = ""
    pending_thinking_suffix = ""
    buffered_thinking_tool_call = ""
    thinking_block_started = False
    thinking_block_ended = False
    text_block_started = False
    next_block_index = 0
    text_block_index = -1
    thinking_block_index = -1
    tool_block_counter = 0
    current_tool_calls = {}
    output_tokens = 0
    total_tokens = None
    provider_prompt_tokens = None
    provider_reported_zero_prompt_tokens = False
    final_stop_reason = Constants.STOP_END_TURN
    
    # 错误恢复追踪
    consecutive_errors = 0
    max_consecutive_errors = 10
    stream_terminated_early = False
    malformed_chunks_count = 0
    max_malformed_chunks = 20
    chunk_count = 0
    
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
                chunk_count += 1
                
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
                delta_reasoning_text = None
                delta_tool_calls = None
                chunk_finish_reason = None

                if hasattr(chunk, 'choices') and chunk.choices:
                    choice = chunk.choices[0]
                    if hasattr(choice, 'delta') and choice.delta:
                        delta = choice.delta
                        delta_content_text = getattr(delta, 'content', None)
                        delta_reasoning_text = getattr(delta, 'reasoning_content', None)
                        if hasattr(delta, 'tool_calls'):
                            delta_tool_calls = delta.tool_calls
                    chunk_finish_reason = getattr(choice, 'finish_reason', None)
                elif isinstance(chunk, dict):
                    choices = chunk.get("choices", [])
                    if choices:
                        choice = choices[0]
                        delta = choice.get("delta", {})
                        delta_content_text = delta.get("content")
                        delta_reasoning_text = delta.get("reasoning_content")
                        delta_tool_calls = delta.get("tool_calls")
                        chunk_finish_reason = choice.get("finish_reason")

                if hasattr(chunk, 'usage') and chunk.usage:
                    chunk_prompt_tokens = getattr(chunk.usage, 'prompt_tokens', None)
                    output_tokens = getattr(chunk.usage, 'completion_tokens', 0)
                    chunk_total_tokens = getattr(chunk.usage, 'total_tokens', None)
                    if chunk_prompt_tokens is not None:
                        if chunk_prompt_tokens > 0:
                            provider_prompt_tokens = chunk_prompt_tokens
                            input_tokens = chunk_prompt_tokens
                        elif initial_input_tokens > 0:
                            provider_reported_zero_prompt_tokens = True
                    if chunk_total_tokens is not None:
                        total_tokens = chunk_total_tokens
                elif isinstance(chunk, dict) and "usage" in chunk:
                    usage = chunk["usage"]
                    chunk_prompt_tokens = usage.get("prompt_tokens")
                    output_tokens = usage.get("completion_tokens", 0)
                    chunk_total_tokens = usage.get("total_tokens")
                    if chunk_prompt_tokens is not None:
                        if chunk_prompt_tokens > 0:
                            provider_prompt_tokens = chunk_prompt_tokens
                            input_tokens = chunk_prompt_tokens
                        elif initial_input_tokens > 0:
                            provider_reported_zero_prompt_tokens = True
                    if chunk_total_tokens is not None:
                        total_tokens = chunk_total_tokens

                if delta_reasoning_text:
                    accumulated_thinking += delta_reasoning_text

                    if buffered_thinking_tool_call:
                        buffered_thinking_tool_call += pending_thinking_suffix + delta_reasoning_text
                        pending_thinking_suffix = ""
                        safe_thinking_to_emit = ""
                    else:
                        combined_thinking = pending_thinking_suffix + delta_reasoning_text
                        pending_thinking_suffix = ""
                        safe_thinking_to_emit, buffered_fragment = split_text_for_tool_call_streaming(
                            combined_thinking
                        )
                        if buffered_fragment:
                            buffered_thinking_tool_call = buffered_fragment

                    if safe_thinking_to_emit:
                        if not thinking_block_started:
                            thinking_block_index = next_block_index
                            next_block_index += 1
                            thinking_block_started = True
                            yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': thinking_block_index, 'content_block': {'type': Constants.CONTENT_THINKING, 'thinking': ''}})}\n\n"

                        emitted_thinking += safe_thinking_to_emit
                        yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': thinking_block_index, 'delta': {'type': Constants.DELTA_THINKING, 'thinking': safe_thinking_to_emit}})}\n\n"

                if delta_content_text or delta_tool_calls:
                    if thinking_block_started and not thinking_block_ended:
                        thinking_block_ended = True
                        yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': thinking_block_index})}\n\n"
                        logger.info(f"💭 思考完成，共 {len(accumulated_thinking)} 字符")

                if delta_content_text:
                    if buffered_text_tool_call:
                        buffered_text_tool_call += pending_text_suffix + delta_content_text
                        pending_text_suffix = ""
                        text_to_emit = ""
                    else:
                        combined_text = pending_text_suffix + delta_content_text
                        pending_text_suffix = ""
                        text_to_emit, buffered_fragment = split_text_for_tool_call_streaming(combined_text)
                        if buffered_fragment:
                            buffered_text_tool_call = buffered_fragment

                    if text_to_emit:
                        if not text_block_started:
                            text_block_index = next_block_index
                            next_block_index += 1
                            text_block_started = True
                            yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': text_block_index, 'content_block': {'type': Constants.CONTENT_TEXT, 'text': ''}})}\n\n"

                        accumulated_text += text_to_emit
                        yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': text_block_index, 'delta': {'type': Constants.DELTA_TEXT, 'text': text_to_emit}})}\n\n"

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
                                if not text_block_started:
                                    text_block_index = next_block_index
                                    next_block_index += 1
                                    text_block_started = True
                                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': text_block_index, 'content_block': {'type': Constants.CONTENT_TEXT, 'text': ''}})}\n\n"
                                
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
        recovered_tool_calls = {}
        if pending_thinking_suffix:
            if buffered_thinking_tool_call:
                buffered_thinking_tool_call += pending_thinking_suffix
            else:
                if not thinking_block_started:
                    thinking_block_index = next_block_index
                    next_block_index += 1
                    thinking_block_started = True
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': thinking_block_index, 'content_block': {'type': Constants.CONTENT_THINKING, 'thinking': ''}})}\n\n"
                emitted_thinking += pending_thinking_suffix
                yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': thinking_block_index, 'delta': {'type': Constants.DELTA_THINKING, 'thinking': pending_thinking_suffix}})}\n\n"
            pending_thinking_suffix = ""

        if pending_text_suffix:
            if buffered_text_tool_call:
                buffered_text_tool_call += pending_text_suffix
            else:
                if not text_block_started:
                    text_block_index = next_block_index
                    next_block_index += 1
                    text_block_started = True
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': text_block_index, 'content_block': {'type': Constants.CONTENT_TEXT, 'text': ''}})}\n\n"
                accumulated_text += pending_text_suffix
                yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': text_block_index, 'delta': {'type': Constants.DELTA_TEXT, 'text': pending_text_suffix}})}\n\n"
            pending_text_suffix = ""

        if not current_tool_calls and buffered_text_tool_call:
            remaining_text, extracted_tool_calls = extract_text_based_tool_calls(
                buffered_text_tool_call
            )
            if extracted_tool_calls:
                logger.error(
                    "❌ Model emitted text-based tool call instead of structured tool_calls during streaming; recovered via proxy fallback. content_preview=%r",
                    buffered_text_tool_call[:120],
                )
                logger.error(
                    "❌ Recovered tool-call raw payload (pre-fix): %r",
                    buffered_text_tool_call[:500],
                )
                if remaining_text:
                    if not text_block_started:
                        text_block_index = next_block_index
                        next_block_index += 1
                        text_block_started = True
                        yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': text_block_index, 'content_block': {'type': Constants.CONTENT_TEXT, 'text': ''}})}\n\n"
                    accumulated_text += remaining_text
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': text_block_index, 'delta': {'type': Constants.DELTA_TEXT, 'text': remaining_text}})}\n\n"

                for tool_call in extracted_tool_calls:
                    tool_id = tool_call["id"]
                    function_data = tool_call[Constants.TOOL_FUNCTION]
                    logger.info(
                        "✅ Recovered tool-call normalized args (post-fix): tool=%s args=%s",
                        function_data["name"],
                        function_data["arguments"],
                    )
                    tool_index = next_block_index
                    next_block_index += 1
                    recovered_tool_calls[tool_id] = {
                        "index": tool_index,
                        "name": function_data["name"],
                        "args_buffer": function_data["arguments"],
                    }
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': tool_index, 'content_block': {'type': Constants.CONTENT_TOOL_USE, 'id': tool_id, 'name': function_data['name'], 'input': {}}})}\n\n"
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': tool_index, 'delta': {'type': Constants.DELTA_INPUT_JSON, 'partial_json': function_data['arguments']}})}\n\n"

                current_tool_calls.update(recovered_tool_calls)
                final_stop_reason = Constants.STOP_TOOL_USE
            elif contains_text_tool_call_marker(buffered_text_tool_call):
                logger.error(
                    "❌ Model emitted malformed text-based tool call during streaming and proxy could not recover it. content_preview=%r",
                    buffered_text_tool_call[:120],
                )
                if not text_block_started:
                    text_block_index = next_block_index
                    next_block_index += 1
                    text_block_started = True
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': text_block_index, 'content_block': {'type': Constants.CONTENT_TEXT, 'text': ''}})}\n\n"
                accumulated_text += buffered_text_tool_call
                yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': text_block_index, 'delta': {'type': Constants.DELTA_TEXT, 'text': buffered_text_tool_call}})}\n\n"

        # 兜底: 某些模型会把 tool_call 协议吐到 reasoning(thinking) 里而不是 content/tool_calls
        thinking_recovery_source = buffered_thinking_tool_call or accumulated_thinking
        if not current_tool_calls and not accumulated_text and thinking_recovery_source:
            _, extracted_thinking_tool_calls = extract_text_based_tool_calls(
                thinking_recovery_source
            )
            if extracted_thinking_tool_calls:
                logger.error(
                    "❌ Model emitted text-based tool call inside reasoning_content during streaming; recovered via proxy fallback. thinking_preview=%r",
                    thinking_recovery_source[:120],
                )
                logger.error(
                    "❌ Recovered tool-call raw payload from reasoning (pre-fix): %r",
                    thinking_recovery_source[:500],
                )
                if thinking_block_started and not thinking_block_ended:
                    thinking_block_ended = True
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': thinking_block_index})}\n\n"

                for tool_call in extracted_thinking_tool_calls:
                    tool_id = tool_call["id"]
                    function_data = tool_call[Constants.TOOL_FUNCTION]
                    logger.info(
                        "✅ Recovered tool-call normalized args from reasoning (post-fix): tool=%s args=%s",
                        function_data["name"],
                        function_data["arguments"],
                    )
                    tool_index = next_block_index
                    next_block_index += 1
                    recovered_tool_calls[tool_id] = {
                        "index": tool_index,
                        "name": function_data["name"],
                        "args_buffer": function_data["arguments"],
                    }
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': tool_index, 'content_block': {'type': Constants.CONTENT_TOOL_USE, 'id': tool_id, 'name': function_data['name'], 'input': {}}})}\n\n"
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': tool_index, 'delta': {'type': Constants.DELTA_INPUT_JSON, 'partial_json': function_data['arguments']}})}\n\n"

                current_tool_calls.update(recovered_tool_calls)
                final_stop_reason = Constants.STOP_TOOL_USE
            elif contains_text_tool_call_marker(thinking_recovery_source):
                logger.error(
                    "❌ Model emitted malformed text-based tool call inside reasoning_content during streaming and proxy could not recover it. thinking_preview=%r",
                    thinking_recovery_source[:120],
                )

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
        
        if thinking_block_started and not thinking_block_ended:
            yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': thinking_block_index})}\n\n"
        
        if text_block_started:
            yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': text_block_index})}\n\n"
        
        for tool_data in current_tool_calls.values():
            yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': tool_data['index']})}\n\n"
        
        if stream_terminated_early and final_stop_reason == Constants.STOP_END_TURN:
            final_stop_reason = Constants.STOP_ERROR

        input_tokens = provider_prompt_tokens if provider_prompt_tokens is not None else initial_input_tokens
        computed_total_tokens = input_tokens + output_tokens
        if total_tokens is None or total_tokens < computed_total_tokens:
            total_tokens = computed_total_tokens
        
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
            logger.info(f"   总令牌: {total_tokens}")
            logger.info(f"   流式块数量: {chunk_count}")

            if provider_reported_zero_prompt_tokens and initial_input_tokens > 0:
                logger.warning(
                    f"⚠️ 上游流式 usage.prompt_tokens=0，已回退到请求侧预计算值: {initial_input_tokens}"
                )
            elif provider_prompt_tokens is None and initial_input_tokens > 0:
                logger.info(
                    f"📊 上游流式 usage 未提供 prompt_tokens，使用请求侧预计算值: {initial_input_tokens}"
                )
            
            if accumulated_thinking:
                logger.info(f"   思考内容: {len(accumulated_thinking)} 字符")
                if config.log_response_details:
                    display_thinking = accumulated_thinking[:300] + "..." if len(accumulated_thinking) > 300 else accumulated_thinking
                    logger.info(f"   思考摘要: {display_thinking}")
            
            if accumulated_text:
                if config.log_response_details:
                    display_text = accumulated_text[:500] + "..." if len(accumulated_text) > 500 else accumulated_text
                    logger.info(f"   累积文本内容: {display_text}")
                else:
                    logger.info(f"   累积文本长度: {len(accumulated_text)} 字符")

            if accumulated_thinking and not accumulated_text and not current_tool_calls:
                logger.warning(
                    f"⚠️ 仅有 thinking 无 text 无 tool_calls! "
                    f"模型={original_request.original_model or original_request.model}, "
                    f"stop_reason={final_stop_reason}, "
                    f"thinking_len={len(accumulated_thinking)}, "
                    f"chunks={chunk_count}, "
                    f"stream_terminated_early={stream_terminated_early}"
                )

            if current_tool_calls:
                logger.info(f"   工具调用: {len(current_tool_calls)} 个工具")
                if config.log_response_details:
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
