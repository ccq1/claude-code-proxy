#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from ghidra_headless import (
    GhidraRuntimeError,
    disassemble as ghidra_disassemble,
    decompile_function as ghidra_decompile_function,
    export_strings as ghidra_export_strings,
    get_call_graph as ghidra_get_call_graph,
    get_program_metadata as ghidra_get_program_metadata,
    get_xrefs as ghidra_get_xrefs,
    import_binary as ghidra_import_binary,
    list_data_types as ghidra_list_data_types,
    list_functions as ghidra_list_functions,
    list_import_exports as ghidra_list_import_exports,
    list_segments as ghidra_list_segments,
    read_memory as ghidra_read_memory,
    search_symbol as ghidra_search_symbol,
)

SERVER_NAME = "ghidra-decompiler"
SERVER_VERSION = "0.3.0"

WORKSPACE_ROOT_ENV = "GHIDRA_WORKSPACE_ROOT"
SESSION_IDLE_TTL_ENV = "GHIDRA_SESSION_IDLE_TTL_SECONDS"
DEFAULT_SESSION_IDLE_TTL_SECONDS = 300
DEFAULT_PROGRAM_ROUTE = "__default__"
LOCK_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


@dataclass
class SessionRecord:
    session_id: str
    workspace_root: str
    created_at: float
    last_used_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "workspace_root": self.workspace_root,
            "created_at_epoch": self.created_at,
            "last_used_at_epoch": self.last_used_at,
        }


