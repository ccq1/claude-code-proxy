"""
日志工具
"""
import os
import sys
import logging
from app.config import config


# 获取 Worker ID (基于进程 ID)
def get_worker_id() -> str:
    """获取 Worker ID"""
    pid = os.getpid()
    return f"W{pid}"


class Colors:
    """终端颜色常量"""
    CYAN = "\033[96m"
    BLUE = "\033[94m" 
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class WorkerFormatter(logging.Formatter):
    """带 Worker ID 的日志格式化器"""
    
    def format(self, record):
        # 添加 worker_id 属性
        record.worker_id = get_worker_id()
        return super().format(record)


class SimpleMessageFilter(logging.Filter):
    """简单的日志消息过滤器"""
    def filter(self, record):
        blocked_phrases = [
            "LiteLLM completion()",
            "HTTP Request:",
            "cost_calculator"
        ]
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            return not any(phrase in record.msg for phrase in blocked_phrases)
        return True


def setup_logging():
    """设置日志配置"""
    root_logger = logging.getLogger()
    
    # 防止重复添加 handlers
    if root_logger.handlers:
        return logging.getLogger(__name__)
    
    # 使用带 Worker ID 的格式
    log_format = '%(asctime)s - [%(worker_id)s] - %(levelname)s - %(message)s'
    formatter = WorkerFormatter(log_format)
    
    # 创建 handlers
    file_handler = logging.FileHandler('logs/proxy.log')
    file_handler.setFormatter(formatter)
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    
    # 配置 root logger
    root_logger.setLevel(getattr(logging, config.log_level.upper()))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    # 添加过滤器
    root_logger.addFilter(SimpleMessageFilter())
    
    # 配置 uvicorn 日志级别
    for uvicorn_logger in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logging.getLogger(uvicorn_logger).setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


def log_request_beautifully(method: str, path: str, requested_model: str, 
                           target_model: str, num_messages: int, 
                           num_tools: int, status_code: int):
    """美化日志输出"""
    worker_id = get_worker_id()
    
    if not sys.stdout.isatty():
        print(f"[{worker_id}] {method} {path} - {requested_model} -> {target_model} ({num_messages} messages, {num_tools} tools)")
        return
    
    # TTY 终端的彩色日志
    worker_display = f"{Colors.YELLOW}[{worker_id}]{Colors.RESET}"
    req_display = f"{Colors.CYAN}{requested_model}{Colors.RESET}"
    target_display = f"{Colors.GREEN}{target_model.replace('openai/', '')}{Colors.RESET}"
    
    endpoint = path.split("?")[0] if "?" in path else path
    tools_str = f"{Colors.MAGENTA}{num_tools} tools{Colors.RESET}"
    messages_str = f"{Colors.BLUE}{num_messages} messages{Colors.RESET}"
    
    if status_code == 200:
        status_str = f"{Colors.GREEN}✓ {status_code} OK{Colors.RESET}"
    else:
        status_str = f"{Colors.RED}✗ {status_code}{Colors.RESET}"

    log_line = f"{worker_display} {Colors.BOLD}{method} {endpoint}{Colors.RESET} {status_str}"
    model_line = f"{worker_display} Request: {req_display} → Target: {target_display} ({tools_str}, {messages_str})"

    print(log_line)
    print(model_line)
    sys.stdout.flush()


def log_tool_names(logger: logging.Logger, path: str, tools):
    """记录请求中的工具名称列表"""
    if not config.log_tool_names_detail:
        return

    if not tools:
        logger.info(f"🔧 {path} 未携带工具")
        return

    tool_names = []
    for index, tool in enumerate(tools, start=1):
        if hasattr(tool, "name") and tool.name:
            tool_name = tool.name
        elif isinstance(tool, dict):
            tool_name = tool.get("name") or tool.get("function", {}).get("name")
        else:
            tool_name = None

        tool_names.append(tool_name or f"<unnamed_tool_{index}>")

    logger.info(f"🔧 {path} 工具列表 ({len(tool_names)} 个):")
    for index, tool_name in enumerate(tool_names, start=1):
        logger.info(f"   工具 {index}: {tool_name}")
