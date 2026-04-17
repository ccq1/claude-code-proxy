#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
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
WORKSPACE_ROOT_ENV = "GHIDRA_WORKSPACE_ROOT"
REQUIRED_JAVA_MAJOR = 21
JAVA_ENV_CANDIDATES = (JAVA_HOME_ENV, "JAVA_HOME")


class GhidraRuntimeError(RuntimeError):
    """Raised when the bundled runtime or the local Java environment is unusable."""

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


def plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


def runtime_root() -> Path:
    return plugin_root() / "runtime" / "ghidra_12.0.4_PUBLIC"


def analyze_headless_path() -> Path:
    return runtime_root() / "support" / "analyzeHeadless"


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
    runtime = runtime_root()
    required_paths = [
        runtime,
        analyze_headless_path(),
        runtime / "LICENSE",
        runtime / "NOTICE",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise GhidraRuntimeError(
            "bundled Ghidra runtime 不完整，缺少: " + ", ".join(missing),
            error_code="missing_runtime",
            details={
                "ghidra_version": GHIDRA_VERSION,
                "ghidra_release_tag": GHIDRA_RELEASE_TAG,
                "ghidra_zip_name": GHIDRA_ZIP_NAME,
                "ghidra_zip_sha256": GHIDRA_ZIP_SHA256,
                "missing_paths": missing,
            },
        )
    return runtime


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
    ensure_runtime_available()
    java_info = ensure_java_available()

    command = [str(analyze_headless_path()), str(project_dir), project_name] + extra_args
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
        existing["workspace_root"] = str(root)
        existing["java_major_version"] = java_info["java_major_version"]
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

    registry.setdefault("programs", {})[program_id] = record.to_dict()
    _save_registry(registry)

    result = record.to_dict()
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
    return _run_program_script(
        program_id,
        "decompile_function.py",
        {
            "program_id": program_id,
            "function_name": function_name or "",
            "address": address or "",
            "timeout_seconds": max(1, min(int(timeout_seconds), 300)),
        },
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
