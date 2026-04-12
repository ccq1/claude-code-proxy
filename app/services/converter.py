"""
请求/响应转换服务
"""
import json
import re
import uuid
import logging
from typing import Dict, Any

from app.constants import Constants
from app.config import config

logger = logging.getLogger(__name__)

BILLING_HEADER_PATTERN = r"(?im)^x-anthropic-billing-header:[^\n]*\n?"
AGENT_SDK_PREFIX = "You are a Claude agent, built on Anthropic's Claude Agent SDK."
SESSION_TITLE_PROMPT_MARKER = (
    "Generate a concise, sentence-case title (3-7 words) "
    "that captures the main topic or goal of this coding session."
)
SESSION_TITLE_JSON_MARKER = 'Return JSON with a single "title" field.'
SESSION_TITLE_PROMPT_REWRITE = """Generate a concise, sentence-case title (3-7 words) that captures the main topic or goal of this coding session. The title should be clear enough that the user recognizes the session in a list. Use sentence case: capitalize only the first word and proper nouns.

Return JSON with a single "title" field.

Return the title in the same language as the user's latest message. Do not default to English. If the user's latest message is in Chinese, return a Chinese title. If it is in English, return an English title. Preserve proper nouns, technical terms, and code identifiers when helpful.

Good examples:
{"title": "修复移动端登录按钮"}
{"title": "Add OAuth authentication"}
{"title": "调试失败的 CI 测试"}
{"title": "Refactor API client error handling"}

Bad (too vague): {"title": "Code changes"}
Bad (too long): {"title": "Investigate and fix the issue where the login button does not respond on mobile devices"}
Bad (wrong case): {"title": "Fix Login Button On Mobile"}"""


def normalize_system_prompt(system_text: str) -> str:
    """清理并按需重写系统提示词。"""
    if not system_text:
        return ""

    cleaned = re.sub(BILLING_HEADER_PATTERN, "", system_text)
    cleaned = cleaned.replace(AGENT_SDK_PREFIX, "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    if (
        SESSION_TITLE_PROMPT_MARKER in cleaned
        and SESSION_TITLE_JSON_MARKER in cleaned
    ):
        cleaned = re.sub(
            r"Generate a concise, sentence-case title \(3-7 words\).*",
            SESSION_TITLE_PROMPT_REWRITE,
            cleaned,
            flags=re.DOTALL,
        ).strip()
        logger.info("📝 Rewrote session title prompt to follow the user's language")

    return cleaned


def clean_model_schema(schema: Any) -> Any:
    """递归清理 JSON schema 中不支持的字段"""
    if isinstance(schema, dict):
        schema.pop("additionalProperties", None)
        schema.pop("default", None)

        if schema.get("type") == "string" and "format" in schema:
            allowed_formats = {"enum", "date-time"}
            if schema["format"] not in allowed_formats:
                logger.debug(f"Removing unsupported format '{schema['format']}' for string type in model schema")
                schema.pop("format")

        for key, value in list(schema.items()):
            schema[key] = clean_model_schema(value)
                
    elif isinstance(schema, list):
        return [clean_model_schema(item) for item in schema]
            
    return schema


def parse_tool_result_content(content) -> str:
    """解析工具结果内容"""
    if content is None:
        return "No content provided"

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        result_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == Constants.CONTENT_TEXT:
                result_parts.append(item.get("text", ""))
            elif isinstance(item, str):
                result_parts.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    result_parts.append(item.get("text", ""))
                else:
                    try:
                        result_parts.append(json.dumps(item))
                    except:
                        result_parts.append(str(item))
        return "\n".join(result_parts).strip()

    if isinstance(content, dict):
        if content.get("type") == Constants.CONTENT_TEXT:
            return content.get("text", "")
        try:
            return json.dumps(content)
        except:
            return str(content)

    try:
        return str(content)
    except:
        return "Unparseable content"


