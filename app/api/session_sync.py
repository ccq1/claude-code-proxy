"""
云端会话同步接口

说明：
- 仅用于 PandoraQ 会话的云端存储与回拉
- 不参与模型调用或插件下载的鉴权
- 当前按 account_id 识别账户
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import auth_store

router = APIRouter(prefix="/sync", tags=["session-sync"])


def _build_project_key(workspace_path: str) -> str:
    return re.sub(r"^-", "-", re.sub(r"-+", "-", re.sub(r"[^a-zA-Z0-9]+", "-", workspace_path)))


def _normalize_workspace_metadata(
    workspace_path: Optional[str],
    project_key: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    normalized_workspace_path = (workspace_path or "").strip() or None
    if normalized_workspace_path:
        normalized_project_key = _build_project_key(normalized_workspace_path)
        return normalized_workspace_path, normalized_project_key
    normalized_project_key = (project_key or "").strip() or None
    return None, normalized_project_key


def _extract_workspace_metadata(payload_json: str) -> dict:
    if not payload_json:
        return {}
    try:
        payload = json.loads(payload_json)
    except Exception:
        return {}

    workspace_path, project_key = _normalize_workspace_metadata(
        payload.get("workspace_path"),
        payload.get("project_key"),
    )

    return {
        "workspace_path": workspace_path,
        "project_key": project_key,
    }


def _build_day_range(days: int) -> tuple[str, str]:
    normalized_days = max(1, min(int(days or 365), 1095))
    end_day = date.today()
    start_day = end_day - timedelta(days=normalized_days - 1)
    return start_day.isoformat(), end_day.isoformat()


class SessionSyncPayload(BaseModel):
    account_id: str = Field(..., min_length=8, max_length=128)
    title: str = Field(default="", max_length=512)
    date_created: Optional[str] = None
    last_modified: Optional[str] = None
    last_user_message_at: Optional[str] = None
    file_size: int = Field(default=0, ge=0)
    workspace_path: Optional[str] = Field(default=None, max_length=4096)
    project_key: Optional[str] = Field(default=None, max_length=512)
    messages: List[Any] = Field(default_factory=list)


@router.get("/sessions")
async def list_cloud_sessions(account_id: str = Query(..., min_length=8, max_length=128)) -> dict:
    profile = auth_store.get_user_profile_by_account_id(account_id)
    if not profile:
        raise HTTPException(status_code=404, detail="account not found")

    sessions = auth_store.list_cloud_sessions(account_id)
    return {
        "success": True,
        "account_id": account_id,
        "sessions": [
            {
                **{
                    "session_id": item.session_id,
                    "title": item.title,
                    "date_created": item.date_created,
                    "last_modified": item.last_modified,
                    "last_user_message_at": item.last_user_message_at,
                    "file_size": item.file_size,
                    "message_count": item.message_count,
                    "updated_at": item.updated_at,
                },
                **_extract_workspace_metadata(item.payload_json),
            }
            for item in sessions
        ],
    }


@router.get("/deletions")
async def list_cloud_session_deletions(
    account_id: str = Query(..., min_length=8, max_length=128),
) -> dict:
    profile = auth_store.get_user_profile_by_account_id(account_id)
    if not profile:
        raise HTTPException(status_code=404, detail="account not found")

    deletions = auth_store.list_cloud_session_deletions(account_id)
    return {
        "success": True,
        "account_id": account_id,
        "deletions": [
            {
                "session_id": item.session_id,
                "deleted_at": item.deleted_at,
            }
            for item in deletions
        ],
    }


@router.get("/stats/daily")
async def get_cloud_daily_stats(
    account_id: str = Query(..., min_length=8, max_length=128),
    days: int = Query(default=365, ge=1, le=1095),
) -> dict:
    profile = auth_store.get_user_profile_by_account_id(account_id)
    if not profile:
        raise HTTPException(status_code=404, detail="account not found")

    start_day, end_day = _build_day_range(days)
    rows = auth_store.get_cloud_daily_productivity_stats(account_id, start_day, end_day)
    by_day = {
        row.day: {
            "editLines": row.edit_lines,
            "inputTokens": row.input_tokens,
        }
        for row in rows
    }

    cursor = date.fromisoformat(start_day)
    end_date = date.fromisoformat(end_day)
    day_items = []
    total_edit_lines = 0
    total_input_tokens = 0
    while cursor <= end_date:
        day_key = cursor.isoformat()
        current = by_day.get(day_key, {"editLines": 0, "inputTokens": 0})
        total_edit_lines += int(current["editLines"])
        total_input_tokens += int(current["inputTokens"])
        day_items.append(
            {
                "day": day_key,
                "editLines": int(current["editLines"]),
                "inputTokens": int(current["inputTokens"]),
            }
        )
        cursor += timedelta(days=1)

    return {
        "success": True,
        "account_id": account_id,
        "stats": {
            "days": day_items,
            "startDay": start_day,
            "endDay": end_day,
            "totalEditLines": total_edit_lines,
            "totalInputTokens": total_input_tokens,
        },
    }


@router.get("/sessions/{session_id}")
async def get_cloud_session(
    session_id: str,
    account_id: str = Query(..., min_length=8, max_length=128),
) -> dict:
    record = auth_store.get_cloud_session(account_id, session_id)
    if not record:
        raise HTTPException(status_code=404, detail="cloud session not found")

    payload = json.loads(record.payload_json)
    return {
        "success": True,
        "account_id": account_id,
        "session": payload,
        "updated_at": record.updated_at,
    }


@router.put("/sessions/{session_id}")
async def put_cloud_session(session_id: str, payload: SessionSyncPayload) -> dict:
    if payload.account_id.strip() == "":
        raise HTTPException(status_code=400, detail="account_id is required")

    normalized_title = (payload.title or "").strip() or session_id
    normalized_workspace_path, normalized_project_key = _normalize_workspace_metadata(
        payload.workspace_path,
        payload.project_key,
    )
    serialized_payload = json.dumps(
        {
            "session_id": session_id,
            "title": normalized_title,
            "date_created": payload.date_created,
            "last_modified": payload.last_modified,
            "last_user_message_at": payload.last_user_message_at,
            "file_size": payload.file_size,
            "workspace_path": normalized_workspace_path,
            "project_key": normalized_project_key,
            "messages": payload.messages,
        },
        ensure_ascii=False,
    )
    record = auth_store.upsert_cloud_session(
        account_id=payload.account_id,
        session_id=session_id,
        title=normalized_title,
        date_created=payload.date_created,
        last_modified=payload.last_modified,
        last_user_message_at=payload.last_user_message_at,
        file_size=payload.file_size,
        message_count=len(payload.messages),
        payload_json=serialized_payload,
    )
    return {
        "success": True,
        "account_id": payload.account_id,
        "session_id": record.session_id,
        "updated_at": record.updated_at,
        "message_count": record.message_count,
    }


@router.delete("/sessions/{session_id}")
async def delete_cloud_session(
    session_id: str,
    account_id: str = Query(..., min_length=8, max_length=128),
) -> dict:
    profile = auth_store.get_user_profile_by_account_id(account_id)
    if not profile:
        raise HTTPException(status_code=404, detail="account not found")

    deleted = auth_store.delete_cloud_session(account_id, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="cloud session not found")
    return {
        "success": True,
        "account_id": account_id,
        "session_id": session_id,
    }
