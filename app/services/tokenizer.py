"""
分词器服务
"""
import json
import logging
from typing import Any, Optional

import litellm
from tokenizers import Tokenizer

from app.config import config

logger = logging.getLogger(__name__)


class TokenizerService:
    """分词器服务"""
    
    def __init__(self):
        self.tokenizer: Optional[Tokenizer] = None
        self._load_tokenizer()
    
    def _load_tokenizer(self):
        """加载自定义分词器"""
        try:
            tokenizer_file = config.tokenizer_file
            self.tokenizer = Tokenizer.from_file(tokenizer_file)
            logger.info(f"✅ Singleton tokenizer loaded from {tokenizer_file}")
        except FileNotFoundError:
            logger.warning(f"⚠️ Tokenizer file not found: {config.tokenizer_file}, using default tokenizer")
            self.tokenizer = None
        except Exception as e:
            logger.warning(f"⚠️ Failed to load custom tokenizer: {e}, using default tokenizer")
            self.tokenizer = None
    
    def get_tokenizer(self) -> Optional[object]:
        """获取分词器实例"""
        return self.tokenizer
    
    def is_custom(self) -> bool:
        """检查是否使用自定义分词器"""
        return self.tokenizer is not None

    def count_litellm_request_tokens(self, litellm_request: dict) -> int:
        """计算 LiteLLM 请求的输入 token 数"""
        if self.tokenizer is None:
            return litellm.token_counter(
                model=litellm_request["model"],
                messages=litellm_request["messages"],
                tools=litellm_request.get("tools"),
                tool_choice=litellm_request.get("tool_choice"),
            )

        total_tokens = 0

        for message in litellm_request.get("messages", []) or []:
            total_tokens += self._count_message_tokens(message)

        tools = litellm_request.get("tools")
        if tools:
            total_tokens += self._count_json_tokens(tools)

        tool_choice = litellm_request.get("tool_choice")
        if tool_choice:
            total_tokens += self._count_json_tokens(tool_choice)

        return total_tokens

    def _count_message_tokens(self, message: dict[str, Any]) -> int:
        """计算单条消息的 token 数"""
        parts = []

        role = message.get("role")
        if role:
            parts.append(str(role))

        content = self._stringify_content(message.get("content"))
        if content:
            parts.append(content)

        for key in sorted(message.keys()):
            if key in {"role", "content"}:
                continue
            value = message.get(key)
            if value is None:
                continue
            parts.append(json.dumps({key: value}, ensure_ascii=False, sort_keys=True))

        if not parts:
            return 0

        return self._count_text_tokens("\n".join(parts))

    def _count_json_tokens(self, value: Any) -> int:
        """计算 JSON 值的 token 数"""
        return self._count_text_tokens(json.dumps(value, ensure_ascii=False, sort_keys=True))

    def _count_text_tokens(self, text: str) -> int:
        """计算纯文本 token 数"""
        if not text or self.tokenizer is None:
            return 0
        return len(self.tokenizer.encode(text).ids)

    def _stringify_content(self, content: Any) -> str:
        """将消息内容序列化为文本"""
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif item.get("type") == "thinking":
                        parts.append(item.get("thinking", ""))
                    else:
                        parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
                else:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part)

        if isinstance(content, dict):
            return json.dumps(content, ensure_ascii=False, sort_keys=True)

        return str(content)

# 创建全局分词器服务实例
tokenizer_service = TokenizerService()