def validate_todowrite_tool_call(tool_name: str, arguments_dict: dict) -> dict:
    """校验 TodoWrite 工具调用的参数格式"""
    if tool_name != Constants.TODO_WRITE_TOOL_NAME:
        return arguments_dict
    
    logger.info(f"🔧 TodoWrite 校验开始，原始参数: {arguments_dict}")
    
    # 处理 raw_arguments 的情况
    if "raw_arguments" in arguments_dict and Constants.TODO_WRITE_TODOS_PARAM not in arguments_dict:
        raw_args = arguments_dict["raw_arguments"]
        logger.info(f"🔧 发现 raw_arguments，尝试解析: {str(raw_args)[:200]}...")
        
        extracted = False
        try:
            if isinstance(raw_args, str):
                parsed_raw = json.loads(raw_args)
                if isinstance(parsed_raw, dict) and Constants.TODO_WRITE_TODOS_PARAM in parsed_raw:
                    arguments_dict[Constants.TODO_WRITE_TODOS_PARAM] = parsed_raw[Constants.TODO_WRITE_TODOS_PARAM]
                    arguments_dict.pop("raw_arguments", None)
                    logger.info(f"🔧 TodoWrite: 从 raw_arguments JSON 中成功提取 todos 参数")
                    extracted = True
        except json.JSONDecodeError as e:
            logger.info(f"🔧 JSON 解析失败: {e}，尝试修复单引号")
            if isinstance(raw_args, str):
                try:
                    import ast
                    try:
                        parsed_raw = ast.literal_eval(raw_args)
                        if isinstance(parsed_raw, dict) and Constants.TODO_WRITE_TODOS_PARAM in parsed_raw:
                            arguments_dict[Constants.TODO_WRITE_TODOS_PARAM] = parsed_raw[Constants.TODO_WRITE_TODOS_PARAM]
                            arguments_dict.pop("raw_arguments", None)
                            logger.info(f"🔧 TodoWrite: 使用 ast.literal_eval 成功提取 todos 参数")
                            extracted = True
                    except (ValueError, SyntaxError):
                        fixed_json = raw_args.replace("'", '"')
                        logger.info(f"🔧 修复后的 JSON: {fixed_json[:200]}...")
                        parsed_raw = json.loads(fixed_json)
                        if isinstance(parsed_raw, dict) and Constants.TODO_WRITE_TODOS_PARAM in parsed_raw:
                            arguments_dict[Constants.TODO_WRITE_TODOS_PARAM] = parsed_raw[Constants.TODO_WRITE_TODOS_PARAM]
                            arguments_dict.pop("raw_arguments", None)
                            logger.info(f"🔧 TodoWrite: 修复单引号后成功提取 todos 参数")
                            extracted = True
                        
                except json.JSONDecodeError as fix_error:
                    logger.info(f"🔧 修复单引号后仍然解析失败: {fix_error}，尝试正则表达式")
                except Exception as general_error:
                    logger.info(f"🔧 ast.literal_eval 失败: {general_error}，尝试 JSON 修复")
                    todos_pattern = r'"todos":\s*(\[.*?\])'
                    match = re.search(todos_pattern, raw_args, re.DOTALL)
                    if match:
                        try:
                            todos_array = json.loads(match.group(1))
                            arguments_dict[Constants.TODO_WRITE_TODOS_PARAM] = todos_array
                            arguments_dict.pop("raw_arguments", None)
                            logger.info(f"🔧 TodoWrite: 通过正则表达式从 raw_arguments 中提取了 todos")
                            extracted = True
                        except json.JSONDecodeError:
                            pass
        
        if not extracted:
            logger.warning(f"🔧 TodoWrite: 无法从 raw_arguments 中提取 todos 参数")
    
    # 检查 todos 参数
    if Constants.TODO_WRITE_TODOS_PARAM in arguments_dict:
        todos_value = arguments_dict[Constants.TODO_WRITE_TODOS_PARAM]
        
        if isinstance(todos_value, str):
            try:
                parsed_todos = json.loads(todos_value)
                if isinstance(parsed_todos, list):
                    arguments_dict[Constants.TODO_WRITE_TODOS_PARAM] = parsed_todos
                    logger.info(f"🔧 TodoWrite: 修复了字符串格式的 todos 参数")
            except json.JSONDecodeError:
                try:
                    array_pattern = r'\[.*?\]'
                    matches = re.findall(array_pattern, todos_value, re.DOTALL)
                    if matches:
                        parsed_array = json.loads(matches[0])
                        if isinstance(parsed_array, list):
                            arguments_dict[Constants.TODO_WRITE_TODOS_PARAM] = parsed_array
                            logger.info(f"🔧 TodoWrite: 从字符串中提取了 todos 数组")
                except:
                    pass
    
    logger.info(f"🔧 TodoWrite 校验完成，最终参数: {arguments_dict}")
    return arguments_dict


