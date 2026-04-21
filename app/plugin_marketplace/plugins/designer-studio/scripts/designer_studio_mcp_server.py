#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

SERVER_NAME = "designer-studio"
SERVER_VERSION = "0.2.0"
PREVIEW_LIMIT = 25
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_TOOL_PATH = (
    PLUGIN_ROOT / "skills" / "designer-studio" / "scripts" / "frontend_offline_tool.py"
)


class DesignerStudioRuntimeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


def _load_frontend_tool() -> Any:
    spec = importlib.util.spec_from_file_location(
        "designer_studio_frontend_tool",
        FRONTEND_TOOL_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load frontend tool module: {FRONTEND_TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


frontend_tool = _load_frontend_tool()
mcp = FastMCP(SERVER_NAME)


def _preview(items: list[dict[str, Any]], limit: int = PREVIEW_LIMIT) -> list[dict[str, Any]]:
    return items[:limit]


class DesignerStudioService:
    def __init__(self) -> None:
        self.layout = frontend_tool.resolve_layout()

    @staticmethod
    def _coerce_env_value(raw_value: str | None) -> str | None:
        if not raw_value:
            return None
        value = raw_value.strip()
        if not value or (value.startswith("{{") and value.endswith("}}")):
            return None
        return value

    def _load_runtime(self) -> dict[str, Any]:
        runtime = dict(frontend_tool.load_runtime(self.layout))
        env_to_runtime_key = {
            "FRONTEND_DESIGN_LIBRARY_ROOT": "designLibraryRoot",
            "FRONTEND_ASSETS_ROOT": "frontendAssetsRoot",
            "FRONTEND_CSS_PACK": "preferredCssPack",
        }
        for env_key, runtime_key in env_to_runtime_key.items():
            value = self._coerce_env_value(os.environ.get(env_key))
            if value is not None:
                runtime[runtime_key] = value
        return runtime

    def server_info(self) -> dict[str, Any]:
        runtime = self._load_runtime()
        design_root = frontend_tool.resolve_design_root(self.layout, runtime)
        assets_root = frontend_tool.resolve_assets_root(runtime)
        preferred_css_pack = frontend_tool.resolve_preferred_css_pack(runtime)
        frameworks = frontend_tool.load_frameworks(self.layout)
        return {
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "plugin_root": str(PLUGIN_ROOT),
            "skill_root": str(self.layout.skill_root),
            "design_root": str(design_root),
            "bundled_design_root": str(frontend_tool.bundled_design_root(self.layout)),
            "assets_root": str(assets_root) if assets_root else None,
            "preferred_css_pack": preferred_css_pack,
            "frameworks": _preview(
                [
                    {
                        "name": rec["name"],
                        "kind": rec.get("kind"),
                        "version": rec.get("version"),
                        "entry": rec.get("entry"),
                    }
                    for rec in frameworks
                ]
            ),
            "framework_count": len(frameworks),
        }

    def rebuild_index(self) -> dict[str, Any]:
        runtime = self._load_runtime()
        payload = frontend_tool.build_index(self.layout, runtime)
        design_root = frontend_tool.resolve_design_root(self.layout, runtime)
        bundled_root = frontend_tool.bundled_design_root(self.layout)
        persisted_path = None
        if design_root == bundled_root:
            persisted_path = str(frontend_tool.save_index(self.layout, payload))
        return {
            "action": "rebuild-index",
            "design_root": str(design_root),
            "bundled_design_root": str(bundled_root),
            "persisted_index_path": persisted_path,
            "persisted": persisted_path is not None,
            "total": payload.get("total", 0),
            "presets": _preview(payload.get("records", [])),
        }

    def list_presets(self, limit: int = PREVIEW_LIMIT) -> dict[str, Any]:
        runtime = self._load_runtime()
        payload = frontend_tool.load_or_build_index(self.layout, runtime)
        normalized_limit = max(1, min(int(limit or PREVIEW_LIMIT), 500))
        return {
            "action": "list-presets",
            "total": payload.get("total", 0),
            "design_root": payload.get("design_root"),
            "presets": _preview(payload.get("records", []), normalized_limit),
        }

    def search_design(self, query: str, limit: int = 10) -> dict[str, Any]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise DesignerStudioRuntimeError(
                "query 不能为空。",
                error_code="invalid_query",
            )
        runtime = self._load_runtime()
        payload = frontend_tool.load_or_build_index(self.layout, runtime)
        tokens = [item.strip().lower() for item in normalized_query.split() if item.strip()]
        matches: list[dict[str, Any]] = []
        for record in payload.get("records", []):
            score = frontend_tool.score_record(record, tokens)
            if score <= 0:
                continue
            matches.append(
                {
                    "score": score,
                    "slug": record.get("slug"),
                    "title": record.get("title"),
                    "tags": record.get("tags", []),
                    "design_md": record.get("design_md"),
                }
            )
        matches.sort(key=lambda item: (-item["score"], str(item["slug"])))
        normalized_limit = max(1, min(int(limit or 10), 100))
        return {
            "action": "search-design",
            "query": normalized_query,
            "match_count": len(matches),
            "matches": _preview(matches, normalized_limit),
        }

    def inspect_design(self, slug: str) -> dict[str, Any]:
        normalized_slug = (slug or "").strip()
        if not normalized_slug:
            raise DesignerStudioRuntimeError(
                "slug 不能为空。",
                error_code="invalid_slug",
            )
        runtime = self._load_runtime()
        payload = frontend_tool.load_or_build_index(self.layout, runtime)
        record = next(
            (item for item in payload.get("records", []) if item.get("slug") == normalized_slug),
            None,
        )
        if record is None:
            raise DesignerStudioRuntimeError(
                f"design slug not found: {normalized_slug}",
                error_code="design_not_found",
                details={"slug": normalized_slug},
            )
        design_path = Path(str(record["design_md"]))
        text = design_path.read_text(encoding="utf-8", errors="replace")
        section_headings = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("## ")
        ][:8]
        excerpt_lines = [
            line.rstrip()
            for line in text.splitlines()
            if line.strip()
        ][:20]
        return {
            "action": "inspect-design",
            "slug": record.get("slug"),
            "title": record.get("title"),
            "tags": record.get("tags", []),
            "design_md": str(design_path),
            "section_headings": section_headings,
            "excerpt": "\n".join(excerpt_lines),
        }

    def inventory_assets(self, root: str | None = None, limit: int = 5) -> dict[str, Any]:
        runtime = self._load_runtime()
        runtime_root = frontend_tool.resolve_assets_root(runtime)
        if root and root.strip():
            assets_root = Path(root).expanduser().resolve()
        else:
            assets_root = runtime_root
        if assets_root is None:
            raise DesignerStudioRuntimeError(
                "assets root not provided. use root or configure frontendAssetsRoot.",
                error_code="missing_assets_root",
            )
        if not assets_root.exists():
            raise DesignerStudioRuntimeError(
                f"assets root not found: {assets_root}",
                error_code="assets_root_not_found",
                details={"root": str(assets_root)},
            )
        if not assets_root.is_dir():
            raise DesignerStudioRuntimeError(
                f"assets root is not a directory: {assets_root}",
                error_code="invalid_assets_root",
                details={"root": str(assets_root)},
            )
        normalized_limit = max(1, min(int(limit or 5), 50))
        counters = {key: 0 for key in frontend_tool.ASSET_EXT_GROUPS}
        sample = {key: [] for key in frontend_tool.ASSET_EXT_GROUPS}
        other_count = 0
        for path in frontend_tool.walk_assets(assets_root):
            suffix = path.suffix.lower()
            group = None
            for key, exts in frontend_tool.ASSET_EXT_GROUPS.items():
                if suffix in exts:
                    group = key
                    break
            if group is None:
                other_count += 1
                continue
            counters[group] += 1
            if len(sample[group]) < normalized_limit:
                sample[group].append(str(path))
        return {
            "action": "inventory-assets",
            "asset_root": str(assets_root),
            "counts": counters,
            "samples": sample,
            "other_files": other_count,
        }

    def list_frameworks(self) -> dict[str, Any]:
        runtime = self._load_runtime()
        try:
            active_framework, fallback_note = frontend_tool.select_framework(self.layout, runtime)
        except ValueError as exc:
            raise DesignerStudioRuntimeError(
                str(exc),
                error_code="invalid_framework_config",
            ) from exc
        frameworks: list[dict[str, Any]] = []
        for framework in frontend_tool.load_frameworks(self.layout):
            source = frontend_tool.resolve_framework_source(self.layout, framework)
            frameworks.append(
                {
                    "name": framework["name"],
                    "kind": framework.get("kind", "css"),
                    "version": framework.get("version"),
                    "notes": framework.get("notes", ""),
                    "source_path": str(source),
                    "available": source.exists(),
                    "preferred": framework["name"] == active_framework["name"],
                }
            )
        return {
            "action": "list-frameworks",
            "preferred_css_pack": frontend_tool.resolve_preferred_css_pack(runtime),
            "active_framework": active_framework["name"],
            "fallback_note": fallback_note,
            "frameworks": frameworks,
        }

    def install_framework(
        self,
        output_dir: str,
        framework: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        normalized_output_dir = (output_dir or "").strip()
        if not normalized_output_dir:
            raise DesignerStudioRuntimeError(
                "output_dir 不能为空。",
                error_code="invalid_output_dir",
            )
        runtime = self._load_runtime()
        try:
            selected_framework, fallback_note = frontend_tool.select_framework(
                self.layout,
                runtime,
                requested_name=framework or None,
            )
            source = frontend_tool.resolve_framework_source(self.layout, selected_framework)
            safe_filename = frontend_tool.sanitize_output_filename(
                filename or source.name,
                source.name,
            )
        except ValueError as exc:
            raise DesignerStudioRuntimeError(
                str(exc),
                error_code="invalid_framework_request",
            ) from exc
        if not source.exists():
            raise DesignerStudioRuntimeError(
                f"framework package not found: {source}",
                error_code="framework_package_not_found",
                details={"source_path": str(source)},
            )
        target_dir = Path(normalized_output_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = (target_dir / safe_filename).resolve()
        shutil.copy2(source, target_path)
        return {
            "action": "install-framework",
            "framework": selected_framework["name"],
            "source_path": str(source),
            "target_path": str(target_path),
            "fallback_note": fallback_note,
        }

    def install_tailwind(
        self,
        output_dir: str,
        filename: str = "tailwind.min.css",
    ) -> dict[str, Any]:
        return self.install_framework(
            output_dir=output_dir,
            framework="tailwindcss",
            filename=filename,
        )


service = DesignerStudioService()


def _handle_runtime_error(exc: DesignerStudioRuntimeError) -> None:
    raise ToolError(
        f"{exc} | error_code={exc.error_code} | details={exc.details}"
    ) from exc


def _run(callback: Any) -> Any:
    try:
        return callback()
    except DesignerStudioRuntimeError as exc:
        _handle_runtime_error(exc)


@mcp.tool()
def server_info() -> dict[str, Any]:
    """返回 Designer Studio MCP server 的版本、设计库和框架配置概览。"""
    return _run(service.server_info)


@mcp.tool()
def rebuild_index() -> dict[str, Any]:
    """重建设计样本索引；若使用内置样本库，会同步更新 bundled design_index.json。"""
    return _run(service.rebuild_index)


@mcp.tool()
def list_presets(limit: int = PREVIEW_LIMIT) -> dict[str, Any]:
    """列出可用设计样本预览，返回 slug、标题、标签和 DESIGN.md 路径。"""
    return _run(lambda: service.list_presets(limit=limit))


@mcp.tool()
def search_design(query: str, limit: int = 10) -> dict[str, Any]:
    """按关键词检索设计样本，适合根据行业、页面类型或风格偏好筛选 preset。"""
    return _run(lambda: service.search_design(query=query, limit=limit))


@mcp.tool()
def inspect_design(slug: str) -> dict[str, Any]:
    """查看某个设计样本的 DESIGN.md 路径、章节标题和摘要片段。"""
    return _run(lambda: service.inspect_design(slug=slug))


@mcp.tool()
def inventory_assets(root: str | None = None, limit: int = 5) -> dict[str, Any]:
    """盘点本地前端资产目录，统计字体、图标、图片、样式和脚本资源。"""
    return _run(lambda: service.inventory_assets(root=root, limit=limit))


@mcp.tool()
def list_frameworks() -> dict[str, Any]:
    """列出内置离线框架包、默认偏好和每个框架的可用状态。"""
    return _run(service.list_frameworks)


@mcp.tool()
def install_framework(
    output_dir: str,
    framework: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """把指定离线框架包复制到目标目录，可选自定义输出文件名。"""
    return _run(
        lambda: service.install_framework(
            output_dir=output_dir,
            framework=framework,
            filename=filename,
        )
    )


@mcp.tool()
def install_tailwind(
    output_dir: str,
    filename: str = "tailwind.min.css",
) -> dict[str, Any]:
    """把内置 tailwind.min.css 复制到目标目录。"""
    return _run(lambda: service.install_tailwind(output_dir=output_dir, filename=filename))


if __name__ == "__main__":
    mcp.run(transport="stdio")
