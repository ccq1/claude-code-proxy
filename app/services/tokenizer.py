"""
分词器服务
"""
import json
import logging
from typing import Optional
from app.config import config

logger = logging.getLogger(__name__)


class TokenizerService:
    """分词器服务"""
    
    def __init__(self):
        self.custom_tokenizer = None
        self._load_tokenizer()
    
    def _load_tokenizer(self):
        """加载自定义分词器"""
        try:
            from litellm import create_tokenizer
            
            tokenizer_file = config.tokenizer_file
            with open(tokenizer_file) as f:
                json_data = json.load(f)
            
            json_str = json.dumps(json_data)
            self.custom_tokenizer = create_tokenizer(json_str)
            logger.info(f"✅ Custom tokenizer loaded from {tokenizer_file}")
        except FileNotFoundError:
            logger.warning(f"⚠️ Tokenizer file not found: {config.tokenizer_file}, using default tokenizer")
            self.custom_tokenizer = None
        except Exception as e:
            logger.warning(f"⚠️ Failed to load custom tokenizer: {e}, using default tokenizer")
            self.custom_tokenizer = None
    
    def get_tokenizer(self) -> Optional[object]:
        """获取分词器实例"""
        return self.custom_tokenizer
    
    def is_custom(self) -> bool:
        """检查是否使用自定义分词器"""
        return self.custom_tokenizer is not None


# 创建全局分词器服务实例
tokenizer_service = TokenizerService()

