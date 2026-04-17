# POC 工程化

## 1. 插件定位

`poc-engineering` 用于把零散的漏洞验证思路、原始 HTTP 请求、利用脚本或安全公告工程化为可复现、可批量、可交付的 POC 模板或验证脚手架。

## 2. 目录结构

```text
poc-engineering/
├── .claude-plugin/plugin.json
├── config/runtime.json
├── skills/poc-engineering/
│   ├── SKILL.md
│   ├── references/
│   │   ├── REFERENCE_INDEX.md
│   │   └── vuln/
│   │       ├── known_exploited_vulnerabilities.json
│   │       └── nvdcve-2.0-recent.json
│   └── scripts/lookup_vuln_mirror.py
├── assets/icon.svg
└── README.md
```

## 3. 工作流程

```text
[扫描工作目录]
      |
      v
[定位主请求 / 公告 / POC 草稿]
      |
      v
[做 reference check]
      |
      v
[归一化漏洞与请求结构]
      |
      v
[拆分前置检查 / 变量提取 / 验证请求]
      |
      v
[生成安全验证版 + 自动化版]
      |
      v
[补成功判定 / 误报控制 / 风险说明]
```

## 4. 离线模式

- 插件自带漏洞镜像
- 支持 `skills/poc-engineering/scripts/lookup_vuln_mirror.py`
- 默认可在隔离环境中完成 CVE / KEV 富化

## 5. 使用方式

- `/poc-engineering 把这个目录里的漏洞材料整理成可复现的 POC`
- `/poc-engineering 基于这个请求样本，给我做一版安全验证模板`
- `/poc-engineering 把这个 exploit note 工程化成可批量验证的脚手架`

## 5.1 一键生产模式

```bash
cd skills/poc-engineering
python scripts/scaffold_poc.py --workdir <your_case_dir> --name incident_case
```

## 6. 输出内容

- `Operator Summary`
- `Normalized Analysis`
- 主模板或主脚本
- `Automation Variant`
- `Safety Notes`
- `References Used`

## 7. 提问策略

- 默认直接产出首版结果
- 只有协议、认证或风险边界不明确且会显著改变结果时才提问
- 若必须提问，必须使用 `AskUserQuestion`

## 8. 注意事项

- 默认优先低影响安全验证。
- 不要把“要不要脚本 / 批量 / 报告”当成问题。
- 大抓包和大漏洞镜像优先局部查询，不整份灌入上下文。
