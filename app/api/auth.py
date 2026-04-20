"""
双层认证接口

1. 平台认证（主身份）：PandoraQ 读取本地平台 token 后向云端自举登录
2. 本地认证（次身份）：注册/登录，由本系统维护账户
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import auth_store

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: Optional[str] = Field(default=None, max_length=128)
    email: Optional[str] = Field(default=None, max_length=256)


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=256)


class PlatformBootstrapRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=128)
    email: Optional[str] = Field(default=None, max_length=256)


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, value = parts[0].lower(), parts[1].strip()
    if scheme != "bearer" or not value:
        return None
    return value


def _build_auth_view(local_token: Optional[str] = None) -> dict:
    """
    构建当前有效身份：
    - 若存在平台身份且启用优先级：返回 platform
    - 否则返回 local
    """
    local_session = auth_store.get_session(local_token) if local_token else None

    local_user_profile = (
        auth_store.get_user_profile(local_session.user_id)
        if local_session
        else None
    )

    if local_session and local_user_profile:
        return {
            "authenticated": True,
            "effective_source": "local",
            "user": local_user_profile,
            "local": {
                "has_local_session": True,
                "user": local_user_profile,
            },
        }

    return {
        "authenticated": False,
        "effective_source": None,
        "user": None,
        "local": {
            "has_local_session": local_session is not None,
            "user": local_user_profile,
        },
    }


@router.get("/me")
async def get_me(authorization: Optional[str] = Header(default=None)) -> dict:
    token = _extract_bearer_token(authorization)
    return _build_auth_view(token)


@router.post("/platform/bootstrap")
async def platform_bootstrap(
    payload: PlatformBootstrapRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="platform token is required")

    user_id = auth_store.ensure_platform_shadow_user_from_token(
        token=token,
        display_name=payload.display_name,
        email=payload.email,
    )
    profile = auth_store.get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=500, detail="failed to resolve platform account")

    return {
        "success": True,
        "auth_source": "platform",
        "account_id": profile.get("account_id"),
        "user": profile,
    }


@router.get("/account/{account_id}")
async def get_cloud_account(account_id: str) -> dict:
    profile = auth_store.get_user_profile_by_account_id(account_id)
    if not profile:
        raise HTTPException(status_code=404, detail="account not found")
    return {
        "success": True,
        "user": profile,
    }


@router.post("/register")
async def register(payload: RegisterRequest) -> dict:
    try:
        user_id = auth_store.register_local_user(
            username_or_email=payload.identifier,
            password=payload.password,
            display_name=payload.display_name,
            email=payload.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    session = auth_store.create_session(user_id=user_id, auth_source="local")
    return {
        "success": True,
        "session_token": session.token,
        "auth_source": "local",
        "expires_at": session.expires_at.isoformat(),
        "me": _build_auth_view(session.token),
    }


@router.post("/login")
async def login(payload: LoginRequest) -> dict:
    user_id = auth_store.verify_local_credentials(
        identifier=payload.identifier,
        password=payload.password,
    )
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid identifier or password")

    session = auth_store.create_session(user_id=user_id, auth_source="local")
    return {
        "success": True,
        "session_token": session.token,
        "auth_source": "local",
        "expires_at": session.expires_at.isoformat(),
        "me": _build_auth_view(session.token),
    }


@router.post("/logout")
async def logout(request: Request, authorization: Optional[str] = Header(default=None)) -> dict:
    token = _extract_bearer_token(authorization)
    if not token:
        body = await request.body()
        if body:
            try:
                # 兼容 body 传 token：{"session_token":"..."}
                import json

                parsed = json.loads(body.decode("utf-8"))
                token = (parsed.get("session_token") or "").strip() or None
            except Exception:
                token = None

    if token:
        auth_store.revoke_session(token)

    return {"success": True}
