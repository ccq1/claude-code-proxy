from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException

from app.config import config

PLUGIN_MARKETPLACE = "pandoraq-private"
PLUGIN_ROOT = Path(__file__).resolve().parent / "plugins"
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".sh",
    ".svg",
}

PLUGIN_CATALOG: Dict[str, Dict[str, Any]] = {
    "redteam-kb": {
        "id": "redteam-kb",
        "name": "红队知识库",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "查询私有红队知识库，快速检索工具、文章、配置和代码证据。",
        "tags": ["知识库", "红队", "检索"],
        "installable": True,
        "kind": "skill-plugin",
        "iconPath": "/plugins/redteam-kb/assets/icon.svg",
        "slashCommands": [
            {
                "name": "redteam-kb",
                "forwardName": "redteam-kb:redteam-kb",
                "description": "调用红队知识库插件。",
            }
        ],
        "settingsSchema": {
            "title": "红队知识库配置",
            "description": "设置插件访问的知识库地址和可选密钥。保存后会重新生成本地命令与技能文件。",
            "fields": [
                {
                    "key": "baseUrl",
                    "label": "知识库地址",
                    "type": "url",
                    "required": True,
                    "placeholder": "http://127.0.0.1:5010",
                    "description": "例如本地 GPU 机器地址，或云上的知识库服务地址。",
                    "placeholderToken": "REDTEAM_KB_BASE_URL",
                },
                {
                    "key": "apiKey",
                    "label": "访问密钥",
                    "type": "password",
                    "required": False,
                    "placeholder": "可选",
                    "description": "如果知识库启用了鉴权，可在这里填写。当前仅本地保存，不会回写到 llm_proxy。",
                },
            ],
        },
    },
    "virustotal-lookup": {
        "id": "virustotal-lookup",
        "name": "威胁情报查询",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "查询文件、域名和地址信誉。",
        "tags": ["情报", "IOC", "检索"],
        "installable": False,
        "kind": "coming-soon",
        "iconText": "VT",
    },
    "attack-mapper": {
        "id": "attack-mapper",
        "name": "行为映射",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "把命令和行为映射成常见攻击阶段。",
        "tags": ["映射", "分析", "报告"],
        "installable": False,
        "kind": "coming-soon",
        "iconText": "AT",
    },
    "sandbox-summary": {
        "id": "sandbox-summary",
        "name": "沙箱摘要",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "把冗长的沙箱输出整理成简短结论。",
        "tags": ["沙箱", "摘要", "样本"],
        "installable": False,
        "kind": "coming-soon",
        "iconText": "SB",
    },
}


def _plugin_dir(plugin_id: str) -> Path:
    return PLUGIN_ROOT / plugin_id


def _require_plugin(plugin_id: str) -> Dict[str, Any]:
    plugin = PLUGIN_CATALOG.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"plugin not found: {plugin_id}")
    return plugin


def list_plugins() -> Dict[str, Any]:
    return {
        "marketplace": PLUGIN_MARKETPLACE,
        "plugins": [dict(item) for item in PLUGIN_CATALOG.values()],
    }


def get_plugin_manifest(plugin_id: str) -> Dict[str, Any]:
    plugin = dict(_require_plugin(plugin_id))
    plugin["marketplace"] = PLUGIN_MARKETPLACE
    return plugin


def build_plugin_runtime_config(plugin_id: str) -> Dict[str, Any]:
    if plugin_id != "redteam-kb":
        raise HTTPException(status_code=404, detail=f"plugin not found: {plugin_id}")

    if not config.redteam_kb_base_url:
        raise HTTPException(
            status_code=404,
            detail="redteam-kb service address is not configured",
        )

    return {
        "plugin": plugin_id,
        "baseUrl": config.redteam_kb_base_url,
        "hasApiKey": bool(config.redteam_kb_api_key),
    }


def _read_bundle_files(plugin_id: str) -> List[Dict[str, Any]]:
    base_dir = _plugin_dir(plugin_id)
    if not base_dir.exists():
        raise HTTPException(status_code=404, detail=f"plugin files not found: {plugin_id}")

    files: List[Dict[str, Any]] = []
    for path in sorted(base_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(base_dir).as_posix()
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            files.append(
                {
                    "path": relative_path,
                    "encoding": "utf-8",
                    "content": path.read_text(encoding="utf-8"),
                }
            )
        else:
            files.append(
                {
                    "path": relative_path,
                    "encoding": "base64",
                    "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            )
    return files


def build_plugin_bundle(plugin_id: str) -> Dict[str, Any]:
    plugin = _require_plugin(plugin_id)
    if not plugin.get("installable"):
        raise HTTPException(status_code=404, detail=f"plugin not installable: {plugin_id}")
    return {
        "plugin": get_plugin_manifest(plugin_id),
        "files": _read_bundle_files(plugin_id),
    }


def get_plugin_asset_path(plugin_id: str, asset_path: str) -> Path:
    _require_plugin(plugin_id)
    normalized_asset_path = asset_path.lstrip("/").replace("\\", "/")
    candidate = (_plugin_dir(plugin_id) / "assets" / normalized_asset_path).resolve()
    plugin_dir = _plugin_dir(plugin_id).resolve()
    if not str(candidate).startswith(str(plugin_dir)) or not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="plugin asset not found")
    return candidate


def guess_asset_media_type(asset_path: str) -> str:
    return mimetypes.guess_type(asset_path)[0] or "application/octet-stream"
