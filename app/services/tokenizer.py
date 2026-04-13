"""
分词器服务
"""
import json
import logging
from typing import Any, Dict, Optional

import litellm
from tokenizers import Tokenizer

from app.config import config

logger = logging.getLogger(__name__)


class TokenizerService:
    """按模型管理分词器单例"""

    def __init__(self):
        self.tokenizers: Dict[str, Optional[Tokenizer]] = {}
        self._load_tokenizers()

    def _load_tokenizers(self):
        """启动时加载所有模型的分词器单例"""
        loaded_files = {}

        for route in config.model_route_list:
            tokenizer_file = route.tokenizer_file

            if tokenizer_file in loaded_files:
                self.tokenizers[route.model_name] = loaded_files[tokenizer_file]
                logger.info(
                    f"♻️ Reusing tokenizer singleton for {route.model_name} from {tokenizer_file}"
                )
                continue

            try:
                tokenizer = Tokenizer.from_file(tokenizer_file)
                loaded_files[tokenizer_file] = tokenizer
                self.tokenizers[route.model_name] = tokenizer
                logger.info(
                    f"✅ Tokenizer singleton loaded for {route.model_name} from {tokenizer_file}"
                )
            except FileNotFoundError:
                logger.warning(
                    f"⚠️ Tokenizer file not found for {route.model_name}: {tokenizer_file}, using default tokenizer"
                )
                loaded_files[tokenizer_file] = None
                self.tokenizers[route.model_name] = None
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to load tokenizer for {route.model_name} from {tokenizer_file}: {e}, using default tokenizer"
                )
                loaded_files[tokenizer_file] = None
                self.tokenizers[route.model_name] = None

    def get_tokenizer(self, model_name: str) -> Optional[Tokenizer]:
        """获取指定模型的分词器实例"""
        clean_model = self._clean_model_name(model_name)
        if clean_model in self.tokenizers:
            return self.tokenizers[clean_model]
        raise KeyError(f"Tokenizer singleton not found for model '{clean_model}'")

    def is_custom(self, model_name: str) -> bool:
        """检查指定模型是否使用自定义分词器"""
        return self.get_tokenizer(model_name) is not None

    def count_litellm_request_tokens(self, litellm_request: dict) -> int:
        """按模型计算 LiteLLM 请求的输入 token 数"""
        model_name = litellm_request["model"]
        tokenizer = self.get_tokenizer(model_name)

        if tokenizer is None:
            return litellm.token_counter(
                model=litellm_request["model"],
                messages=litellm_request["messages"],
                tools=litellm_request.get("tools"),
                tool_choice=litellm_request.get("tool_choice"),
            )

        total_tokens = 0

        for message in litellm_request.get("messages", []) or []:
            total_tokens += self._count_message_tokens(message, tokenizer)

        tools = litellm_request.get("tools")
        if tools:
            total_tokens += self._count_json_tokens(tools, tokenizer)

        tool_choice = litellm_request.get("tool_choice")
        if tool_choice:
            total_tokens += self._count_json_tokens(tool_choice, tokenizer)

        return total_tokens

    def _count_message_tokens(self, message: dict[str, Any], tokenizer: Tokenizer) -> int:
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

        return self._count_text_tokens("\n".join(parts), tokenizer)

    def _count_json_tokens(self, value: Any, tokenizer: Tokenizer) -> int:
        """计算 JSON 值的 token 数"""
        return self._count_text_tokens(
            json.dumps(value, ensure_ascii=False, sort_keys=True),
            tokenizer,
        )

    def _count_text_tokens(self, text: str, tokenizer: Tokenizer) -> int:
        """计算纯文本 token 数"""
        if not text:
            return 0
        return len(tokenizer.encode(text).ids)

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

    def _clean_model_name(self, model_name: str) -> str:
        """清理模型名前缀"""
        if model_name.startswith("openai/"):
            return model_name[7:]
        if model_name.startswith("anthropic/"):
            return model_name[10:]
        if model_name.startswith("gemini/"):
            return model_name[7:]
        return model_name


# 创建全局分词器服务实例
tokenizer_service = TokenizerService()
