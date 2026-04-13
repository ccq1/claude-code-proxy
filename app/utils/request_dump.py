"""
模型请求上下文落盘工具
"""
import copy
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from app.config import config

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {"api_key", "authorization", "auth_token"}


def _sanitize_payload(value: Any) -> Any:
    """递归脱敏请求体中的敏感字段。"""
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS:
                sanitized[key] = "***"
            else:
                sanitized[key] = _sanitize_payload(item)
        return sanitized

    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]

    return value


def dump_model_request_context(
    request_id: str,
    original_model: str,
    routed_model: str,
    base_url: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    """
    把最终发送给模型的请求上下文写入独立目录。
    返回落盘文件路径，失败返回 None。
    """
    try:
        os.makedirs(config.model_request_dump_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_name = f"{timestamp}_{request_id}.json"
        output_path = os.path.join(config.model_request_dump_dir, file_name)

        snapshot = {
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
            "original_model": original_model,
            "routed_model": routed_model,
            "base_url": base_url,
            "payload": _sanitize_payload(copy.deepcopy(payload)),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)

        return output_path
    except Exception as e:
        logger.warning(f"Failed to dump model request context: {e}")
        return None


def record_model_request_context_for_debug(
    request_id: str,
    original_model: str,
    routed_model: str,
    base_url: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    """调试模式下记录最终模型请求上下文。"""
    if not config.debug_mode:
        return None

    return dump_model_request_context(
        request_id=request_id,
        original_model=original_model,
        routed_model=routed_model,
        base_url=base_url,
        payload=payload,
    )