def convert_anthropic_to_litellm(anthropic_request,num_tools:int) -> Dict[str, Any]:
    """将 Anthropic API 请求格式转换为 LiteLLM 格式"""
    litellm_messages = []
    pending_tool_messages = []
    
    # 处理 system 消息
    if anthropic_request.system:
        system_text = ""
        if isinstance(anthropic_request.system, str):
            system_text = anthropic_request.system
        elif isinstance(anthropic_request.system, list):
            text_parts = []
            for block in anthropic_request.system:
                if hasattr(block, 'type') and block.type == Constants.CONTENT_TEXT:
                    text_parts.append(block.text)
                elif isinstance(block, dict) and block.get("type") == Constants.CONTENT_TEXT:
                    text_parts.append(block.get("text", ""))
            system_text = "\n\n".join(text_parts)
        
        system_text = normalize_system_prompt(system_text)
        if system_text.strip():
            litellm_messages.append({"role": Constants.ROLE_SYSTEM, "content": system_text.strip()})

    # 处理消息
    for msg in anthropic_request.messages:
        if isinstance(msg.content, str):
            litellm_messages.append({"role": msg.role, "content": msg.content})
            continue

        text_parts = []
        image_parts = []
        tool_calls = []

        for block in msg.content:
            if block.type == Constants.CONTENT_TEXT:
                text_parts.append(block.text)
            elif block.type == Constants.CONTENT_IMAGE:
                if (isinstance(block.source, dict) and 
                    block.source.get("type") == "base64" and
                    "media_type" in block.source and "data" in block.source):
                    image_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{block.source['media_type']};base64,{block.source['data']}"
                        }
                    })
            elif block.type == Constants.CONTENT_TOOL_USE and msg.role == Constants.ROLE_ASSISTANT:
                tool_calls.append({
                    "id": block.id,
                    "type": Constants.TOOL_FUNCTION,
                    Constants.TOOL_FUNCTION: {
                        "name": block.name,
                        "arguments": json.dumps(block.input)
                    }
                })
            elif block.type == Constants.CONTENT_TOOL_RESULT and msg.role == Constants.ROLE_USER:
                if text_parts or image_parts:
                    content_parts = []
                    text_content = "".join(text_parts).strip()
                    if text_content:
                        content_parts.append({"type": Constants.CONTENT_TEXT, "text": text_content})
                    content_parts.extend(image_parts)
                    
                    litellm_messages.append({
                        "role": Constants.ROLE_USER,
                        "content": content_parts[0]["text"] if len(content_parts) == 1 and content_parts[0]["type"] == Constants.CONTENT_TEXT else content_parts
                    })
                    text_parts.clear()
                    image_parts.clear()

                parsed_content = parse_tool_result_content(block.content)
                pending_tool_messages.append({
                    "role": Constants.ROLE_TOOL,
                    "tool_call_id": block.tool_use_id,
                    "content": parsed_content
                })

        # 根据角色处理消息
        if msg.role == Constants.ROLE_USER:
            if text_parts or image_parts:
                content_parts = []
                text_content = "".join(text_parts).strip()
                if text_content:
                    content_parts.append({"type": Constants.CONTENT_TEXT, "text": text_content})
                content_parts.extend(image_parts)
                
                litellm_messages.append({
                    "role": Constants.ROLE_USER,
                    "content": content_parts[0]["text"] if len(content_parts) == 1 and content_parts[0]["type"] == Constants.CONTENT_TEXT else content_parts
                })
            litellm_messages.extend(pending_tool_messages)
            pending_tool_messages.clear()
            
        elif msg.role == Constants.ROLE_ASSISTANT:
            assistant_msg = {"role": Constants.ROLE_ASSISTANT}
            
            content_parts = []
            text_content = "".join(text_parts).strip()
            if text_content:
                content_parts.append({"type": Constants.CONTENT_TEXT, "text": text_content})
            content_parts.extend(image_parts)
            
            if content_parts:
                assistant_msg["content"] = content_parts[0]["text"] if len(content_parts) == 1 and content_parts[0]["type"] == Constants.CONTENT_TEXT else content_parts
            else: 
                assistant_msg["content"] = None
                
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
                
            if assistant_msg.get("content") or assistant_msg.get("tool_calls"):
                litellm_messages.append(assistant_msg)

    # 构建最终请求
    litellm_request = {
        "model": anthropic_request.model,
        "messages": litellm_messages,
        "max_tokens": min(anthropic_request.max_tokens, config.max_tokens_limit),
        "temperature": anthropic_request.temperature,
        "stream": anthropic_request.stream,
    }

    if anthropic_request.stream:
        # Ask OpenAI-compatible streaming endpoints to include usage
        # in the final chunk when the upstream implementation supports it.
        litellm_request["stream_options"] = {"include_usage": True}

    # 添加可选参数
    if anthropic_request.stop_sequences:
        litellm_request["stop"] = anthropic_request.stop_sequences
    if anthropic_request.top_p is not None:
        litellm_request["top_p"] = anthropic_request.top_p
    if anthropic_request.top_k is not None:
        litellm_request["topK"] = anthropic_request.top_k

    # 添加工具定义
    if anthropic_request.tools:
        valid_tools = []
        for tool in anthropic_request.tools:
            if tool.name and tool.name.strip():
                cleaned_schema = clean_model_schema(tool.input_schema)
                valid_tools.append({
                    "type": Constants.TOOL_FUNCTION,
                    Constants.TOOL_FUNCTION: {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": cleaned_schema
                    }
                })
        if valid_tools:
            litellm_request["tools"] = valid_tools
            # 枚举工具
            #logger.info(f"🔧 工具定义:")
            #for i, tool in enumerate(valid_tools):
                #func_info = tool[Constants.TOOL_FUNCTION]
                #logger.info(f"   工具 {i+1}: {func_info['name']}")
                # if func_info['name'] == 'Write':

                #     logger.info(f"🔧 工具定义 Write 参数: {json.dumps(func_info['parameters'])}")
                #logger.info(f"🔧 工具定义 Write 参数示例: {json.dumps(func_info['description'])}")

    # 添加工具选择配置
    if anthropic_request.tool_choice:
        choice_type = anthropic_request.tool_choice.get("type")
        if choice_type == "auto":
            litellm_request["tool_choice"] = "auto"
        elif choice_type == "any":
            litellm_request["tool_choice"] = "auto"
        elif choice_type == "tool" and "name" in anthropic_request.tool_choice:
            litellm_request["tool_choice"] = {
                "type": Constants.TOOL_FUNCTION, 
                Constants.TOOL_FUNCTION: {"name": anthropic_request.tool_choice["name"]}
            }
        else:
            litellm_request["tool_choice"] = "auto"

    # 添加 thinking 配置
    if anthropic_request.thinking is not None:
        if anthropic_request.thinking.enabled:
            litellm_request["thinkingConfig"] = {"thinkingBudget": 24576}
        else:
            litellm_request["thinkingConfig"] = {"thinkingBudget": 0}

    # 添加是否思考 - 如果有工具就开启思考，否则关闭思考
    litellm_request['extra_body'] = {
            "chat_template_kwargs": {
                "enable_thinking": num_tools > 0
                # "enable_thinking": True
            }
        }
    logger.info(f"💡 思考配置: {'启用' if num_tools > 0 else '禁用'} (工具数量: {num_tools})")



    # 添加用户元数据
    if (anthropic_request.metadata and 
        "user_id" in anthropic_request.metadata and
        isinstance(anthropic_request.metadata["user_id"], str)):
        litellm_request["user"] = anthropic_request.metadata["user_id"]

    return litellm_request


