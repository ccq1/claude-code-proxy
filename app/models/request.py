"""
请求数据模型
"""
import logging
from pydantic import BaseModel, field_validator, model_validator
from typing import List, Dict, Any, Optional, Union, Literal

logger = logging.getLogger(__name__)


class ContentBlockText(BaseModel):
    type: Literal["text"]
    text: str


class ContentBlockThinking(BaseModel):
    type: Literal["thinking"]
    thinking: str


class ContentBlockImage(BaseModel):
    type: Literal["image"]
    source: Dict[str, Any]


class ContentBlockToolUse(BaseModel):
    type: Literal["tool_use"]
    id: str
    name: str
    input: Dict[str, Any]


class ContentBlockToolResult(BaseModel):
    type: Literal["tool_result"]
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]], Dict[str, Any]]


class SystemContent(BaseModel):
    type: Literal["text"]
    text: str


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[Union[ContentBlockThinking, ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult]]]


class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any]


class ThinkingConfig(BaseModel):
    enabled: bool = True


class MessagesRequest(BaseModel):
    model: str
    max_tokens: int
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Dict[str, Any]] = None
    thinking: Optional[ThinkingConfig] = None
    original_model: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def set_original_model(cls, data):
        """在模型验证前设置原始模型名称"""
        if isinstance(data, dict) and 'model' in data:
            # 如果没有设置 original_model，则用 model 字段的值
            if not data.get('original_model'):
                data['original_model'] = data['model']
        return data

    @field_validator('model')
    @classmethod
    def validate_model_field(cls, v):
        # 延迟导入避免循环依赖
        from app.services.model_manager import model_manager

        original_model = v
        mapped_model, was_mapped = model_manager.validate_and_map_model(v)

        if was_mapped:
            logger.info(f"📌 MODEL MAPPING: '{original_model}' ➡️  '{mapped_model}'")

        return mapped_model


class TokenCountRequest(BaseModel):
    model: str
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    tools: Optional[List[Tool]] = None
    thinking: Optional[ThinkingConfig] = None
    tool_choice: Optional[Dict[str, Any]] = None
    original_model: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def set_original_model_token_count(cls, data):
        """在模型验证前设置原始模型名称"""
        if isinstance(data, dict) and 'model' in data:
            # 如果没有设置 original_model，则用 model 字段的值
            if not data.get('original_model'):
                data['original_model'] = data['model']
        return data

    @field_validator('model')
    @classmethod
    def validate_model_token_count(cls, v):
        from app.services.model_manager import model_manager

        mapped_model, _ = model_manager.validate_and_map_model(v)
        return mapped_model

