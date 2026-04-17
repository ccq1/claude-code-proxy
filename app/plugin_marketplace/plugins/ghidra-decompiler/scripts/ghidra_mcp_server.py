#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from ghidra_headless import (
    GhidraRuntimeError,
    decompile_function,
    export_strings,
    import_binary,
    list_functions,
    search_symbol,
)

SERVER_NAME = "ghidra-decompiler"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-03-26"


TOOL_DEFINITIONS = [
    {
        "name": "import_binary",
        "description": "导入本地二进制到 bundled Ghidra headless project，并返回后续分析所需的 program_id。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary_path": {
                    "type": "string",
                    "description": "本地 ELF/PE/Mach-O 样本路径。",
                },
                "force_reimport": {
                    "type": "boolean",
                    "description": "若为 true，则丢弃已有缓存并重新导入。",
                    "default": False,
                },
            },
            "required": ["binary_path"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    },
    {
        "name": "list_functions",
        "description": "列出当前样本的函数，可按名称做子串过滤。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string"},
                "query": {
                    "type": "string",
                    "description": "可选。按函数名做子串过滤。",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "required": ["program_id"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "decompile_function",
        "description": "按函数名或入口地址反编译单个函数。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string"},
                "function_name": {
                    "type": "string",
                    "description": "可选。精确函数名或主要名称。",
                },
                "address": {
                    "type": "string",
                    "description": "可选。函数入口地址，例如 00401230 或 0x00401230。",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 30,
                },
            },
            "required": ["program_id"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "export_strings",
        "description": "按分页和关键词预览当前样本中的已定义字符串，并可把筛选结果落到 artifact 文件，避免一次性把大量字符串塞进上下文。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string"},
                "min_length": {"type": "integer", "minimum": 1, "maximum": 64, "default": 4},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 50,
                    "description": "只返回当前页的预览数量，默认不超过 50 条。",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                    "description": "分页偏移量，用于分批查看字符串。",
                },
                "query": {
                    "type": "string",
                    "description": "可选。按字符串内容做大小写不敏感的子串过滤。",
                },
                "save_to_file": {
                    "type": "boolean",
                    "default": True,
                    "description": "默认为 true。把当前筛选结果保存为 workspace 中的 jsonl artifact 文件。",
                },
            },
            "required": ["program_id"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "search_symbol",
        "description": "按关键词搜索函数和其他符号，适合快速定位命名入口。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 50},
            },
            "required": ["program_id", "query"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
]


