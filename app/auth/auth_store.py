"""
认证与云端会话同步存储层（SQLite）

支持：
1. 平台影子账户（provider=platform）
2. 本地账户注册/登录（provider=local）
3. 会话 token 管理
4. 基于 account_id 的云端会话同步
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.auth.platform_identity import PlatformIdentity
from app.config import config


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _pbkdf2_hash_password(password: str, salt: bytes) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return base64.b64encode(derived).decode("ascii")


def _normalize_local_identifier(identifier: str) -> str:
    return (identifier or "").strip().lower()


@dataclass
class AuthSession:
    token: str
    user_id: int
    auth_source: str
    expires_at: datetime


@dataclass
class CloudSessionRecord:
    session_id: str
    title: str
    date_created: Optional[str]
    last_modified: Optional[str]
    last_user_message_at: Optional[str]
    file_size: int
    message_count: int
    updated_at: str
    payload_json: str


@dataclass
class CloudSessionDeletionRecord:
    session_id: str
    deleted_at: str


@dataclass
class DailyProductivityStatRecord:
    day: str
    edit_lines: int
    input_tokens: int


class AuthStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.RLock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _generate_account_id(self) -> str:
        return f"acct_{secrets.token_urlsafe(18)}"

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_sql: str,
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def _backfill_missing_account_ids(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT id
            FROM users
            WHERE account_id IS NULL OR TRIM(account_id) = ''
            """
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE users SET account_id=?, updated_at=? WHERE id=?",
                (self._generate_account_id(), _iso(_utcnow()), int(row["id"])),
            )

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA foreign_keys=ON;")
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id TEXT UNIQUE,
                        display_name TEXT,
                        email TEXT,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS identity_accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        provider TEXT NOT NULL,
                        provider_user_id TEXT NOT NULL,
                        email TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(provider, provider_user_id)
                    );

                    CREATE TABLE IF NOT EXISTS local_credentials (
                        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                        password_hash TEXT NOT NULL,
                        password_salt TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS auth_sessions (
                        token TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        auth_source TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS cloud_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT NOT NULL,
                        title TEXT,
                        date_created TEXT,
                        last_modified TEXT,
                        last_user_message_at TEXT,
                        file_size INTEGER NOT NULL DEFAULT 0,
                        message_count INTEGER NOT NULL DEFAULT 0,
                        payload_json TEXT NOT NULL,
                        deleted_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(user_id, session_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_cloud_sessions_user_updated
                    ON cloud_sessions(user_id, updated_at DESC);

                    CREATE TABLE IF NOT EXISTS cloud_session_tombstones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT NOT NULL,
                        deleted_at TEXT NOT NULL,
                        UNIQUE(user_id, session_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_cloud_session_tombstones_user_deleted
                    ON cloud_session_tombstones(user_id, deleted_at DESC);

                    CREATE TABLE IF NOT EXISTS cloud_session_day_stats (
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT NOT NULL,
                        day TEXT NOT NULL,
                        edit_lines INTEGER NOT NULL DEFAULT 0,
                        input_tokens INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, session_id, day)
                    );

                    CREATE INDEX IF NOT EXISTS idx_cloud_session_day_stats_user_day
                    ON cloud_session_day_stats(user_id, day DESC);

                    CREATE TABLE IF NOT EXISTS cloud_session_stats_cache (
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        synced_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, session_id)
                    );
                    """
                )
                self._ensure_column(conn, "users", "account_id", "TEXT")
                self._ensure_column(conn, "cloud_sessions", "deleted_at", "TEXT")
                self._backfill_missing_account_ids(conn)
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_users_account_id
                    ON users(account_id)
                    WHERE account_id IS NOT NULL AND TRIM(account_id) <> ''
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def _create_user(self, display_name: Optional[str], email: Optional[str]) -> int:
        now = _iso(_utcnow())
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO users(account_id, display_name, email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self._generate_account_id(), display_name, email, now, now),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _count_lines(self, text: str) -> int:
        if not text:
            return 0
        return len(text.split("\n"))

    def _estimate_edited_lines_from_tool_use(self, tool_name: str, tool_input: Dict[str, object]) -> int:
        if tool_name == "Write":
            content = tool_input.get("content")
            return self._count_lines(content if isinstance(content, str) else "")

        if tool_name == "Edit":
            old_string = tool_input.get("old_string")
            new_string = tool_input.get("new_string")
            old_lines = self._count_lines(old_string if isinstance(old_string, str) else "")
            new_lines = self._count_lines(new_string if isinstance(new_string, str) else "")
            return max(old_lines, new_lines)

        if tool_name == "MultiEdit":
            edits = tool_input.get("edits")
            if not isinstance(edits, list) or len(edits) == 0:
                old_string = tool_input.get("old_string")
                new_string = tool_input.get("new_string")
                return max(
                    self._count_lines(old_string if isinstance(old_string, str) else ""),
                    self._count_lines(new_string if isinstance(new_string, str) else ""),
                )

            total = 0
            for item in edits:
                if not isinstance(item, dict):
                    continue
                old_string = item.get("old_string")
                new_string = item.get("new_string")
                total += max(
                    self._count_lines(old_string if isinstance(old_string, str) else ""),
                    self._count_lines(new_string if isinstance(new_string, str) else ""),
                )
            return total

        return 0

    def _extract_usage_from_record(self, record: object) -> Optional[Dict[str, object]]:
        if not isinstance(record, dict):
            return None

        def pick_usage(value: object) -> Optional[Dict[str, object]]:
            if isinstance(value, dict) and (
                value.get("input_tokens") is not None or value.get("output_tokens") is not None
            ):
                return value
            return None

        return (
            pick_usage(record.get("message", {}).get("usage") if isinstance(record.get("message"), dict) else None)
            or pick_usage(record.get("usage"))
            or pick_usage(record.get("token_usage"))
        )

    def _extract_record_timestamp(self, record: object) -> Optional[str]:
        if not isinstance(record, dict):
            return None

        value = record.get("timestamp")
        if isinstance(value, str) and value.strip():
            return value.strip()

        message = record.get("message")
        if isinstance(message, dict):
            nested = message.get("timestamp")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()

        return None

    def _to_day_key(self, timestamp_value: str) -> Optional[str]:
        try:
            normalized = timestamp_value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except Exception:
            return None
        return parsed.date().isoformat()

    def _payload_hash(self, payload_json: str) -> str:
        return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    def _rebuild_cloud_session_day_stats(
        self,
        conn: sqlite3.Connection,
        user_id: int,
        session_id: str,
        payload_json: str,
    ) -> None:
        try:
            payload = json.loads(payload_json)
        except Exception:
            payload = {}

        messages = payload.get("messages")
        if not isinstance(messages, list):
            messages = []

        day_map: Dict[str, Dict[str, int]] = {}
        counted_usage_message_ids = set()
        counted_tool_use_ids = set()

        for record in messages:
            if not isinstance(record, dict) or record.get("type") != "assistant":
                continue

            timestamp = self._extract_record_timestamp(record)
            if not timestamp:
                continue
            day = self._to_day_key(timestamp)
            if not day:
                continue

            bucket = day_map.setdefault(day, {"edit_lines": 0, "input_tokens": 0})

            message = record.get("message")
            message_id = ""
            if isinstance(message, dict):
                message_id = str(message.get("id") or "")
            if not message_id:
                message_id = str(record.get("uuid") or "")

            usage = self._extract_usage_from_record(record)
            usage_input = 0
            if isinstance(usage, dict):
                try:
                    usage_input = int(usage.get("input_tokens") or 0)
                except Exception:
                    usage_input = 0
            if usage_input > 0:
                usage_dedup_key = message_id or f"{day}:{len(json.dumps(record, ensure_ascii=False))}:{usage_input}"
                if usage_dedup_key not in counted_usage_message_ids:
                    bucket["input_tokens"] += usage_input
                    counted_usage_message_ids.add(usage_dedup_key)

            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue

            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_use":
                    continue
                tool_name = str(part.get("name") or "")
                if tool_name not in {"Write", "Edit", "MultiEdit"}:
                    continue
                tool_input = part.get("input")
                if not isinstance(tool_input, dict):
                    tool_input = {}
                tool_dedup_key = str(part.get("id") or "") or (
                    f"{message_id}:{tool_name}:{json.dumps(tool_input, ensure_ascii=False, sort_keys=True)}"
                )
                if tool_dedup_key in counted_tool_use_ids:
                    continue
                counted_tool_use_ids.add(tool_dedup_key)
                bucket["edit_lines"] += self._estimate_edited_lines_from_tool_use(tool_name, tool_input)

        conn.execute(
            """
            DELETE FROM cloud_session_day_stats
            WHERE user_id=? AND session_id=?
            """,
            (user_id, session_id),
        )

        for day, bucket in day_map.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO cloud_session_day_stats(
                    user_id, session_id, day, edit_lines, input_tokens
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    session_id,
                    day,
                    max(0, int(bucket["edit_lines"])),
                    max(0, int(bucket["input_tokens"])),
                ),
            )

        conn.execute(
            """
            INSERT INTO cloud_session_stats_cache(user_id, session_id, payload_hash, synced_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, session_id)
            DO UPDATE SET payload_hash=excluded.payload_hash, synced_at=excluded.synced_at
            """,
            (user_id, session_id, self._payload_hash(payload_json), _iso(_utcnow())),
        )

    def _ensure_cloud_stats_backfilled(self, conn: sqlite3.Connection, user_id: int) -> None:
        rows = conn.execute(
            """
            SELECT cs.session_id, cs.payload_json, cache.payload_hash
            FROM cloud_sessions cs
            LEFT JOIN cloud_session_stats_cache cache
              ON cache.user_id = cs.user_id AND cache.session_id = cs.session_id
            WHERE cs.user_id=?
            """,
            (user_id,),
        ).fetchall()

        for row in rows:
            payload_json = row["payload_json"] or ""
            payload_hash = self._payload_hash(payload_json)
            if row["payload_hash"] == payload_hash:
                continue
            self._rebuild_cloud_session_day_stats(
                conn,
                user_id,
                str(row["session_id"]),
                payload_json,
            )

    def _upsert_identity(
        self,
        user_id: int,
        provider: str,
        provider_user_id: str,
        email: Optional[str],
    ) -> None:
        now = _iso(_utcnow())
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO identity_accounts(user_id, provider, provider_user_id, email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_user_id)
                DO UPDATE SET user_id=excluded.user_id, email=excluded.email, updated_at=excluded.updated_at
                """,
                (user_id, provider, provider_user_id, email, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def _find_user_by_identity(self, provider: str, provider_user_id: str) -> Optional[int]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT user_id FROM identity_accounts
                WHERE provider=? AND provider_user_id=?
                LIMIT 1
                """,
                (provider, provider_user_id),
            ).fetchone()
            return int(row["user_id"]) if row else None
        finally:
            conn.close()

    def ensure_platform_shadow_user(self, identity: PlatformIdentity) -> int:
        with self._lock:
            existing = self._find_user_by_identity(identity.provider, identity.provider_user_id)
            if existing is not None:
                return existing

            user_id = self._create_user(identity.display_name, identity.email)
            self._upsert_identity(
                user_id=user_id,
                provider=identity.provider,
                provider_user_id=identity.provider_user_id,
                email=identity.email,
            )
            return user_id

    def ensure_platform_shadow_user_from_token(
        self,
        token: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> int:
        token = (token or "").strip()
        if not token:
            raise ValueError("platform token is required")

        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        identity = PlatformIdentity(
            provider="platform",
            provider_user_id=f"platform-{digest[:24]}",
            token_fingerprint=digest[:12],
            display_name=display_name,
            email=email,
        )
        return self.ensure_platform_shadow_user(identity)

    def register_local_user(
        self,
        username_or_email: str,
        password: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> int:
        identifier = _normalize_local_identifier(username_or_email)
        if not identifier:
            raise ValueError("identifier is required")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")

        with self._lock:
            existing = self._find_user_by_identity("local", identifier)
            if existing is not None:
                raise ValueError("local account already exists")

            user_id = self._create_user(display_name=display_name, email=email)
            self._upsert_identity(
                user_id=user_id,
                provider="local",
                provider_user_id=identifier,
                email=email,
            )

            salt = os.urandom(16)
            hashed = _pbkdf2_hash_password(password, salt)
            now = _iso(_utcnow())

            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO local_credentials(user_id, password_hash, password_salt, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, hashed, base64.b64encode(salt).decode("ascii"), now),
                )
                conn.commit()
            finally:
                conn.close()

            return user_id

    def verify_local_credentials(self, identifier: str, password: str) -> Optional[int]:
        normalized = _normalize_local_identifier(identifier)
        if not normalized:
            return None

        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT ia.user_id, lc.password_hash, lc.password_salt
                FROM identity_accounts ia
                JOIN local_credentials lc ON lc.user_id = ia.user_id
                WHERE ia.provider='local' AND ia.provider_user_id=?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if not row:
                return None

            salt = base64.b64decode(row["password_salt"].encode("ascii"))
            expected = row["password_hash"]
            actual = _pbkdf2_hash_password(password, salt)
            if not hmac.compare_digest(actual, expected):
                return None
            return int(row["user_id"])
        finally:
            conn.close()

    def create_session(self, user_id: int, auth_source: str) -> AuthSession:
        token = secrets.token_urlsafe(40)
        now = _utcnow()
        expires_at = now + timedelta(seconds=config.auth_session_ttl_seconds)
        now_iso = _iso(now)
        expires_iso = _iso(expires_at)

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO auth_sessions(token, user_id, auth_source, created_at, expires_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token, user_id, auth_source, now_iso, expires_iso, now_iso),
            )
            conn.commit()
        finally:
            conn.close()

        return AuthSession(token=token, user_id=user_id, auth_source=auth_source, expires_at=expires_at)

    def get_session(self, token: str) -> Optional[AuthSession]:
        if not token:
            return None

        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT token, user_id, auth_source, expires_at
                FROM auth_sessions
                WHERE token=?
                LIMIT 1
                """,
                (token,),
            ).fetchone()
            if not row:
                return None

            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= _utcnow():
                self.revoke_session(token)
                return None

            conn.execute(
                "UPDATE auth_sessions SET last_seen_at=? WHERE token=?",
                (_iso(_utcnow()), token),
            )
            conn.commit()
            return AuthSession(
                token=row["token"],
                user_id=int(row["user_id"]),
                auth_source=row["auth_source"],
                expires_at=expires_at,
            )
        finally:
            conn.close()

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        conn = self._connect()
        try:
            conn.execute("DELETE FROM auth_sessions WHERE token=?", (token,))
            conn.commit()
        finally:
            conn.close()

    def get_user_profile(self, user_id: int) -> Optional[Dict[str, object]]:
        conn = self._connect()
        try:
            user = conn.execute(
                """
                SELECT id, account_id, display_name, email, status, created_at, updated_at
                FROM users
                WHERE id=?
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if not user:
                return None

            identities = conn.execute(
                """
                SELECT provider, provider_user_id, email, created_at, updated_at
                FROM identity_accounts
                WHERE user_id=?
                ORDER BY provider ASC
                """,
                (user_id,),
            ).fetchall()

            return {
                "id": int(user["id"]),
                "account_id": user["account_id"],
                "display_name": user["display_name"],
                "email": user["email"],
                "status": user["status"],
                "created_at": user["created_at"],
                "updated_at": user["updated_at"],
                "identities": [
                    {
                        "provider": row["provider"],
                        "provider_user_id": row["provider_user_id"],
                        "email": row["email"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                    for row in identities
                ],
            }
        finally:
            conn.close()

    def get_user_profile_by_account_id(self, account_id: str) -> Optional[Dict[str, object]]:
        normalized = (account_id or "").strip()
        if not normalized:
            return None

        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT id
                FROM users
                WHERE account_id=?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if not row:
                return None
            return self.get_user_profile(int(row["id"]))
        finally:
            conn.close()

    def get_user_id_by_account_id(self, account_id: str) -> Optional[int]:
        normalized = (account_id or "").strip()
        if not normalized:
            return None

        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT id
                FROM users
                WHERE account_id=?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            return int(row["id"]) if row else None
        finally:
            conn.close()

    def upsert_cloud_session(
        self,
        account_id: str,
        session_id: str,
        title: str,
        date_created: Optional[str],
        last_modified: Optional[str],
        last_user_message_at: Optional[str],
        file_size: int,
        message_count: int,
        payload_json: str,
    ) -> CloudSessionRecord:
        user_id = self.get_user_id_by_account_id(account_id)
        if user_id is None:
            raise ValueError("account not found")

        normalized_session_id = (session_id or "").strip()
        if not normalized_session_id:
            raise ValueError("session_id is required")

        now = _iso(_utcnow())
        conn = self._connect()
        try:
            existing = conn.execute(
                """
                SELECT created_at
                FROM cloud_sessions
                WHERE user_id=? AND session_id=?
                LIMIT 1
                """,
                (user_id, normalized_session_id),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO cloud_sessions(
                    user_id, session_id, title, date_created, last_modified,
                    last_user_message_at, file_size, message_count, payload_json,
                    deleted_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(user_id, session_id)
                DO UPDATE SET
                    title=excluded.title,
                    date_created=excluded.date_created,
                    last_modified=excluded.last_modified,
                    last_user_message_at=excluded.last_user_message_at,
                    file_size=excluded.file_size,
                    message_count=excluded.message_count,
                    payload_json=excluded.payload_json,
                    deleted_at=NULL,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    normalized_session_id,
                    title,
                    date_created,
                    last_modified,
                    last_user_message_at,
                    max(0, int(file_size or 0)),
                    max(0, int(message_count or 0)),
                    payload_json,
                    created_at,
                    now,
                ),
            )
            self._rebuild_cloud_session_day_stats(
                conn,
                user_id,
                normalized_session_id,
                payload_json,
            )
            conn.execute(
                """
                DELETE FROM cloud_session_tombstones
                WHERE user_id=? AND session_id=?
                """,
                (user_id, normalized_session_id),
            )
            conn.commit()
            return self.get_cloud_session(account_id, normalized_session_id)  # type: ignore[return-value]
        finally:
            conn.close()

    def list_cloud_sessions(self, account_id: str) -> List[CloudSessionRecord]:
        user_id = self.get_user_id_by_account_id(account_id)
        if user_id is None:
            return []

        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT session_id, title, date_created, last_modified, last_user_message_at,
                       file_size, message_count, updated_at, payload_json
                FROM cloud_sessions
                WHERE user_id=? AND deleted_at IS NULL
                ORDER BY COALESCE(last_user_message_at, last_modified, updated_at) DESC
                """,
                (user_id,),
            ).fetchall()
            return [
                CloudSessionRecord(
                    session_id=row["session_id"],
                    title=row["title"] or row["session_id"],
                    date_created=row["date_created"],
                    last_modified=row["last_modified"],
                    last_user_message_at=row["last_user_message_at"],
                    file_size=int(row["file_size"] or 0),
                    message_count=int(row["message_count"] or 0),
                    updated_at=row["updated_at"],
                    payload_json=row["payload_json"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_cloud_session(self, account_id: str, session_id: str) -> Optional[CloudSessionRecord]:
        user_id = self.get_user_id_by_account_id(account_id)
        if user_id is None:
            return None

        normalized_session_id = (session_id or "").strip()
        if not normalized_session_id:
            return None

        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT session_id, title, date_created, last_modified, last_user_message_at,
                       file_size, message_count, updated_at, payload_json
                FROM cloud_sessions
                WHERE user_id=? AND session_id=? AND deleted_at IS NULL
                LIMIT 1
                """,
                (user_id, normalized_session_id),
            ).fetchone()
            if not row:
                return None
            return CloudSessionRecord(
                session_id=row["session_id"],
                title=row["title"] or row["session_id"],
                date_created=row["date_created"],
                last_modified=row["last_modified"],
                last_user_message_at=row["last_user_message_at"],
                file_size=int(row["file_size"] or 0),
                message_count=int(row["message_count"] or 0),
                updated_at=row["updated_at"],
                payload_json=row["payload_json"],
            )
        finally:
            conn.close()

    def delete_cloud_session(self, account_id: str, session_id: str) -> bool:
        user_id = self.get_user_id_by_account_id(account_id)
        if user_id is None:
            return False

        normalized_session_id = (session_id or "").strip()
        if not normalized_session_id:
            return False

        conn = self._connect()
        try:
            deleted_at = _iso(_utcnow())
            conn.execute(
                """
                INSERT INTO cloud_session_tombstones(user_id, session_id, deleted_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, session_id)
                DO UPDATE SET deleted_at=excluded.deleted_at
                """,
                (user_id, normalized_session_id, deleted_at),
            )
            conn.execute(
                """
                UPDATE cloud_sessions
                SET deleted_at=?, updated_at=?
                WHERE user_id=? AND session_id=?
                """,
                (deleted_at, deleted_at, user_id, normalized_session_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_cloud_daily_productivity_stats(
        self,
        account_id: str,
        start_day: str,
        end_day: str,
    ) -> List[DailyProductivityStatRecord]:
        with self._lock:
            user_id = self.get_user_id_by_account_id(account_id)
            if user_id is None:
                return []

            conn = self._connect()
            try:
                self._ensure_cloud_stats_backfilled(conn, user_id)
                conn.commit()
                rows = conn.execute(
                    """
                    SELECT day, SUM(edit_lines) AS edit_lines, SUM(input_tokens) AS input_tokens
                    FROM cloud_session_day_stats
                    WHERE user_id=? AND day >= ? AND day <= ?
                    GROUP BY day
                    ORDER BY day ASC
                    """,
                    (user_id, start_day, end_day),
                ).fetchall()
                return [
                    DailyProductivityStatRecord(
                        day=row["day"],
                        edit_lines=int(row["edit_lines"] or 0),
                        input_tokens=int(row["input_tokens"] or 0),
                    )
                    for row in rows
                ]
            finally:
                conn.close()

    def list_cloud_session_deletions(self, account_id: str) -> List[CloudSessionDeletionRecord]:
        user_id = self.get_user_id_by_account_id(account_id)
        if user_id is None:
            return []

        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT session_id, deleted_at
                FROM cloud_session_tombstones
                WHERE user_id=?
                ORDER BY deleted_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [
                CloudSessionDeletionRecord(
                    session_id=row["session_id"],
                    deleted_at=row["deleted_at"],
                )
                for row in rows
            ]
        finally:
            conn.close()


auth_store = AuthStore(config.auth_db_path)
