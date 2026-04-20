"""
平台身份解析模块

从 code-server 进程环境变量读取平台注入信息，作为主身份源。
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional

from app.config import config


@dataclass(frozen=True)
class PlatformIdentity:
    provider: str
    provider_user_id: str
    token_fingerprint: str
    display_name: Optional[str]
    email: Optional[str]


def _stable_user_id_from_token(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"platform-{digest[:24]}"


def resolve_platform_identity() -> Optional[PlatformIdentity]:
    """
    解析平台身份。

    返回 None 表示当前实例没有可用的平台身份。
    """
    if not config.platform_auth_enabled:
        return None

    token_env_name = config.platform_identity_token_env
    raw_token = (os.environ.get(token_env_name, "") or "").strip()
    if not raw_token:
        return None

    user_id_env_name = config.platform_identity_user_id_env
    display_name_env_name = config.platform_identity_name_env
    email_env_name = config.platform_identity_email_env

    provider_user_id = (os.environ.get(user_id_env_name, "") or "").strip()
    if not provider_user_id:
        provider_user_id = _stable_user_id_from_token(raw_token)

    display_name = (os.environ.get(display_name_env_name, "") or "").strip() or None
    email = (os.environ.get(email_env_name, "") or "").strip() or None
    token_fingerprint = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()[:12]

    return PlatformIdentity(
        provider="platform",
        provider_user_id=provider_user_id,
        token_fingerprint=token_fingerprint,
        display_name=display_name,
        email=email,
    )

