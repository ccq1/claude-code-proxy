"""
错误处理工具
"""
from app.config import config


def classify_local_model_error(error_msg: str) -> str:
    """为常见的本地模型错误提供具体的错误指导"""
    error_lower = error_msg.lower()
    
    # 流式/解析错误
    if "error parsing chunk" in error_lower and "expecting property name" in error_lower:
        return "Local model streaming parsing error (malformed JSON chunk). This may be an intermittent API issue. Please try again or disable streaming by setting stream=false."
    
    # 工具 schema 验证错误
    if "function_declarations" in error_lower and "format" in error_lower:
        return "Tool schema validation error. Check your tool parameter definitions for unsupported format types or properties."
    
    # 速率限制
    elif "rate limit" in error_lower or "quota" in error_lower:
        return "Rate limit exceeded. Please wait a moment and try again."
    
    # 认证问题
    elif "api key" in error_lower or "authentication" in error_lower or "unauthorized" in error_lower:
        return "API key error. Please check that your API_KEY is valid for your local model service."
    
    # 连接问题
    elif "connection" in error_lower or "timeout" in error_lower or "refused" in error_lower:
        return f"Connection error. Please check that your local model service is running at {config.base_url} and accessible."
    
    # 解析/流式问题
    elif "parsing" in error_lower or "json" in error_lower or "malformed" in error_lower:
        return "Response parsing error. This may be a temporary API issue - please retry your request."
    
    # 模型未找到
    elif "model" in error_lower and ("not found" in error_lower or "not exist" in error_lower):
        return "Model not found. Please check that the specified model is available on your local model service."
    
    # Token/长度问题
    elif "token" in error_lower and ("limit" in error_lower or "exceed" in error_lower):
        return "Token limit exceeded. Please reduce the length of your request or increase the max_tokens parameter."
    
    # 默认：返回原始消息
    return error_msg

