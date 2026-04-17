# POC 工程化 Reference Index

本 skill 自带离线漏洞参考资料。以下路径都相对于 skill 基目录：

## Bundled References

- `references/vuln/known_exploited_vulnerabilities.json`
  - CISA KEV 镜像
  - 用于确认是否在野利用与补丁时限

- `references/vuln/nvdcve-2.0-recent.json`
  - NVD 近期 CVE 镜像
  - 用于提取描述、CVSS、受影响产品和版本线索

## Helper Scripts

- `scripts/lookup_vuln_mirror.py <query>`
  - 快速查询 CVE / KEV 上下文

## 使用规则

1. 先扫描工作目录，锁定主公告、主请求或主 POC 草稿。
2. 涉及 CVE / KEV / 版本研判时优先查 helper script。
3. 若使用了内置漏洞资料，输出中必须列出实际使用的相对路径。
4. 若本轮未使用内置资料，也要明确说明。
