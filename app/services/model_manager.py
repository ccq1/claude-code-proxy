"""
模型管理服务
"""
from typing import List, Tuple
from app.config import config


class ModelManager:
    """模型管理器"""
    
    def __init__(self, cfg):
        self.config = cfg
        # 本地模型列表
        self.base_local_models = [
            cfg.big_model,
            cfg.small_model
        ]
        self._local_models = set(self.base_local_models)
    
    
    @property
    def local_models(self) -> List[str]:
        """获取所有本地模型列表"""
        return sorted(list(self._local_models))
    
    def validate_and_map_model(self, original_model: str) -> Tuple[str, bool]:
        """验证并映射模型名称"""
        clean_model = self._clean_model_name(original_model)
        mapped_model = self._map_model_alias(clean_model)
        
        if mapped_model != clean_model:
            return f"openai/{mapped_model}", True
        elif clean_model in self._local_models:
            return f"openai/{clean_model}", True
        elif not original_model.startswith('openai/'):
            return f"openai/{original_model}", False
        else:
            return original_model, False
    
    def _clean_model_name(self, model: str) -> str:
        """清理模型名称前缀"""
        if model.startswith('openai/'):
            return model[7:]
        elif model.startswith('anthropic/'):
            return model[10:]
        elif model.startswith('gemini/'):
            return model[7:]
        return model
    
    def _map_model_alias(self, clean_model: str) -> str:
        """映射模型别名到本地模型"""
        model_lower = clean_model.lower()
        
        # 映射 Claude 模型别名到本地模型
        if 'haiku' in model_lower or 'fast' in model_lower:
            return self.config.small_model
        elif 'sonnet' in model_lower or 'opus' in model_lower or 'large' in model_lower:
            return self.config.big_model
        
        return clean_model


# 创建全局模型管理器实例
model_manager = ModelManager(config)

