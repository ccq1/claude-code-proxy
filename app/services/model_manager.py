"""
模型管理服务
"""
from typing import List, Tuple
from app.config import ModelRoute, config


class ModelManager:
    """模型管理器"""
    
    def __init__(self, cfg):
        self.config = cfg
        self.base_local_models = [route.model_name for route in cfg.model_route_list]
        self._local_models = set(self.base_local_models)
    
    
    @property
    def local_models(self) -> List[str]:
        """获取所有本地模型列表"""
        return sorted(list(self._local_models))

    def is_configured_model(self, model_name: str) -> bool:
        """判断模型是否已配置"""
        clean_model = self._clean_model_name(model_name)
        return clean_model in self._local_models
    
    def validate_and_map_model(self, original_model: str) -> Tuple[str, bool]:
        """验证并映射模型名称"""
        clean_model = self._clean_model_name(original_model)
        if clean_model in self._local_models:
            return f"openai/{clean_model}", clean_model != original_model

        default_model = self.config.default_model_route.model_name
        return f"openai/{default_model}", True

    def get_model_route(self, model_name: str) -> ModelRoute:
        """获取指定模型的路由配置，未命中时回退到默认模型"""
        clean_model = self._clean_model_name(model_name)
        if clean_model in self._local_models:
            return self.config.get_model_route(clean_model)
        return self.config.default_model_route

    def _clean_model_name(self, model: str) -> str:
        """清理模型名称前缀"""
        if model.startswith('openai/'):
            return model[7:]
        elif model.startswith('anthropic/'):
            return model[10:]
        elif model.startswith('gemini/'):
            return model[7:]
        return model
    
# 创建全局模型管理器实例
model_manager = ModelManager(config)
