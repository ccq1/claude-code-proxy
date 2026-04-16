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
    "attack-surface-intel": {
        "id": "attack-surface-intel",
        "name": "目标攻击面情报",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "聚合资产清单、域名、IP、URL、样本与基础设施快照，在离线或隔离环境中快速定位高价值入口与可疑暴露面。",
        "tags": ["攻击面", "情报", "入口"],
        "installable": True,
        "kind": "skill-plugin",
        "iconPath": "/plugins/attack-surface-intel/assets/icon.svg",
        "iconText": "AS",
        "slashCommands": [
            {
                "name": "attack-surface-intel",
                "forwardName": "attack-surface-intel:attack-surface-intel",
                "description": "研判域名、IP、URL 与样本相关的攻击面情报。",
            }
        ],
        "settingsSchema": {
            "title": "攻击面情报配置",
            "description": "默认适配离线环境。可选配置第三方情报平台 API 凭据；无外网时可直接基于本地资产快照、IOC 导出和样本清单工作。",
            "fields": [
                {
                    "key": "intelWorkspace",
                    "label": "本地情报目录",
                    "type": "text",
                    "required": False,
                    "placeholder": "/data/intel",
                    "description": "可选。本地资产清单、IOC 导出、证书快照或样本索引所在目录。",
                    "placeholderToken": "INTEL_WORKSPACE",
                },
                {
                    "key": "vtApiKey",
                    "label": "VirusTotal API Key",
                    "type": "password",
                    "required": False,
                    "placeholder": "可选",
                    "description": "用于查询文件、URL、域名、IP 及关联关系。",
                    "placeholderToken": "VT_API_KEY",
                },
                {
                    "key": "shodanApiKey",
                    "label": "Shodan API Key",
                    "type": "password",
                    "required": False,
                    "placeholder": "可选",
                    "description": "用于枚举开放服务、Banner 和暴露端口。",
                    "placeholderToken": "SHODAN_API_KEY",
                },
                {
                    "key": "censysApiId",
                    "label": "Censys API ID",
                    "type": "text",
                    "required": False,
                    "placeholder": "可选",
                    "description": "用于查询主机、证书与被动基础设施关联。",
                    "placeholderToken": "CENSYS_API_ID",
                },
                {
                    "key": "censysApiSecret",
                    "label": "Censys API Secret",
                    "type": "password",
                    "required": False,
                    "placeholder": "可选",
                    "description": "与 Censys API ID 配套使用。",
                    "placeholderToken": "CENSYS_API_SECRET",
                },
            ],
        },
    },
    "attack-path-mapper": {
        "id": "attack-path-mapper",
        "name": "攻击路径推演",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "基于身份、权限、资产关系和 ATT&CK 技术链推演横向移动、提权与关键资产触达路径。",
        "tags": ["路径", "横向", "提权"],
        "installable": True,
        "kind": "skill-plugin",
        "iconPath": "/plugins/attack-path-mapper/assets/icon.svg",
        "iconText": "AP",
        "slashCommands": [
            {
                "name": "attack-path-mapper",
                "forwardName": "attack-path-mapper:attack-path-mapper",
                "description": "推演从当前 foothold 到目标资产的攻击链。",
            }
        ],
        "settingsSchema": {
            "title": "攻击路径推演配置",
            "description": "默认适配离线环境。可选指定本地 ATT&CK STIX 镜像目录，用于离线映射 tactic / technique。",
            "fields": [
                {
                    "key": "attackDataRoot",
                    "label": "ATT&CK 数据目录",
                    "type": "text",
                    "required": False,
                    "placeholder": "/var/lib/pandoraq/open-intel/attack",
                    "description": "本地 MITRE ATT&CK STIX 数据目录。",
                    "placeholderToken": "ATTACK_DATA_ROOT",
                },
            ],
        },
    },
    "malware-capability-review": {
        "id": "malware-capability-review",
        "name": "恶意能力研判",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "从样本、脚本和动态痕迹中提炼持久化、远控、凭据获取、投递与破坏能力画像。",
        "tags": ["样本", "能力", "研判"],
        "installable": True,
        "kind": "skill-plugin",
        "iconPath": "/plugins/malware-capability-review/assets/icon.svg",
        "iconText": "MC",
        "slashCommands": [
            {
                "name": "malware-capability-review",
                "forwardName": "malware-capability-review:malware-capability-review",
                "description": "从恶意样本与脚本中提炼能力画像。",
            }
        ],
    },
    "evasion-analysis": {
        "id": "evasion-analysis",
        "name": "沙箱对抗分析",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "识别反沙箱、反调试、反虚拟机、延时触发与环境探测逻辑，评估真实投放能力与规避门槛。",
        "tags": ["反沙箱", "规避", "反调试"],
        "installable": True,
        "kind": "skill-plugin",
        "iconPath": "/plugins/evasion-analysis/assets/icon.svg",
        "iconText": "EV",
        "slashCommands": [
            {
                "name": "evasion-analysis",
                "forwardName": "evasion-analysis:evasion-analysis",
                "description": "分析样本中的反沙箱、反调试与环境探测逻辑。",
            }
        ],
    },
    "detection-rule-engineering": {
        "id": "detection-rule-engineering",
        "name": "检测规则工程",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "基于样本、IOC 和行为证据生成并优化 YARA / Sigma 规则，兼顾命中率、可解释性与误报控制。",
        "tags": ["YARA", "Sigma", "检测"],
        "installable": True,
        "kind": "skill-plugin",
        "iconPath": "/plugins/detection-rule-engineering/assets/icon.svg",
        "iconText": "YR",
        "slashCommands": [
            {
                "name": "detection-rule-engineering",
                "forwardName": "detection-rule-engineering:detection-rule-engineering",
                "description": "生成并打磨 YARA、Sigma 等检测规则。",
            }
        ],
        "settingsSchema": {
            "title": "检测规则工程配置",
            "description": "默认适配离线环境。可选指定本地漏洞与 ATT&CK 镜像目录，用于离线引用 CVE、KEV 与 ATT&CK 数据。",
            "fields": [
                {
                    "key": "vulnDataRoot",
                    "label": "漏洞数据目录",
                    "type": "text",
                    "required": False,
                    "placeholder": "/var/lib/pandoraq/open-intel/vuln",
                    "description": "本地 NVD、KEV、CVE 等漏洞数据目录。",
                    "placeholderToken": "VULN_DATA_ROOT",
                },
                {
                    "key": "attackDataRoot",
                    "label": "ATT&CK 数据目录",
                    "type": "text",
                    "required": False,
                    "placeholder": "/var/lib/pandoraq/open-intel/attack",
                    "description": "本地 MITRE ATT&CK STIX 数据目录。",
                    "placeholderToken": "ATTACK_DATA_ROOT",
                },
            ],
        },
    },
    "poc-engineering": {
        "id": "poc-engineering",
        "name": "POC 工程化",
        "version": "0.1.0",
        "publisher": "PandoraQ Labs",
        "description": "将零散漏洞验证思路固化为可复现、可批量、可交付的检测与利用模板，覆盖请求编排、变量提取、前置探测与结果降噪。",
        "tags": ["POC", "模板", "工程化"],
        "installable": True,
        "kind": "skill-plugin",
        "iconPath": "/plugins/poc-engineering/assets/icon.svg",
        "iconText": "PO",
        "slashCommands": [
            {
                "name": "poc-engineering",
                "forwardName": "poc-engineering:poc-engineering",
                "description": "把漏洞验证思路落成可复现的 POC 模板。",
            }
        ],
        "settingsSchema": {
            "title": "POC 工程化配置",
            "description": "默认适配离线环境。可选指定本地漏洞镜像目录，用于离线引用 CVE、KEV 与版本信息。",
            "fields": [
                {
                    "key": "vulnDataRoot",
                    "label": "漏洞数据目录",
                    "type": "text",
                    "required": False,
                    "placeholder": "/var/lib/pandoraq/open-intel/vuln",
                    "description": "本地 NVD、KEV、CVE 等漏洞数据目录。",
                    "placeholderToken": "VULN_DATA_ROOT",
                },
            ],
        },
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
    if plugin_id == "redteam-kb":
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

    if plugin_id == "attack-surface-intel":
        return {
            "plugin": plugin_id,
        }

    if plugin_id == "attack-path-mapper":
        return {
            "plugin": plugin_id,
        }

    if plugin_id == "detection-rule-engineering":
        return {
            "plugin": plugin_id,
        }

    if plugin_id == "poc-engineering":
        return {
            "plugin": plugin_id,
        }

    if plugin_id in {"malware-capability-review", "evasion-analysis"}:
        return {"plugin": plugin_id}

    raise HTTPException(status_code=404, detail=f"plugin not found: {plugin_id}")


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
