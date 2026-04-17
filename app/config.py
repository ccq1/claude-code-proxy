"""
配置管理模块
"""
import os
import sys
from dataclasses import dataclass
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables early
load_dotenv()


@dataclass(frozen=True)
class ModelRoute:
    """单个模型的路由配置"""

    model_name: str
    base_url: str
    auth_token: str
    context_length: int
    description: str
    supports_image_analysis: bool
    tokenizer_file: str


class Config:
    """应用配置类"""
    
    def __init__(self):
        self.default_tokenizer_file = os.environ.get(
            "DEFAULT_TOKENIZER_FILE",
            "tokenizers/qwen3_5_30b_a3b_tokenizer.json",
        ).strip()
        self.model_count = int(os.environ.get("MODEL_COUNT", "0"))
        self.model_routes = self._load_model_routes()
        
        # 服务器配置
        self.host = os.environ.get("HOST", "0.0.0.0")
        self.port = int(os.environ.get("PORT", "4000"))
        raw_log_level = (os.environ.get("LOG_LEVEL", "INFO") or "").strip()
        normalized_log_level = raw_log_level.upper()
        if normalized_log_level in {"1", "TRUE", "YES", "ON"}:
            normalized_log_level = "DEBUG"
        elif normalized_log_level in {"0", "FALSE", "NO", "OFF", ""}:
            normalized_log_level = "INFO"
        elif normalized_log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
            print(
                f"🟠 Invalid LOG_LEVEL={raw_log_level!r}; falling back to 'INFO'. "
                "Use one of: CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET."
            )
            normalized_log_level = "INFO"
        self.log_level = normalized_log_level
        debug_env = (
            os.environ.get("DEBUG_MODE")
            or os.environ.get("DEBUG")
            or ""
        ).strip().lower()
        self.debug_mode = debug_env in {"1", "true", "yes", "on"} or self.log_level.upper() == "DEBUG"
        self.max_tokens_limit = int(os.environ.get("MAX_TOKENS_LIMIT", "16384"))

        # 非标准 OpenAI 字段注入（仅限自建/兼容后端开启）
        self.inject_thinking_config = os.environ.get("INJECT_THINKING_CONFIG", "false").lower() == "true"
        self.inject_chat_template_kwargs = os.environ.get("INJECT_CHAT_TEMPLATE_KWARGS", "false").lower() == "true"
        self.allow_non_openai_sampling_params = os.environ.get("ALLOW_NON_OPENAI_SAMPLING_PARAMS", "false").lower() == "true"
        
        # 连接配置
        self.request_timeout = int(os.environ.get("REQUEST_TIMEOUT", "90"))
        self.max_retries = int(os.environ.get("MAX_RETRIES", "1"))
        
        # 流式配置
        self.max_streaming_retries = int(os.environ.get("MAX_STREAMING_RETRIES", "12"))
        self.force_disable_streaming = os.environ.get("FORCE_DISABLE_STREAMING", "false").lower() == "true"
        self.emergency_disable_streaming = os.environ.get("EMERGENCY_DISABLE_STREAMING", "false").lower() == "true"
        self.force_disable_streaming_models = [
            item.strip()
            for item in os.environ.get("FORCE_DISABLE_STREAMING_MODELS", "").split(",")
            if item.strip()
        ]
        
        # 日志细节开关
        self.log_tool_names_detail = os.environ.get("LOG_TOOL_NAMES_DETAIL", "false").lower() == "true"
        self.log_response_details = os.environ.get("LOG_RESPONSE_DETAILS", "false").lower() == "true"
        self.model_request_dump_dir = os.environ.get("MODEL_REQUEST_DUMP_DIR", "logs/model_request_contexts").strip()
        self.sanitize_brand_terms = os.environ.get("SANITIZE_BRAND_TERMS", "true").lower() == "true"

        # 插件配置
        self.redteam_kb_base_url = os.environ.get("REDTEAM_KB_BASE_URL", "").strip()
        self.redteam_kb_api_key = os.environ.get("REDTEAM_KB_API_KEY", "").strip()
        
        # Worker 配置
        self.workers = int(os.environ.get("WORKERS", "1"))

    def _load_model_routes(self) -> Dict[str, ModelRoute]:
        """加载多模型路由配置"""
        if self.model_count <= 0:
            raise ValueError("MODEL_COUNT must be greater than 0")

        routes: Dict[str, ModelRoute] = {}
        for index in range(1, self.model_count + 1):
            model_name = os.environ.get(f"MODEL_NAME_{index}", "").strip()
            base_url = os.environ.get(f"MODEL_BASE_URL_{index}", "").strip()
            auth_token = os.environ.get(f"MODEL_AUTH_TOKEN_{index}", "").strip()
            raw_context_length = os.environ.get(f"MODEL_CONTEXT_LENGTH_{index}", "").strip()
            description = os.environ.get(f"MODEL_DESCRIPTION_{index}", "").strip()
            raw_supports_image_analysis = os.environ.get(
                f"MODEL_SUPPORTS_IMAGE_ANALYSIS_{index}",
                "false",
            ).strip().lower()
            tokenizer_file = (
                os.environ.get(f"MODEL_TOKENIZER_FILE_{index}", "").strip()
                or self.default_tokenizer_file
            )

            if (
                not model_name
                or not base_url
                or not auth_token
                or not raw_context_length
                or not description
            ):
                raise ValueError(
                    f"Model #{index} must include MODEL_NAME_{index}, MODEL_BASE_URL_{index}, "
                    f"MODEL_AUTH_TOKEN_{index}, MODEL_CONTEXT_LENGTH_{index}, MODEL_DESCRIPTION_{index}"
                )
            try:
                context_length = int(raw_context_length)
                if context_length <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(
                    f"MODEL_CONTEXT_LENGTH_{index} must be a positive integer, got '{raw_context_length}'"
                )
            if raw_supports_image_analysis not in {"true", "false"}:
                raise ValueError(
                    f"MODEL_SUPPORTS_IMAGE_ANALYSIS_{index} must be 'true' or 'false', "
                    f"got '{raw_supports_image_analysis}'"
                )
            supports_image_analysis = raw_supports_image_analysis == "true"

            if model_name in routes:
                raise ValueError(f"Duplicate model_name in routes: '{model_name}'")

            routes[model_name] = ModelRoute(
                model_name=model_name,
                base_url=base_url,
                auth_token=auth_token,
                context_length=context_length,
                description=description,
                supports_image_analysis=supports_image_analysis,
                tokenizer_file=tokenizer_file,
            )

        return routes

    def get_model_route(self, model_name: str) -> ModelRoute:
        """按模型名获取路由，未命中时报错"""
        clean_model_name = model_name.strip()
        if clean_model_name in self.model_routes:
            return self.model_routes[clean_model_name]
        raise KeyError(f"Model route not found for '{clean_model_name}'")
    
    def validate_api_key(self) -> bool:
        """验证所有模型路由都有鉴权配置"""
        return all(route.auth_token for route in self.model_routes.values())

    @property
    def model_route_list(self) -> List[ModelRoute]:
        """返回所有模型路由列表"""
        return list(self.model_routes.values())

    @property
    def default_model_route(self) -> ModelRoute:
        """返回默认模型路由（第一个模型）"""
        return self.model_route_list[0]
    
    def print_config(self):
        """打印配置摘要"""
        print("✅ Configuration loaded from indexed model routes")
        print(f"   MODEL_COUNT={len(self.model_routes)} configured")
        print(f"   DEFAULT_TOKENIZER_FILE='{self.default_tokenizer_file}'")
        for route in self.model_route_list[:10]:
            masked_token = "*" * min(10, len(route.auth_token)) if route.auth_token else "(empty)"
            print(
                f"      - model='{route.model_name}', base_url='{route.base_url}', auth_token={masked_token}, "
                f"context_length={route.context_length}, description='{route.description}', "
                f"supports_image_analysis={route.supports_image_analysis}, tokenizer_file='{route.tokenizer_file}'"
            )
        print(f"   MAX_TOKENS_LIMIT={self.max_tokens_limit}")
        print(f"   MAX_STREAMING_RETRIES={self.max_streaming_retries}")
        print(f"   FORCE_DISABLE_STREAMING={self.force_disable_streaming}")
        print(f"   EMERGENCY_DISABLE_STREAMING={self.emergency_disable_streaming}")
        print(f"   FORCE_DISABLE_STREAMING_MODELS={self.force_disable_streaming_models}")
        print(f"   LOG_TOOL_NAMES_DETAIL={self.log_tool_names_detail}")
        print(f"   LOG_RESPONSE_DETAILS={self.log_response_details}")
        print(f"   DEBUG_MODE={self.debug_mode}")
        print(f"   SANITIZE_BRAND_TERMS={self.sanitize_brand_terms}")
        print(f"   MODEL_REQUEST_DUMP_DIR='{self.model_request_dump_dir}'")
        print(f"   REDTEAM_KB_BASE_URL={'(set)' if self.redteam_kb_base_url else '(empty)'}")
        print(f"   WORKERS={self.workers}")


# 创建全局配置实例
try:
    config = Config()
    config.print_config()
except Exception as e:
    print(f"🔴 Configuration Error: {e}")
    sys.exit(1)
