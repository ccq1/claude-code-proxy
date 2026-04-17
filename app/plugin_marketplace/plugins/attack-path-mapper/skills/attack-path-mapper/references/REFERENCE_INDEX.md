# 攻击路径推演 Reference Index

本 skill 自带离线 ATT&CK 参考资料。以下路径都相对于 skill 基目录：

## Bundled References

- `references/attack/enterprise-attack.json`
  - MITRE ATT&CK Enterprise STIX 镜像
  - 用于查询 technique 名称、ID、tactic 和简要描述

## Helper Scripts

- `scripts/lookup_attack_stix.py <query>`
  - 快速查询 technique ID、名称和 tactic
  - 适合处理大 STIX 文件，避免整文件读取

## 使用规则

1. 先扫描工作目录，锁定图数据、凭据、会话和资产关系。
2. 需要 ATT&CK 映射时，再查询内置 reference。
3. 若使用了内置 ATT&CK 资料，在输出中列出实际使用的相对路径。
4. 若本轮未使用内置资料，也要明确说明。