class MCPServer:
    def __init__(self) -> None:
        self._input = sys.stdin.buffer
        self._output = sys.stdout.buffer
        self._tool_handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "import_binary": self._tool_import_binary,
            "list_functions": self._tool_list_functions,
            "decompile_function": self._tool_decompile_function,
            "export_strings": self._tool_export_strings,
            "search_symbol": self._tool_search_symbol,
        }

    def serve_forever(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                return
            try:
                self._handle_message(message)
            except Exception as exc:  # pragma: no cover - best effort runtime guard
                request_id = message.get("id") if isinstance(message, dict) else None
                self._send_error(
                    request_id,
                    -32603,
                    "Internal server error",
                    {"detail": str(exc), "traceback": traceback.format_exc()},
                )

    def _read_message(self) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = self._input.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            decoded = line.decode("utf-8").strip()
            if not decoded:
                continue
            if ":" not in decoded:
                raise ValueError("Malformed MCP header: {0}".format(decoded))
            name, value = decoded.split(":", 1)
            headers[name.lower().strip()] = value.strip()

        content_length = int(headers["content-length"])
        payload = self._input.read(content_length)
        return json.loads(payload.decode("utf-8"))

    def _send_message(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        header = "Content-Length: {0}\r\n\r\n".format(len(body)).encode("ascii")
        self._output.write(header)
        self._output.write(body)
        self._output.flush()

    def _send_result(self, request_id: Any, result: dict[str, Any]) -> None:
        self._send_message({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _send_error(self, request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._send_message({"jsonrpc": "2.0", "id": request_id, "error": error})

    def _handle_message(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if not method:
            if request_id is not None:
                self._send_error(request_id, -32600, "Invalid request: missing method")
            return

        if request_id is None:
            if method == "notifications/initialized":
                return
            return

        if method == "initialize":
            self._send_result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
            return

        if method == "ping":
            self._send_result(request_id, {})
            return

        if method == "tools/list":
            self._send_result(request_id, {"tools": TOOL_DEFINITIONS})
            return

        if method == "resources/list":
            self._send_result(request_id, {"resources": []})
            return

        if method == "prompts/list":
            self._send_result(request_id, {"prompts": []})
            return

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            if tool_name not in self._tool_handlers:
                self._send_error(
                    request_id,
                    -32601,
                    "Unknown tool: {0}".format(tool_name),
                )
                return

            try:
                result = self._tool_handlers[tool_name](arguments)
                self._send_result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": self._summarize_tool_result(tool_name, result)}],
                        "structuredContent": result,
                        "isError": False,
                    },
                )
            except GhidraRuntimeError as exc:
                error_result = {"tool": tool_name, **exc.to_dict()}
                self._send_result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": self._summarize_tool_error(tool_name, exc)}],
                        "structuredContent": error_result,
                        "isError": True,
                    },
                )
            return

        self._send_error(request_id, -32601, "Method not found: {0}".format(method))

    def _tool_import_binary(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return import_binary(
            binary_path=str(arguments["binary_path"]),
            force_reimport=bool(arguments.get("force_reimport", False)),
        )

    def _tool_list_functions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return list_functions(
            program_id=str(arguments["program_id"]),
            query=arguments.get("query"),
            limit=int(arguments.get("limit", 100)),
            offset=int(arguments.get("offset", 0)),
        )

    def _tool_decompile_function(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return decompile_function(
            program_id=str(arguments["program_id"]),
            function_name=arguments.get("function_name"),
            address=arguments.get("address"),
            timeout_seconds=int(arguments.get("timeout_seconds", 30)),
        )

    def _tool_export_strings(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return export_strings(
            program_id=str(arguments["program_id"]),
            min_length=int(arguments.get("min_length", 4)),
            limit=int(arguments.get("limit", 50)),
            offset=int(arguments.get("offset", 0)),
            query=arguments.get("query"),
            save_to_file=bool(arguments.get("save_to_file", True)),
        )

    def _tool_search_symbol(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return search_symbol(
            program_id=str(arguments["program_id"]),
            query=str(arguments["query"]),
            limit=int(arguments.get("limit", 50)),
        )

    def _summarize_tool_result(self, tool_name: str, result: dict[str, Any]) -> str:
        if tool_name == "import_binary":
            return (
                "导入完成\n"
                "program_id: {0}\n"
                "program_name: {1}\n"
                "format: {2}\n"
                "language: {3}".format(
                    result.get("program_id", ""),
                    result.get("program_name", ""),
                    result.get("executable_format", ""),
                    result.get("language_id", ""),
                )
            )

        if tool_name == "list_functions":
            functions = result.get("functions", [])
            lines = ["共返回 {0} 个函数".format(len(functions))]
            for item in functions[:10]:
                lines.append("- {0} @ {1}".format(item.get("name", ""), item.get("entry_point", "")))
            if len(functions) > 10:
                lines.append("- ...")
            return "\n".join(lines)

        if tool_name == "search_symbol":
            matches = result.get("matches", [])
            lines = ["共命中 {0} 个符号".format(len(matches))]
            for item in matches[:10]:
                lines.append(
                    "- [{0}] {1} @ {2}".format(
                        item.get("kind", ""),
                        item.get("name", ""),
                        item.get("address", ""),
                    )
                )
            if len(matches) > 10:
                lines.append("- ...")
            return "\n".join(lines)

        if tool_name == "export_strings":
            strings = result.get("strings", [])
            lines = [
                "字符串预览: returned={0}, total_matches={1}, offset={2}, query={3}".format(
                    result.get("returned", len(strings)),
                    result.get("total_matches", len(strings)),
                    result.get("offset", 0),
                    repr(result.get("query", "")),
                )
            ]
            for item in strings[:10]:
                lines.append(
                    "- {0}: {1}".format(
                        item.get("address", ""),
                        item.get("value", ""),
                    )
                )
            if len(strings) > 10:
                lines.append("- ...")
            if result.get("artifact_path"):
                lines.append("artifact: {0}".format(result.get("artifact_path")))
            return "\n".join(lines)

        if tool_name == "decompile_function":
            header = "已反编译 {0} @ {1}".format(
                result.get("function", {}).get("name", ""),
                result.get("function", {}).get("entry_point", ""),
            )
            code = result.get("decompiled_c", "") or ""
            if not code:
                return header
            lines = code.splitlines()
            preview = "\n".join(lines[:40])
            if len(lines) > 40:
                preview += "\n..."
            return header + "\n\n" + preview

        return json.dumps(result, ensure_ascii=False, indent=2)

    def _summarize_tool_error(self, tool_name: str, error: GhidraRuntimeError) -> str:
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

        if error.error_code == "missing_runtime":
            return (
                "bundled Ghidra runtime 不完整，当前无法调用 analyzeHeadless。\n"
                "请确认插件随包携带了完整的官方 Ghidra runtime。\n"
                "tool: {0}".format(tool_name)
            )

        return str(error)


def main() -> int:
    server = MCPServer()
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
