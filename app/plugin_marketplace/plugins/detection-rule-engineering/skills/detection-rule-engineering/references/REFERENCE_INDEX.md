# 检测规则工程 Reference Index

本 skill 自带离线漏洞与 ATT&CK 参考资料。以下路径都相对于 skill 基目录：

## Bundled References

- `references/vuln/known_exploited_vulnerabilities.json`
  - CISA KEV 镜像
  - 用于确认是否在野利用、到期日和简要说明

- `references/vuln/nvdcve-2.0-recent.json`
  - NVD 近期 CVE 镜像
  - 用于提取描述、CVSS 和产品线索

- `references/attack/enterprise-attack.json`
  - MITRE ATT&CK Enterprise STIX 镜像
  - 用于 tactic / technique 名称、ID 和映射说明

## Helper Scripts

- `scripts/lookup_vuln_mirror.py <query>`
  - 快速查询 CVE / KEV

- `scripts/lookup_attack_stix.py <query>`
  - 快速查询 ATT&CK technique

## 使用规则

1. 先扫描工作目录，确定主样本、日志或漏洞说明。
2. 涉及 CVE / KEV / ATT&CK 时必须先查 helper script。
3. 若使用了内置资料，输出中必须列出实际使用的相对路径。
4. 若本轮未使用内置资料，要明确写明。
