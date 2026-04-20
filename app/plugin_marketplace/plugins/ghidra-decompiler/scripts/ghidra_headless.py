#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from glob import glob
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

GHIDRA_VERSION = "12.0.4"
GHIDRA_RELEASE_DATE = "20260303"
GHIDRA_RELEASE_TAG = "Ghidra_12.0.4_build"
GHIDRA_ZIP_NAME = "ghidra_12.0.4_PUBLIC_20260303.zip"
GHIDRA_ZIP_SHA256 = "c3b458661d69e26e203d739c0c82d143cc8a4a29d9e571f099c2cf4bda62a120"

PROGRAM_REGISTRY_FILENAME = "registry.json"
DEFAULT_PROJECT_NAME = "project"
JAVA_HOME_ENV = "GHIDRA_JAVA_HOME"
GHIDRA_INSTALL_DIR_ENV = "GHIDRA_INSTALL_DIR"
WORKSPACE_ROOT_ENV = "GHIDRA_WORKSPACE_ROOT"
REQUIRED_JAVA_MAJOR = 21
JAVA_ENV_CANDIDATES = (JAVA_HOME_ENV, "JAVA_HOME")
ANALYZE_HEADLESS_ENTRY_RELATIVE = Path("support") / "analyzeHeadless"
AUTO_DETECT_GHIDRA_GLOBS = (
    "/opt/ghidra*",
    "/opt/Ghidra*",
    "/usr/local/ghidra*",
    "/usr/local/share/ghidra*",
    "~/.local/share/ghidra*",
    "~/tools/ghidra*",
    "~/ghidra*",
)


