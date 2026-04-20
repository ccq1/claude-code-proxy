"""
认证模块导出
"""

from .auth_store import auth_store, AuthSession
from .platform_identity import PlatformIdentity, resolve_platform_identity

__all__ = [
    "auth_store",
    "AuthSession",
    "PlatformIdentity",
    "resolve_platform_identity",
]

