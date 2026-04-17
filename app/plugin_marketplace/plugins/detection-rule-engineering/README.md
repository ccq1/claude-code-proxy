# 检测规则工程

## 1. 插件定位

`detection-rule-engineering` 用于把样本、IOC、漏洞材料和行为证据固化为可交付的 YARA / Sigma 检测内容，并补齐命中依据、误报控制和验证策略。

## 2. 目录结构

```text
detection-rule-engineering/
├── .claude-plugin/plugin.json
├── config/runtime.json
├── skills/detection-rule-engineering/
│   ├── SKILL.md
│   ├── references/
│   │   ├── REFERENCE_INDEX.md
│   │   ├── attack/enterprise-attack.json
│   │   └── vuln/
│   │       ├── known_exploited_vulnerabilities.json
│   │       └── nvdcve-2.0-recent.json
│   └── scripts/
│       ├── lookup_attack_stix.py
│       └── lookup_vuln_mirror.py
├── assets/icon.svg
└── README.md
```

## 3. 工作流程

```text
[扫描工作目录]
      |
      v
[定位样本 / 日志 / 规则 / 漏洞说明]
      |
      v
[做 reference check]
      |
      +--> [CVE / KEV] --> [lookup_vuln_mirror.py]
      |
      +--> [ATT&CK] ----> [lookup_attack_stix.py]
      |
      v
[提炼稳定特征]
      |
      +--> [文件侧] --> [YARA]
      |
      +--> [行为侧] --> [Sigma]
      |
      v
[补验证计划与格式检查]
```

## 4. 离线模式

- 插件自带漏洞与 ATT&CK 镜像
- helper script 默认从 skill 目录读取 reference
- 适合无公网环境下做 CVE / KEV / ATT&CK 富化

## 5. 使用方式

- `/detection-rule-engineering 基于这个目录里的样本和日志，给我生成一版 YARA 和 Sigma`
- `/detection-rule-engineering 帮我把这个样本特征做成稳定一点的检测规则`
- `/detection-rule-engineering 结合这个 CVE 材料做一版检测方案`

## 5.1 一键生产模式

```bash
cd skills/detection-rule-engineering
python scripts/build_detection_pack.py --workdir <your_case_dir> --family incident_pack
python scripts/validate_detection_artifacts.py --workdir ./generated_detection_pack
```

## 6. 输出内容

- `Rule Choice`
- `Deliverables`
- 单个可执行规则正文
- `Rationale`
- `Validation Plan`
- `Format Checks`
- `References Used`

## 7. 默认范围

- 最多 `1` 条高置信 YARA
- 最多 `1-3` 条 Sigma
- 最多 `0-2` 条补充 KQL / SPL

## 8. 注意事项

- 不要把所有字符串硬塞进 YARA。
- 不要把多条 Sigma 糊成一个 YAML 文档。
- `.kql` / `.spl` 里只能放可执行查询文本。
- 若无法完成最小自检，就不应宣称“高置信”或“可直接交付”。
