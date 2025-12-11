"""
配置管理模块
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables early
load_dotenv()


class Config:
    """应用配置类"""
    
    def __init__(self):
        # 本地模型配置
        self.base_url = os.environ.get("BASE_URL", "http://10.1.1.125:29000/v1")
        self.api_key = os.environ.get("API_KEY", "sk-faker")
        
        # 模型配置
        self.big_model = os.environ.get("BIG_MODEL", "qwen3-coder")
        self.small_model = os.environ.get("SMALL_MODEL", "qwen3-coder")
        
        # 服务器配置
        self.host = os.environ.get("HOST", "0.0.0.0")
        self.port = int(os.environ.get("PORT", "4000"))
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.max_tokens_limit = int(os.environ.get("MAX_TOKENS_LIMIT", "16384"))
        
        # 连接配置
        self.request_timeout = int(os.environ.get("REQUEST_TIMEOUT", "90"))
        self.max_retries = int(os.environ.get("MAX_RETRIES", "1"))
        
        # 流式配置
        self.max_streaming_retries = int(os.environ.get("MAX_STREAMING_RETRIES", "12"))
        self.force_disable_streaming = os.environ.get("FORCE_DISABLE_STREAMING", "true").lower() == "true"
        self.emergency_disable_streaming = os.environ.get("EMERGENCY_DISABLE_STREAMING", "false").lower() == "true"
        
        # Tokenizer 配置
        self.tokenizer_file = os.environ.get("TOKENIZER_FILE", "tokenizers/qwen3coder30b_tokenizer.json")
        
        # Worker 配置
        self.workers = int(os.environ.get("WORKERS", "1"))
        
    def validate_api_key(self) -> bool:
        """验证 API key"""
        if not self.api_key:
            return False
        return len(self.api_key) > 0
    
    def print_config(self):
        """打印配置摘要"""
        print(f"✅ Configuration loaded: API_KEY={'*' * min(10, len(self.api_key))}...")
        print(f"   BASE_URL='{self.base_url}'")
        print(f"   BIG_MODEL='{self.big_model}'")
        print(f"   SMALL_MODEL='{self.small_model}'")


# 创建全局配置实例
try:
    config = Config()
    config.print_config()
except Exception as e:
    print(f"🔴 Configuration Error: {e}")
    sys.exit(1)