class GhidraMCPService:
    def __init__(self) -> None:
        self._state_lock = threading.Lock()
        self._default_workspace_lock = threading.Lock()
        self._session_locks: dict[str, threading.Lock] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._program_sessions: dict[str, str] = {}

        self._base_workspace_root = self._resolve_base_workspace_root()
        self._session_idle_ttl_seconds = self._resolve_idle_ttl_seconds()

    def _resolve_base_workspace_root(self) -> Path:
        configured = self._normalize_env_value(os.environ.get(WORKSPACE_ROOT_ENV))
        if configured:
            return Path(configured).expanduser().resolve()
        return (Path.home() / ".cache" / "pandoraq-ghidra-decompiler").resolve()

    def _resolve_idle_ttl_seconds(self) -> int:
        configured = self._normalize_env_value(os.environ.get(SESSION_IDLE_TTL_ENV))
        if not configured:
            return DEFAULT_SESSION_IDLE_TTL_SECONDS
        try:
            value = int(configured)
        except ValueError:
            return DEFAULT_SESSION_IDLE_TTL_SECONDS
        return max(30, value)

    @staticmethod
    def _normalize_env_value(raw_value: str | None) -> str | None:
        if not raw_value:
            return None
        value = raw_value.strip()
        if not value or (value.startswith("{{") and value.endswith("}}")):
            return None
        return value

    def _validate_session_id(self, session_id: str) -> str:
        normalized = session_id.strip()
        if not normalized:
            raise GhidraRuntimeError("session_id 不能为空。", error_code="invalid_session_id")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", normalized):
            raise GhidraRuntimeError(
                "session_id 仅允许字母、数字、-、_，长度不超过 64。",
                error_code="invalid_session_id",
            )
        return normalized

    def _new_session_id(self) -> str:
        return "sess-{0}-{1}".format(int(time.time()), uuid.uuid4().hex[:8])

    def _session_workspace(self, session_id: str) -> Path:
        return (self._base_workspace_root / "sessions" / session_id).resolve()

    def _gc_sessions_locked(self) -> None:
        now = time.time()
        expired_ids = [
            session_id
            for session_id, record in self._sessions.items()
            if now - record.last_used_at > self._session_idle_ttl_seconds
        ]
        for session_id in expired_ids:
            del self._sessions[session_id]
            self._session_locks.pop(session_id, None)
            for program_id, mapped in list(self._program_sessions.items()):
                if mapped == session_id:
                    del self._program_sessions[program_id]

    def _ensure_session(self, session_id: str | None, *, auto_create: bool) -> SessionRecord | None:
        if session_id is None:
            if not auto_create:
                return None
            session_id = self._new_session_id()

        normalized = self._validate_session_id(session_id)
        now = time.time()

        with self._state_lock:
            self._gc_sessions_locked()
            existing = self._sessions.get(normalized)
            if existing:
                existing.last_used_at = now
                return existing

            if not auto_create:
                raise GhidraRuntimeError(
                    "session_id 不存在: {0}".format(normalized),
                    error_code="session_not_found",
                    details={"session_id": normalized},
                )

            workspace = self._session_workspace(normalized)
            workspace.mkdir(parents=True, exist_ok=True)
            created = SessionRecord(
                session_id=normalized,
                workspace_root=str(workspace),
                created_at=now,
                last_used_at=now,
            )
            self._sessions[normalized] = created
            self._session_locks[normalized] = threading.Lock()
            return created

    def _close_session(self, session_id: str, purge_workspace: bool) -> dict[str, Any]:
        normalized = self._validate_session_id(session_id)
        removed = False
        workspace_root = str(self._session_workspace(normalized))
        removed_program_ids: list[str] = []

        with self._state_lock:
            self._gc_sessions_locked()
            session = self._sessions.pop(normalized, None)
            if session:
                removed = True
                workspace_root = session.workspace_root
            self._session_locks.pop(normalized, None)
            for program_id, mapped in list(self._program_sessions.items()):
                if mapped == normalized:
                    removed_program_ids.append(program_id)
                    del self._program_sessions[program_id]

        purged = False
        purge_error = None
        if purge_workspace:
            try:
                import shutil

                shutil.rmtree(workspace_root, ignore_errors=False)
                purged = True
            except FileNotFoundError:
                purged = True
            except Exception as exc:  # pragma: no cover
                purge_error = str(exc)

        return {
            "session_id": normalized,
            "closed": removed,
            "workspace_root": workspace_root,
            "purge_workspace": purge_workspace,
            "workspace_purged": purged,
            "purge_error": purge_error,
            "removed_program_ids": removed_program_ids,
        }

    def _infer_session_for_call(self, *, session_id: str | None, program_id: str | None, require_program: bool) -> str | None:
        if session_id is not None and session_id.strip():
            return self._validate_session_id(session_id)

        if not require_program or not program_id:
            return None

        with self._state_lock:
            mapped = self._program_sessions.get(program_id)
            if not mapped or mapped == DEFAULT_PROGRAM_ROUTE:
                return None
            return mapped

    @contextmanager
    def _workspace_context(self, workspace_root: str | None):
        if not workspace_root:
            yield
            return

        previous = os.environ.get(WORKSPACE_ROOT_ENV)
        os.environ[WORKSPACE_ROOT_ENV] = workspace_root
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop(WORKSPACE_ROOT_ENV, None)
            else:
                os.environ[WORKSPACE_ROOT_ENV] = previous

    def _execute_with_session(
        self,
        *,
        tool_name: str,
        session_id: str | None,
        program_id: str | None,
        auto_create_session: bool,
        require_program: bool,
        callback: Callable[[], dict[str, Any]],
    ) -> tuple[dict[str, Any], str | None]:
        resolved_session_id = self._infer_session_for_call(
            session_id=session_id,
            program_id=program_id,
            require_program=require_program,
        )
        session = self._ensure_session(resolved_session_id, auto_create=auto_create_session)

        if session is None:
            lock = self._default_workspace_lock
        else:
            with self._state_lock:
                lock = self._session_locks.setdefault(session.session_id, threading.Lock())

        for attempt in range(len(LOCK_RETRY_BACKOFF_SECONDS) + 1):
            try:
                with lock:
                    workspace_root = session.workspace_root if session else None
                    with self._workspace_context(workspace_root):
                        result = callback()

                if session:
                    with self._state_lock:
                        refreshed = self._sessions.get(session.session_id)
                        if refreshed:
                            refreshed.last_used_at = time.time()
                return result, (session.session_id if session else None)
            except GhidraRuntimeError as exc:
                if exc.error_code != "project_locked" or attempt >= len(LOCK_RETRY_BACKOFF_SECONDS):
                    raise
                time.sleep(LOCK_RETRY_BACKOFF_SECONDS[attempt])

        raise GhidraRuntimeError(
            "project lock retry exhausted",
            error_code="project_locked",
            details={"tool": tool_name},
        )

    def create_session(self, session_id: str | None = None) -> dict[str, Any]:
        requested_id = session_id if isinstance(session_id, str) and session_id.strip() else None
        session = self._ensure_session(requested_id, auto_create=True)
        assert session is not None
        return {
            "session": session.to_dict(),
            "idle_ttl_seconds": self._session_idle_ttl_seconds,
            "base_workspace_root": str(self._base_workspace_root),
        }

    def list_sessions(self) -> dict[str, Any]:
        with self._state_lock:
            self._gc_sessions_locked()
            sessions = [record.to_dict() for record in sorted(self._sessions.values(), key=lambda x: x.last_used_at)]
        return {
            "count": len(sessions),
            "idle_ttl_seconds": self._session_idle_ttl_seconds,
            "sessions": sessions,
        }

    def close_session(self, session_id: str, purge_workspace: bool = False) -> dict[str, Any]:
        return self._close_session(session_id, purge_workspace)

    def import_binary(
        self,
        *,
        binary_path: str,
        force_reimport: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="import_binary",
            session_id=session_id,
            program_id=None,
            auto_create_session=True,
            require_program=False,
            callback=lambda: ghidra_import_binary(
                binary_path=binary_path,
                force_reimport=force_reimport,
            ),
        )

        program_id = result.get("program_id")
        if isinstance(program_id, str) and program_id:
            with self._state_lock:
                self._program_sessions[program_id] = resolved_session_id or DEFAULT_PROGRAM_ROUTE

        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def list_functions(
        self,
        *,
        program_id: str,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="list_functions",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_list_functions(
                program_id=program_id,
                query=query,
                limit=limit,
                offset=offset,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def decompile_function(
        self,
        *,
        program_id: str,
        function_name: str | None = None,
        address: str | None = None,
        timeout_seconds: int = 30,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="decompile_function",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_decompile_function(
                program_id=program_id,
                function_name=function_name,
                address=address,
                timeout_seconds=timeout_seconds,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def export_strings(
        self,
        *,
        program_id: str,
        min_length: int = 4,
        limit: int = 50,
        offset: int = 0,
        query: str | None = None,
        save_to_file: bool = True,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="export_strings",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_export_strings(
                program_id=program_id,
                min_length=min_length,
                limit=limit,
                offset=offset,
                query=query,
                save_to_file=save_to_file,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def search_symbol(
        self,
        *,
        program_id: str,
        query: str,
        limit: int = 50,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="search_symbol",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_search_symbol(
                program_id=program_id,
                query=query,
                limit=limit,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def get_program_metadata(
        self,
        *,
        program_id: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="get_program_metadata",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_get_program_metadata(program_id=program_id),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def list_segments(
        self,
        *,
        program_id: str,
        limit: int = 200,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="list_segments",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_list_segments(
                program_id=program_id,
                limit=limit,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def get_xrefs(
        self,
        *,
        program_id: str,
        function_name: str | None = None,
        address: str | None = None,
        direction: str = "to",
        limit: int = 100,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="get_xrefs",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_get_xrefs(
                program_id=program_id,
                function_name=function_name,
                address=address,
                direction=direction,
                limit=limit,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def disassemble(
        self,
        *,
        program_id: str,
        function_name: str | None = None,
        address: str | None = None,
        max_instructions: int = 80,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="disassemble",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_disassemble(
                program_id=program_id,
                function_name=function_name,
                address=address,
                max_instructions=max_instructions,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def get_call_graph(
        self,
        *,
        program_id: str,
        function_name: str | None = None,
        address: str | None = None,
        limit: int = 100,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="get_call_graph",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_get_call_graph(
                program_id=program_id,
                function_name=function_name,
                address=address,
                limit=limit,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def list_import_exports(
        self,
        *,
        program_id: str,
        query: str | None = None,
        limit: int = 200,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="list_import_exports",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_list_import_exports(
                program_id=program_id,
                query=query,
                limit=limit,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def list_data_types(
        self,
        *,
        program_id: str,
        query: str | None = None,
        kind: str | None = None,
        limit: int = 100,
        include_members: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="list_data_types",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_list_data_types(
                program_id=program_id,
                query=query,
                kind=kind,
                limit=limit,
                include_members=include_members,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def read_memory(
        self,
        *,
        program_id: str,
        address: str,
        length: int = 128,
        row_width: int = 16,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result, resolved_session_id = self._execute_with_session(
            tool_name="read_memory",
            session_id=session_id,
            program_id=program_id,
            auto_create_session=False,
            require_program=True,
            callback=lambda: ghidra_read_memory(
                program_id=program_id,
                address=address,
                length=length,
                row_width=row_width,
            ),
        )
        if resolved_session_id:
            result["session_id"] = resolved_session_id
        return result

    def summarize_tool_error(self, tool_name: str, error: GhidraRuntimeError) -> str:
        if error.error_code == "missing_jdk":
            return (
                "当前环境缺少 JDK 21。\n"
                "请安装 JDK 21+，并配置 GHIDRA_JAVA_HOME / JAVA_HOME，"
                "或保证 PATH 中存在可用的 java。\n"
                "tool: {0}".format(tool_name)
            )

        if error.error_code == "unsupported_jdk":
            detected = error.details.get("detected_java_major_version")
            return (
                "当前环境的 Java 版本不满足 Ghidra 12.0.4 要求，需要 JDK 21+。\n"
                "detected_java_major_version: {0}\n"
                "tool: {1}".format(detected if detected is not None else "unknown", tool_name)
            )

        if error.error_code == "broken_jdk":
            return (
                "当前环境里的 java 无法正常执行 `java -version`。\n"
                "请确认本机安装的是可用的 JDK 21+。\n"
                "tool: {0}".format(tool_name)
            )

        if error.error_code == "missing_ghidra_install":
            return (
                "当前环境未发现可用 Ghidra 安装，无法调用 analyzeHeadless。\n"
                "请配置 GHIDRA_INSTALL_DIR（安装目录或 analyzeHeadless 文件路径）。\n"
                "tool: {0}".format(tool_name)
            )

        if error.error_code == "project_locked":
            return (
                "当前项目正在被占用，插件已自动重试但仍未拿到锁。\n"
                "请稍后重试，或切换到独立 session。\n"
                "tool: {0}".format(tool_name)
            )

        if error.error_code == "session_not_found":
            return (
                "指定的 session 不存在或已过期。\n"
                "请先 create_session，或重新 import_binary。\n"
                "tool: {0}".format(tool_name)
            )

        if error.error_code == "invalid_session_id":
            return (
                "session_id 不合法，仅允许字母、数字、-、_。\n"
                "tool: {0}".format(tool_name)
            )

        return str(error)


service = GhidraMCPService()
mcp = FastMCP(
    name=SERVER_NAME,
    instructions=(
        "Offline local Ghidra headless MCP server. "
        "Always import_binary before any program-specific tool such as get_program_metadata, list_functions, "
        "list_segments, get_xrefs, disassemble, decompile_function, get_call_graph, export_strings, "
        "search_symbol, list_import_exports, list_data_types, or read_memory. "
        "All binary paths must be local filesystem paths."
    ),
)


def _raise_tool_error(tool_name: str, error: GhidraRuntimeError) -> None:
    message = service.summarize_tool_error(tool_name, error)
    details = error.to_dict()
    details.pop("error", None)
    if details:
        message += "\n" + json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True)
    raise ToolError(message)


@mcp.tool(
    name="create_session",
    description="创建一个可复用的分析会话，返回 session_id 与会话 workspace 目录。",
    structured_output=True,
)
def create_session(session_id: str | None = None) -> dict[str, Any]:
    """创建一个可复用的分析会话。

    Args:
        session_id: 可选。自定义会话 ID，仅允许字母、数字、-、_。
    """

    try:
        return service.create_session(session_id=session_id)
    except GhidraRuntimeError as error:
        _raise_tool_error("create_session", error)


@mcp.tool(
    name="list_sessions",
    description="列出当前 server 内存中活跃的会话。",
    structured_output=True,
)
def list_sessions() -> dict[str, Any]:
    """列出当前活跃的分析会话。"""

    return service.list_sessions()


@mcp.tool(
    name="close_session",
    description="关闭会话并清理路由状态；可选删除会话工作目录。",
    structured_output=True,
)
def close_session(session_id: str, purge_workspace: bool = False) -> dict[str, Any]:
    """关闭会话并按需清理 workspace。

    Args:
        session_id: 要关闭的会话 ID。
        purge_workspace: 若为 true，同时删除该 session 的 workspace 目录。
    """

    try:
        return service.close_session(session_id=session_id, purge_workspace=purge_workspace)
    except GhidraRuntimeError as error:
        _raise_tool_error("close_session", error)


@mcp.tool(
    name="import_binary",
    description="导入本地二进制到 Ghidra headless project，并返回后续分析所需的 program_id。",
    structured_output=True,
)
def import_binary(binary_path: str, force_reimport: bool = False, session_id: str | None = None) -> dict[str, Any]:
    """导入本地 ELF/PE/Mach-O 样本。

    Args:
        binary_path: 本地样本路径。
        force_reimport: 若为 true，则丢弃已有缓存并重新导入。
        session_id: 可选。分析会话 ID；若省略会自动创建。
    """

    try:
        return service.import_binary(
            binary_path=binary_path,
            force_reimport=force_reimport,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("import_binary", error)


@mcp.tool(
    name="list_functions",
    description="列出当前样本的函数，可按名称做子串过滤。",
    structured_output=True,
)
def list_functions(
    program_id: str,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session_id: str | None = None,
) -> dict[str, Any]:
    """列出样本中的函数。

    Args:
        program_id: import_binary 返回的 program_id。
        query: 可选。按函数名做子串过滤。
        limit: 返回数量上限。
        offset: 分页偏移。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.list_functions(
            program_id=program_id,
            query=query,
            limit=limit,
            offset=offset,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("list_functions", error)


@mcp.tool(
    name="decompile_function",
    description="按函数名或入口地址反编译单个函数。",
    structured_output=True,
)
def decompile_function(
    program_id: str,
    function_name: str | None = None,
    address: str | None = None,
    timeout_seconds: int = 30,
    session_id: str | None = None,
) -> dict[str, Any]:
    """反编译单个函数。

    Args:
        program_id: import_binary 返回的 program_id。
        function_name: 可选。精确函数名或主要名称。
        address: 可选。函数入口地址，例如 00401230 或 0x00401230。
        timeout_seconds: 反编译超时时间。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.decompile_function(
            program_id=program_id,
            function_name=function_name,
            address=address,
            timeout_seconds=timeout_seconds,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("decompile_function", error)


@mcp.tool(
    name="export_strings",
    description="按分页和关键词预览当前样本中的已定义字符串，并可把筛选结果落到 artifact 文件。",
    structured_output=True,
)
def export_strings(
    program_id: str,
    min_length: int = 4,
    limit: int = 50,
    offset: int = 0,
    query: str | None = None,
    save_to_file: bool = True,
    session_id: str | None = None,
) -> dict[str, Any]:
    """分页导出样本字符串。

    Args:
        program_id: import_binary 返回的 program_id。
        min_length: 字符串最小长度。
        limit: 当前页返回上限。
        offset: 分页偏移。
        query: 可选。按字符串内容做大小写不敏感的子串过滤。
        save_to_file: 默认为 true，把筛选结果保存为 workspace 中的 artifact 文件。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.export_strings(
            program_id=program_id,
            min_length=min_length,
            limit=limit,
            offset=offset,
            query=query,
            save_to_file=save_to_file,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("export_strings", error)


@mcp.tool(
    name="search_symbol",
    description="按关键词搜索函数和其他符号，适合快速定位命名入口。",
    structured_output=True,
)
def search_symbol(program_id: str, query: str, limit: int = 50, session_id: str | None = None) -> dict[str, Any]:
    """搜索符号。

    Args:
        program_id: import_binary 返回的 program_id。
        query: 搜索关键词。
        limit: 返回数量上限。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.search_symbol(
            program_id=program_id,
            query=query,
            limit=limit,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("search_symbol", error)


@mcp.tool(
    name="get_program_metadata",
    description="获取当前样本的程序元信息、入口点候选与建议分析起点。",
    structured_output=True,
)
def get_program_metadata(program_id: str, session_id: str | None = None) -> dict[str, Any]:
    """获取程序元信息。

    Args:
        program_id: import_binary 返回的 program_id。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.get_program_metadata(
            program_id=program_id,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("get_program_metadata", error)


@mcp.tool(
    name="list_segments",
    description="列出程序内存段/节信息，包括地址范围、权限和初始化状态。",
    structured_output=True,
)
def list_segments(program_id: str, limit: int = 200, session_id: str | None = None) -> dict[str, Any]:
    """列出内存段。

    Args:
        program_id: import_binary 返回的 program_id。
        limit: 返回数量上限。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.list_segments(
            program_id=program_id,
            limit=limit,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("list_segments", error)


@mcp.tool(
    name="get_xrefs",
    description="获取函数入口或指定地址的交叉引用，可查看谁引用它或它引用了谁。",
    structured_output=True,
)
def get_xrefs(
    program_id: str,
    function_name: str | None = None,
    address: str | None = None,
    direction: str = "to",
    limit: int = 100,
    session_id: str | None = None,
) -> dict[str, Any]:
    """获取交叉引用。

    Args:
        program_id: import_binary 返回的 program_id。
        function_name: 可选。目标函数名。
        address: 可选。目标地址。
        direction: to / from / both。
        limit: 返回数量上限。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.get_xrefs(
            program_id=program_id,
            function_name=function_name,
            address=address,
            direction=direction,
            limit=limit,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("get_xrefs", error)


@mcp.tool(
    name="disassemble",
    description="按函数或地址输出原始反汇编指令、字节和流向信息。",
    structured_output=True,
)
def disassemble(
    program_id: str,
    function_name: str | None = None,
    address: str | None = None,
    max_instructions: int = 80,
    session_id: str | None = None,
) -> dict[str, Any]:
    """获取反汇编。

    Args:
        program_id: import_binary 返回的 program_id。
        function_name: 可选。目标函数名。
        address: 可选。起始地址或函数入口地址。
        max_instructions: 返回的最大指令数。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.disassemble(
            program_id=program_id,
            function_name=function_name,
            address=address,
            max_instructions=max_instructions,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("disassemble", error)


@mcp.tool(
    name="get_call_graph",
    description="获取单个函数的一阶调用图，包括调用者和被调用函数。",
    structured_output=True,
)
def get_call_graph(
    program_id: str,
    function_name: str | None = None,
    address: str | None = None,
    limit: int = 100,
    session_id: str | None = None,
) -> dict[str, Any]:
    """获取函数调用图。

    Args:
        program_id: import_binary 返回的 program_id。
        function_name: 可选。目标函数名。
        address: 可选。目标函数入口地址。
        limit: incoming / outgoing 的返回数量上限。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.get_call_graph(
            program_id=program_id,
            function_name=function_name,
            address=address,
            limit=limit,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("get_call_graph", error)


@mcp.tool(
    name="list_import_exports",
    description="获取导入符号与导出/命名入口概览，便于快速看 IAT/EAT 风格信息。",
    structured_output=True,
)
def list_import_exports(
    program_id: str,
    query: str | None = None,
    limit: int = 200,
    session_id: str | None = None,
) -> dict[str, Any]:
    """获取导入导出概览。

    Args:
        program_id: import_binary 返回的 program_id。
        query: 可选。按名称过滤。
        limit: imports / exports 的返回数量上限。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.list_import_exports(
            program_id=program_id,
            query=query,
            limit=limit,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("list_import_exports", error)


@mcp.tool(
    name="list_data_types",
    description="列出程序数据类型、结构体、联合体、枚举和 typedef，可选展开成员。",
    structured_output=True,
)
def list_data_types(
    program_id: str,
    query: str | None = None,
    kind: str | None = None,
    limit: int = 100,
    include_members: bool = False,
    session_id: str | None = None,
) -> dict[str, Any]:
    """获取数据类型信息。

    Args:
        program_id: import_binary 返回的 program_id。
        query: 可选。按名称或路径过滤。
        kind: 可选。structure / union / enum / typedef / function_definition / pointer / other。
        limit: 返回数量上限。
        include_members: 是否展开结构体成员或枚举值。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.list_data_types(
            program_id=program_id,
            query=query,
            kind=kind,
            limit=limit,
            include_members=include_members,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("list_data_types", error)


@mcp.tool(
    name="read_memory",
    description="按地址读取原始字节并返回 hex / ascii 视图。",
    structured_output=True,
)
def read_memory(
    program_id: str,
    address: str,
    length: int = 128,
    row_width: int = 16,
    session_id: str | None = None,
) -> dict[str, Any]:
    """读取内存。

    Args:
        program_id: import_binary 返回的 program_id。
        address: 起始地址。
        length: 读取字节数。
        row_width: hex 视图每行字节数。
        session_id: 可选。分析会话 ID。
    """

    try:
        return service.read_memory(
            program_id=program_id,
            address=address,
            length=length,
            row_width=row_width,
            session_id=session_id,
        )
    except GhidraRuntimeError as error:
        _raise_tool_error("read_memory", error)


def main() -> int:
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