class GhidraRuntimeError(RuntimeError):
    """Raised when local Ghidra/JDK runtime requirements are not satisfied."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "runtime_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "error": str(self),
            "error_code": self.error_code,
        }
        payload.update(self.details)
        return payload


@dataclass(frozen=True)
class ProgramRecord:
    program_id: str
    binary_path: str
    binary_name: str
    sha256: str
    project_dir: str
    project_name: str
    program_name: str
    ghidra_version: str
    executable_format: str | None = None
    language_id: str | None = None
    compiler_spec_id: str | None = None
    image_base: str | None = None
    function_count: int | None = None
    created_at_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "binary_path": self.binary_path,
            "binary_name": self.binary_name,
            "sha256": self.sha256,
            "project_dir": self.project_dir,
            "project_name": self.project_name,
            "program_name": self.program_name,
            "ghidra_version": self.ghidra_version,
            "executable_format": self.executable_format,
            "language_id": self.language_id,
            "compiler_spec_id": self.compiler_spec_id,
            "image_base": self.image_base,
            "function_count": self.function_count,
            "created_at_utc": self.created_at_utc,
        }


SUMMARY_RECORD_KEYS = (
    "entry_point",
    "entry_point_candidates",
    "main_candidates",
    "suggested_start_functions",
    "external_startup_candidates",
    "internal_function_count",
    "external_function_count",
    "thunk_function_count",
    "analysis_hints",
)


def plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _analyze_headless_from_install_candidate(install_candidate: Path) -> Path:
    if install_candidate.name == "analyzeHeadless":
        return install_candidate
    return install_candidate / ANALYZE_HEADLESS_ENTRY_RELATIVE


def _discover_ghidra_candidates() -> list[Path]:
    candidates: list[Path] = []
    which_headless = shutil.which("analyzeHeadless")
    if which_headless:
        candidates.append(Path(which_headless).expanduser().resolve())

    for pattern in AUTO_DETECT_GHIDRA_GLOBS:
        for matched in glob(os.path.expanduser(pattern)):
            candidates.append(Path(matched).expanduser().resolve())

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def analyze_headless_path() -> Path:
    return ensure_runtime_available()


def ghidra_script_dir() -> Path:
    return plugin_root() / "scripts" / "ghidra_scripts"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_compact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_env_value(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    value = raw_value.strip()
    if not value or (value.startswith("{{") and value.endswith("}}")):
        return None
    return value


def _java_requirement_details() -> dict[str, Any]:
    return {
        "needs_jdk": True,
        "required_jdk_major": REQUIRED_JAVA_MAJOR,
        "ghidra_version": GHIDRA_VERSION,
        "java_home_env_vars": list(JAVA_ENV_CANDIDATES),
        "java_path_fallback": "PATH",
    }


def _ghidra_requirement_details(checked_candidates: list[str]) -> dict[str, Any]:
    return {
        "needs_ghidra_install": True,
        "ghidra_install_env_var": GHIDRA_INSTALL_DIR_ENV,
        "required_entry_relative_path": str(ANALYZE_HEADLESS_ENTRY_RELATIVE),
        "checked_candidates": checked_candidates,
        "auto_detect_globs": list(AUTO_DETECT_GHIDRA_GLOBS),
    }


def workspace_root() -> Path:
    configured = _normalize_env_value(os.environ.get(WORKSPACE_ROOT_ENV))
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".cache" / "pandoraq-ghidra-decompiler").resolve()


def registry_path() -> Path:
    return workspace_root() / PROGRAM_REGISTRY_FILENAME


def _load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.exists():
        return {"programs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_registry(registry: dict[str, Any]) -> None:
    root = workspace_root()
    root.mkdir(parents=True, exist_ok=True)
    registry_path().write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _find_java_executable() -> tuple[str, dict[str, str]]:
    env = dict(os.environ)

    for env_name in JAVA_ENV_CANDIDATES:
        configured = _normalize_env_value(os.environ.get(env_name))
        if not configured:
            continue
        java_home = Path(configured).expanduser().resolve()
        candidate = java_home / "bin" / "java"
        if candidate.exists():
            env["JAVA_HOME"] = str(java_home)
            env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
            return str(candidate), env

    which_java = shutil.which("java")
    if which_java:
        return which_java, env

    raise GhidraRuntimeError(
        "当前环境缺少 JDK 21。请安装 JDK 21+，并配置 GHIDRA_JAVA_HOME / JAVA_HOME，"
        "或保证 PATH 中存在可用的 java。",
        error_code="missing_jdk",
        details=_java_requirement_details(),
    )


def ensure_java_available() -> dict[str, Any]:
    java_executable, env = _find_java_executable()
    completed = subprocess.run(
        [java_executable, "-version"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    combined = (completed.stderr or "") + "\n" + (completed.stdout or "")
    version_match = re.search(r'version "([^"]+)"', combined)
    major = None
    if version_match:
        raw_version = version_match.group(1)
        if raw_version.startswith("1."):
            try:
                major = int(raw_version.split(".")[1])
            except (IndexError, ValueError):
                major = None
        else:
            major_match = re.match(r"(\d+)", raw_version)
            if major_match:
                major = int(major_match.group(1))

    if completed.returncode != 0:
        raise GhidraRuntimeError(
            "检测到 java 命令，但执行 `java -version` 失败。",
            error_code="broken_jdk",
            details={
                **_java_requirement_details(),
                "java_executable": java_executable,
                "version_output": combined.strip(),
            },
        )
    if major is None or major < REQUIRED_JAVA_MAJOR:
        raise GhidraRuntimeError(
            "Ghidra 12.0.4 需要 JDK 21 或更高版本。当前检测到的版本输出为: "
            + combined.strip(),
            error_code="unsupported_jdk",
            details={
                **_java_requirement_details(),
                "java_executable": java_executable,
                "detected_java_major_version": major,
                "version_output": combined.strip(),
            },
        )

    return {
        "java_executable": java_executable,
        "java_major_version": major,
        "env": env,
        "version_output": combined.strip(),
    }


def ensure_runtime_available() -> Path:
    configured_install = _normalize_env_value(os.environ.get(GHIDRA_INSTALL_DIR_ENV))
    checked_candidates: list[str] = []

    if configured_install:
        install_candidate = Path(configured_install).expanduser().resolve()
        checked_candidates.append(str(install_candidate))
        headless_entry = _analyze_headless_from_install_candidate(install_candidate)
        if headless_entry.exists() and headless_entry.is_file():
            return headless_entry

        raise GhidraRuntimeError(
            "未找到可用的 analyzeHeadless。请将 GHIDRA_INSTALL_DIR 指向 Ghidra 安装目录，"
            "或直接指向 support/analyzeHeadless。",
            error_code="missing_ghidra_install",
            details={
                **_ghidra_requirement_details(checked_candidates),
                "configured_ghidra_install_dir": str(install_candidate),
            },
        )

    discovered = _discover_ghidra_candidates()
    checked_candidates.extend(str(item) for item in discovered)
    for install_candidate in discovered:
        headless_entry = _analyze_headless_from_install_candidate(install_candidate)
        if headless_entry.exists() and headless_entry.is_file():
            return headless_entry

    raise GhidraRuntimeError(
        "当前环境未发现可用 Ghidra 安装。请配置 GHIDRA_INSTALL_DIR，"
        "并确保存在 support/analyzeHeadless。",
        error_code="missing_ghidra_install",
        details={
            **_ghidra_requirement_details(checked_candidates),
            "ghidra_version": GHIDRA_VERSION,
            "ghidra_release_tag": GHIDRA_RELEASE_TAG,
            "ghidra_zip_name": GHIDRA_ZIP_NAME,
            "ghidra_zip_sha256": GHIDRA_ZIP_SHA256,
        },
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _program_id_for(binary_path: Path, sha256_value: str) -> str:
    return "ghidra-" + sha256_value[:12]


def _load_program_record(program_id: str) -> dict[str, Any]:
    registry = _load_registry()
    program = registry.get("programs", {}).get(program_id)
    if not program:
        raise GhidraRuntimeError(
            "找不到 program_id={0}。请先调用 import_binary。".format(program_id)
        )
    return program


def _write_temp_json(temp_dir: Path, filename: str, payload: dict[str, Any]) -> Path:
    path = temp_dir / filename
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _slugify_filename_component(value: str, *, fallback: str, max_length: int = 40) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        return fallback
    return normalized[:max_length].rstrip("-") or fallback


def _strings_artifact_path(program_id: str, query: str, min_length: int) -> Path:
    artifact_root = workspace_root() / "artifacts" / program_id / "strings"
    artifact_root.mkdir(parents=True, exist_ok=True)
    query_component = _slugify_filename_component(query, fallback="all")
    filename = "strings-{0}-min{1}-{2}.jsonl".format(
        query_component,
        min_length,
        _utc_compact_timestamp(),
    )
    return artifact_root / filename


def _run_headless(project_dir: Path, project_name: str, extra_args: list[str]) -> subprocess.CompletedProcess[str]:
    headless_entry = ensure_runtime_available()
    java_info = ensure_java_available()

    command = [str(headless_entry), str(project_dir), project_name] + extra_args
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=java_info["env"],
        cwd=str(plugin_root()),
    )
    if completed.returncode != 0:
        stderr_text = (completed.stderr or "").strip()
        stdout_text = (completed.stdout or "").strip()
        preview_parts = []
        if stderr_text:
            preview_parts.append("stderr: " + "\n".join(stderr_text.splitlines()[-20:]))
        if stdout_text:
            preview_parts.append("stdout: " + "\n".join(stdout_text.splitlines()[-20:]))
        preview = "\n\n".join(preview_parts) if preview_parts else "无额外输出"
        combined_output = "\n".join([stderr_text, stdout_text]).lower()
        if "lockexception" in combined_output or "unable to lock project" in combined_output:
            raise GhidraRuntimeError(
                "当前 Ghidra project 被占用，无法获取锁。请稍后重试。",
                error_code="project_locked",
                details={
                    "project_dir": str(project_dir),
                    "project_name": project_name,
                    "analyze_headless": str(headless_entry),
                },
            )
        raise GhidraRuntimeError(
            "analyzeHeadless 执行失败，命令为: {0}\n{1}".format(
                " ".join(command),
                preview,
            )
        )
    return completed


def import_binary(binary_path: str, force_reimport: bool = False) -> dict[str, Any]:
    binary = Path(binary_path).expanduser().resolve()
    if not binary.exists() or not binary.is_file():
        raise GhidraRuntimeError("样本不存在或不是普通文件: {0}".format(binary))

    ensure_runtime_available()
    java_info = ensure_java_available()
    root = workspace_root()
    root.mkdir(parents=True, exist_ok=True)

    sha256_value = _sha256_file(binary)
    program_id = _program_id_for(binary, sha256_value)
    project_dir = root / "projects" / program_id

    registry = _load_registry()
    existing = registry.get("programs", {}).get(program_id)
    if existing and not force_reimport:
        existing = dict(existing)
        existing_project_dir = Path(existing["project_dir"])
        if existing_project_dir.exists():
            summary = _export_program_summary(
                existing_project_dir,
                existing.get("project_name") or DEFAULT_PROJECT_NAME,
                existing.get("program_name") or existing["binary_name"],
                program_id=program_id,
                binary_path=str(binary),
                sha256_value=sha256_value,
            )
            existing.update(_summary_fields_from_summary(summary))
            registry.setdefault("programs", {})[program_id] = existing
            _save_registry(registry)
        existing["workspace_root"] = str(root)
        existing["java_major_version"] = java_info["java_major_version"]
        existing["ghidra_release_tag"] = GHIDRA_RELEASE_TAG
        existing["ghidra_zip_name"] = GHIDRA_ZIP_NAME
        existing["ghidra_zip_sha256"] = GHIDRA_ZIP_SHA256
        return existing

    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=str(root)) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        output_path = temp_dir / "import_result.json"
        request_path = _write_temp_json(
            temp_dir,
            "import_request.json",
            {
                "program_id": program_id,
                "binary_path": str(binary),
                "sha256": sha256_value,
            },
        )
        _run_headless(
            project_dir,
            DEFAULT_PROJECT_NAME,
            [
                "-import",
                str(binary),
                "-overwrite",
                "-scriptPath",
                str(ghidra_script_dir()),
                "-postScript",
                "export_program_summary.py",
                str(output_path),
                str(request_path),
            ],
        )
        summary = json.loads(output_path.read_text(encoding="utf-8"))

    record = ProgramRecord(
        program_id=program_id,
        binary_path=str(binary),
        binary_name=binary.name,
        sha256=sha256_value,
        project_dir=str(project_dir),
        project_name=DEFAULT_PROJECT_NAME,
        program_name=summary.get("program_name") or binary.name,
        ghidra_version=GHIDRA_VERSION,
        executable_format=summary.get("executable_format"),
        language_id=summary.get("language_id"),
        compiler_spec_id=summary.get("compiler_spec_id"),
        image_base=summary.get("image_base"),
        function_count=summary.get("function_count"),
        created_at_utc=_utc_now(),
    )

    stored_record = record.to_dict()
    stored_record.update(_summary_fields_from_summary(summary))
    registry.setdefault("programs", {})[program_id] = stored_record
    _save_registry(registry)

    result = dict(stored_record)
    result["workspace_root"] = str(root)
    result["java_major_version"] = java_info["java_major_version"]
    result["ghidra_release_tag"] = GHIDRA_RELEASE_TAG
    result["ghidra_zip_name"] = GHIDRA_ZIP_NAME
    result["ghidra_zip_sha256"] = GHIDRA_ZIP_SHA256
    return result


def _run_program_script(program_id: str, script_name: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    program = _load_program_record(program_id)
    project_dir = Path(program["project_dir"])
    project_name = program["project_name"]
    process_name = program.get("program_name") or program["binary_name"]

    if not project_dir.exists():
        raise GhidraRuntimeError(
            "program_id={0} 对应的 Ghidra project 目录不存在: {1}".format(
                program_id,
                project_dir,
            )
        )

    root = workspace_root()
    root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=str(root)) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        output_path = temp_dir / "result.json"
        request_path = _write_temp_json(temp_dir, "request.json", request_payload)
        _run_headless(
            project_dir,
            project_name,
            [
                "-process",
                process_name,
                "-scriptPath",
                str(ghidra_script_dir()),
                "-postScript",
                script_name,
                str(output_path),
                str(request_path),
            ],
        )
        return json.loads(output_path.read_text(encoding="utf-8"))


def _export_program_summary(
    project_dir: Path,
    project_name: str,
    process_name: str,
    *,
    program_id: str,
    binary_path: str,
    sha256_value: str,
) -> dict[str, Any]:
    root = workspace_root()
    root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=str(root)) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        output_path = temp_dir / "import_result.json"
        request_path = _write_temp_json(
            temp_dir,
            "import_request.json",
            {
                "program_id": program_id,
                "binary_path": binary_path,
                "sha256": sha256_value,
            },
        )
        _run_headless(
            project_dir,
            project_name,
            [
                "-process",
                process_name,
                "-scriptPath",
                str(ghidra_script_dir()),
                "-postScript",
                "export_program_summary.py",
                str(output_path),
                str(request_path),
            ],
        )
        return json.loads(output_path.read_text(encoding="utf-8"))


def _summary_fields_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: summary.get(key) for key in SUMMARY_RECORD_KEYS if key in summary}


def _raise_script_result_error(tool_name: str, result: dict[str, Any], *, default_message: str) -> None:
    if result.get("success", True):
        return

    error_code = result.get("error_code") or "script_error"
    error_message = result.get("error_message") or default_message
    details = {}
    for key, value in result.items():
        if key in ("success", "error_code", "error_message"):
            continue
        if value is not None:
            details[key] = value

    raise GhidraRuntimeError(
        "{0}\nreason: {1}".format(default_message, error_message),
        error_code=error_code,
        details=details,
    )


def get_program_metadata(program_id: str) -> dict[str, Any]:
    program = _load_program_record(program_id)
    project_dir = Path(program["project_dir"])
    if not project_dir.exists():
        raise GhidraRuntimeError(
            "program_id={0} 对应的 Ghidra project 目录不存在: {1}".format(
                program_id,
                project_dir,
            )
        )

    summary = _export_program_summary(
        project_dir,
        program.get("project_name") or DEFAULT_PROJECT_NAME,
        program.get("program_name") or program["binary_name"],
        program_id=program_id,
        binary_path=program["binary_path"],
        sha256_value=program["sha256"],
    )
    result = dict(program)
    result.update(_summary_fields_from_summary(summary))
    result["success"] = True
    return result


def list_functions(program_id: str, query: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    return _run_program_script(
        program_id,
        "list_functions.py",
        {
            "program_id": program_id,
            "query": query or "",
            "limit": max(1, min(int(limit), 1000)),
            "offset": max(0, int(offset)),
        },
    )


def decompile_function(
    program_id: str,
    function_name: str | None = None,
    address: str | None = None,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    if not function_name and not address:
        raise GhidraRuntimeError("decompile_function 至少需要 function_name 或 address 其中一个参数。")
    normalized_timeout = max(1, min(int(timeout_seconds), 300))
    result = _run_program_script(
        program_id,
        "decompile_function.py",
        {
            "program_id": program_id,
            "function_name": function_name or "",
            "address": address or "",
            "timeout_seconds": normalized_timeout,
        },
    )
    if result.get("success", True):
        return result

    requested_function_name = function_name or ""
    requested_address = address or ""
    error_code = result.get("error_code") or "decompile_failed"
    error_message = result.get("error_message") or "反编译失败。"
    resolved_function = result.get("resolved_function")

    message_lines = ["函数反编译失败。", "reason: {0}".format(error_message)]
    if requested_address:
        message_lines.append("requested_address: {0}".format(requested_address))
    if requested_function_name:
        message_lines.append("requested_function_name: {0}".format(requested_function_name))
    if resolved_function:
        message_lines.append(
            "resolved_function: {0} @ {1}".format(
                resolved_function.get("full_name") or resolved_function.get("name") or "unknown",
                resolved_function.get("entry_point") or "unknown",
            )
        )
    if result.get("resolved_by"):
        message_lines.append("resolved_by: {0}".format(result.get("resolved_by")))

    details = {
        "program_id": program_id,
        "requested_address": requested_address,
        "requested_function_name": requested_function_name,
        "timeout_seconds": normalized_timeout,
    }
    for key in (
        "resolved_by",
        "resolved_function",
        "decompile_status",
        "exception_type",
        "candidates",
        "candidate_count",
    ):
        value = result.get(key)
        if value is not None:
            details[key] = value

    raise GhidraRuntimeError(
        "\n".join(message_lines),
        error_code=error_code,
        details=details,
    )


def export_strings(
    program_id: str,
    min_length: int = 4,
    limit: int = 50,
    offset: int = 0,
    query: str | None = None,
    save_to_file: bool = True,
) -> dict[str, Any]:
    normalized_query = (query or "").strip()
    artifact_path = None
    if save_to_file:
        artifact_path = _strings_artifact_path(
            program_id,
            normalized_query,
            max(1, min(int(min_length), 64)),
        )
    return _run_program_script(
        program_id,
        "export_strings.py",
        {
            "program_id": program_id,
            "min_length": max(1, min(int(min_length), 64)),
            "limit": max(1, min(int(limit), 1000)),
            "offset": max(0, int(offset)),
            "query": normalized_query,
            "save_to_file": bool(save_to_file),
            "artifact_output_path": str(artifact_path) if artifact_path else "",
        },
    )


def search_symbol(program_id: str, query: str, limit: int = 50) -> dict[str, Any]:
    normalized_query = (query or "").strip()
    if not normalized_query:
        raise GhidraRuntimeError("search_symbol 需要非空的 query。")
    return _run_program_script(
        program_id,
        "search_symbol.py",
        {
            "program_id": program_id,
            "query": normalized_query,
            "limit": max(1, min(int(limit), 1000)),
        },
    )


def list_segments(program_id: str, limit: int = 200) -> dict[str, Any]:
    result = _run_program_script(
        program_id,
        "list_segments.py",
        {
            "program_id": program_id,
            "limit": max(1, min(int(limit), 2000)),
        },
    )
    _raise_script_result_error("list_segments", result, default_message="列出内存段失败。")
    return result


def get_xrefs(
    program_id: str,
    function_name: str | None = None,
    address: str | None = None,
    direction: str = "to",
    limit: int = 100,
) -> dict[str, Any]:
    if not function_name and not address:
        raise GhidraRuntimeError("get_xrefs 至少需要 function_name 或 address 其中一个参数。")

    normalized_direction = (direction or "to").strip().lower()
    if normalized_direction not in ("to", "from", "both"):
        raise GhidraRuntimeError(
            "direction 仅支持 to / from / both。",
            error_code="invalid_direction",
            details={"direction": direction},
        )

    result = _run_program_script(
        program_id,
        "get_xrefs.py",
        {
            "program_id": program_id,
            "function_name": function_name or "",
            "address": address or "",
            "direction": normalized_direction,
            "limit": max(1, min(int(limit), 1000)),
        },
    )
    _raise_script_result_error("get_xrefs", result, default_message="获取交叉引用失败。")
    return result


def disassemble(
    program_id: str,
    function_name: str | None = None,
    address: str | None = None,
    max_instructions: int = 80,
) -> dict[str, Any]:
    if not function_name and not address:
        raise GhidraRuntimeError("disassemble 至少需要 function_name 或 address 其中一个参数。")

    result = _run_program_script(
        program_id,
        "disassemble.py",
        {
            "program_id": program_id,
            "function_name": function_name or "",
            "address": address or "",
            "max_instructions": max(1, min(int(max_instructions), 1000)),
        },
    )
    _raise_script_result_error("disassemble", result, default_message="获取反汇编失败。")
    return result


def get_call_graph(
    program_id: str,
    function_name: str | None = None,
    address: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    if not function_name and not address:
        raise GhidraRuntimeError("get_call_graph 至少需要 function_name 或 address 其中一个参数。")

    result = _run_program_script(
        program_id,
        "get_call_graph.py",
        {
            "program_id": program_id,
            "function_name": function_name or "",
            "address": address or "",
            "limit": max(1, min(int(limit), 1000)),
        },
    )
    _raise_script_result_error("get_call_graph", result, default_message="获取函数调用图失败。")
    return result


def list_import_exports(program_id: str, query: str | None = None, limit: int = 200) -> dict[str, Any]:
    result = _run_program_script(
        program_id,
        "list_import_exports.py",
        {
            "program_id": program_id,
            "query": (query or "").strip(),
            "limit": max(1, min(int(limit), 2000)),
        },
    )
    _raise_script_result_error("list_import_exports", result, default_message="获取导入导出信息失败。")
    return result


def list_data_types(
    program_id: str,
    query: str | None = None,
    kind: str | None = None,
    limit: int = 100,
    include_members: bool = False,
) -> dict[str, Any]:
    result = _run_program_script(
        program_id,
        "list_data_types.py",
        {
            "program_id": program_id,
            "query": (query or "").strip(),
            "kind": (kind or "").strip(),
            "limit": max(1, min(int(limit), 1000)),
            "include_members": bool(include_members),
        },
    )
    _raise_script_result_error("list_data_types", result, default_message="获取数据类型信息失败。")
    return result


def read_memory(
    program_id: str,
    address: str,
    length: int = 128,
    row_width: int = 16,
) -> dict[str, Any]:
    normalized_address = (address or "").strip()
    if not normalized_address:
        raise GhidraRuntimeError("read_memory 需要非空的 address。")

    result = _run_program_script(
        program_id,
        "read_memory.py",
        {
            "program_id": program_id,
            "address": normalized_address,
            "length": max(1, min(int(length), 4096)),
            "row_width": max(1, min(int(row_width), 64)),
        },
    )
    _raise_script_result_error("read_memory", result, default_message="读取内存失败。")
    return result
