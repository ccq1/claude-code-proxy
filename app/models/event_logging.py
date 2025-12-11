"""
事件日志数据模型
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class EventLogItem(BaseModel):
    event_type: Optional[str] = None
    timestamp: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class EventLoggingBatchRequest(BaseModel):
    events: Optional[List[EventLogItem]] = None
    batch_id: Optional[str] = None
    source: Optional[str] = None
    
    class Config:
        extra = "allow"  # 允许额外字段


class EventLoggingBatchResponse(BaseModel):
    success: bool = True
    batch_id: Optional[str] = None
    processed_count: int = 0
    message: Optional[str] = None