def convert_litellm_to_anthropic(litellm_response, original_request):
    """将 LiteLLM 响应转换为 Anthropic API 格式"""
    from app.models.request import ContentBlockText, ContentBlockToolUse
    from app.models.response import MessagesResponse, Usage
    
    logger.info(f"非流式解析开始")
    try:
        response_id = f"msg_{uuid.uuid4()}"
        content_text = ""
        tool_calls = None
        finish_reason = "stop"
        prompt_tokens = 0
        completion_tokens = 0
        reasoning_content = None

        # 处理 LiteLLM ModelResponse 对象格式
        if hasattr(litellm_response, 'choices') and hasattr(litellm_response, 'usage'):
            choices = litellm_response.choices
            message = choices[0].message if choices else None
            content_text = getattr(message, 'content', "") or ""
            reasoning_content = getattr(message, 'reasoning_content', None)
            tool_calls = getattr(message, 'tool_calls', None)
            finish_reason = choices[0].finish_reason if choices else "stop"
            response_id = getattr(litellm_response, 'id', response_id)
            
            if hasattr(litellm_response, 'usage'):
                usage = litellm_response.usage
                prompt_tokens = getattr(usage, "prompt_tokens", 0)
                completion_tokens = getattr(usage, "completion_tokens", 0)
                
        # 处理字典格式响应
        elif isinstance(litellm_response, dict):
            choices = litellm_response.get("choices", [])
            message = choices[0].get("message", {}) if choices else {}
            content_text = message.get("content", "") or ""
            reasoning_content = message.get("reasoning_content")
            tool_calls = message.get("tool_calls")
            finish_reason = choices[0].get("finish_reason", "stop") if choices else "stop"
            usage = litellm_response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            response_id = litellm_response.get("id", response_id)


        if reasoning_content:
            if config.log_response_details:
                print(f"✅ 模型的思考内容 (Reasoning Content): \n{reasoning_content}")
                logger.info(f"Reasoning Content 捕获成功: {reasoning_content[:100]}...")
            else:
                logger.info(f"Reasoning Content 捕获成功: {len(reasoning_content)} 字符")
        # 检查write 工具和内容
        if '<function=Write>' in content_text:
            logger.info(f"❌ write 工具调用疑似错误放在content字段里: {content_text[:100]}...")
        

        # 构建内容块
        content_blocks = []
        
        # 【新增】如果有 reasoning_content，先添加 thinking 内容块
        if reasoning_content:
            from app.models.request import ContentBlockThinking
            content_blocks.append(ContentBlockThinking(type=Constants.CONTENT_THINKING, thinking=reasoning_content))
        
        if content_text:
            content_blocks.append(ContentBlockText(type=Constants.CONTENT_TEXT, text=content_text))

        # 处理工具调用
        if tool_calls:
            if not isinstance(tool_calls, list):
                tool_calls = [tool_calls]

            for tool_call in tool_calls:
                try:
                    if isinstance(tool_call, dict):
                        tool_id = tool_call.get("id", f"tool_{uuid.uuid4()}")
                        function_data = tool_call.get(Constants.TOOL_FUNCTION, {})
                        name = function_data.get("name", "")
                        arguments_str = function_data.get("arguments", "{}")
                    elif hasattr(tool_call, "id") and hasattr(tool_call, Constants.TOOL_FUNCTION):
                        tool_id = tool_call.id
                        name = tool_call.function.name
                        arguments_str = tool_call.function.arguments
                    else:
                        continue

                    if not name:
                        continue

                    try:
                        arguments_dict = json.loads(arguments_str)
                    except json.JSONDecodeError:
                        arguments_dict = {"raw_arguments": arguments_str}

                    arguments_dict = validate_todowrite_tool_call(name, arguments_dict)

                    if name == "Write" and config.log_response_details:
                        logger.info(f"🔧 Write 工具调用参数 --> : {arguments_dict}")

                    content_blocks.append(ContentBlockToolUse(
                        type=Constants.CONTENT_TOOL_USE,
                        id=tool_id,
                        name=name,
                        input=arguments_dict
                    ))
                except Exception as e:
                    logger.warning(f"Error processing tool call: {e}")
                    continue

        # 检测仅有 thinking 无 text 无 tool_calls 的异常情况
        has_thinking = any(
            getattr(b, 'type', None) == Constants.CONTENT_THINKING for b in content_blocks
        )
        has_text = any(
            getattr(b, 'type', None) == Constants.CONTENT_TEXT and getattr(b, 'text', '') for b in content_blocks
        )
        has_tool_use = any(
            getattr(b, 'type', None) == Constants.CONTENT_TOOL_USE for b in content_blocks
        )
        if has_thinking and not has_text and not has_tool_use:
            logger.warning(
                f"⚠️ 仅有 thinking 无 text 无 tool_calls(非流式)! "
                f"模型={original_request.original_model or original_request.model}, "
                f"finish_reason={finish_reason}, "
                f"reasoning_len={len(reasoning_content) if reasoning_content else 0}, "
                f"content_text='{content_text[:100]}'"
            )

        # 确保至少有一个内容块
        if not content_blocks:
            content_blocks.append(ContentBlockText(type=Constants.CONTENT_TEXT, text=""))

        # 映射停止原因
        if finish_reason == "length":
            stop_reason = Constants.STOP_MAX_TOKENS
        elif finish_reason == "tool_calls":
            stop_reason = Constants.STOP_TOOL_USE
        elif finish_reason is None and tool_calls:
            stop_reason = Constants.STOP_TOOL_USE
        else:
            stop_reason = Constants.STOP_END_TURN

        return MessagesResponse(
            id=response_id,
            model=original_request.original_model or original_request.model,
            role=Constants.ROLE_ASSISTANT,
            content=content_blocks,
            stop_reason=stop_reason,
            stop_sequence=None,
            usage=Usage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens
            )
        )
        
    except Exception as e:
        logger.error(f"Error converting response: {e}")
        from app.models.request import ContentBlockText
        from app.models.response import MessagesResponse, Usage
        
        return MessagesResponse(
            id=f"msg_error_{uuid.uuid4()}",
            model=original_request.original_model or original_request.model,
            role=Constants.ROLE_ASSISTANT, 
            content=[ContentBlockText(type=Constants.CONTENT_TEXT, text="Response conversion error")],
            stop_reason=Constants.STOP_ERROR,
            usage=Usage(input_tokens=0, output_tokens=0)
        )
