"""
常量定义模块
"""


class Constants:
    """API 常量定义"""
    
    # 角色常量
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"
    ROLE_TOOL = "tool"
    
    # 内容类型常量
    CONTENT_TEXT = "text"
    CONTENT_THINKING = "thinking"
    CONTENT_IMAGE = "image"
    CONTENT_TOOL_USE = "tool_use"
    CONTENT_TOOL_RESULT = "tool_result"
    
    # 工具常量
    TOOL_FUNCTION = "function"
    
    # 停止原因常量
    STOP_END_TURN = "end_turn"
    STOP_MAX_TOKENS = "max_tokens"
    STOP_TOOL_USE = "tool_use"
    STOP_ERROR = "error"
    
    # SSE 事件常量
    EVENT_MESSAGE_START = "message_start"
    EVENT_MESSAGE_STOP = "message_stop"
    EVENT_MESSAGE_DELTA = "message_delta"
    EVENT_CONTENT_BLOCK_START = "content_block_start"
    EVENT_CONTENT_BLOCK_STOP = "content_block_stop"
    EVENT_CONTENT_BLOCK_DELTA = "content_block_delta"
    EVENT_PING = "ping"
    
    # Delta 类型常量
    DELTA_TEXT = "text_delta"
    DELTA_THINKING = "thinking_delta"
    DELTA_INPUT_JSON = "input_json_delta"
    
    # TodoWrite 工具相关的常量
    TODO_WRITE_TOOL_NAME = "TodoWrite"
    TODO_WRITE_TODOS_PARAM = "todos"

