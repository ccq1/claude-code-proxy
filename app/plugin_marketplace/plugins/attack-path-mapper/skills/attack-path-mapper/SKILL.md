---
name: attack-path-mapper
description: 根据身份、权限、主机关系和 ATT&CK 技术链推演横向移动、提权与关键资产触达路径。
---

# 攻击路径推演

## 何时使用

当用户要回答下面这些问题时使用本 skill：
- 从当前 foothold 如何最稳地到达目标资产
- 凭据、会话、ACL、组关系和主机关系怎样组成可执行攻击链
- 某条路径需要哪些前置条件、会触发哪些检测面
- 观察到的行为应该映射到哪些 ATT&CK tactic / technique

## skill 基目录约定

本 skill 加载后，以下路径都相对于 skill 基目录：
- `references/REFERENCE_INDEX.md`
- `references/attack/enterprise-attack.json`
- `scripts/lookup_attack_stix.py`
- `scripts/build_attack_paths.py`

如需 ATT&CK 富化，优先运行：
```bash
python scripts/lookup_attack_stix.py T1497
python scripts/lookup_attack_stix.py kerberoasting
```

## 生产快速路径（默认）

默认先跑路径构建脚本，再补充路径解释：

```bash
python scripts/build_attack_paths.py --workdir . --start user01 --target dc01
```

规则：
- 优先复用脚本输出的最短路径和置信标签
- 如果脚本未找到路径，不能伪造主路径，必须报告阻塞点
- 输出中必须引用 `attack_path_report.json`

## 工作目录优先

默认认为用户把图数据或关系导出放在当前工作目录。

优先扫描：
- `bloodhound*`
- `nodes*`
- `edges*`
- `sessions*`
- `creds*`
- `hosts*`
- `acl*`
- `notes*`
- `*.json`
- `*.csv`

规则：
- 有明显主输入就直接开始。
- 有多组候选就选最贴近用户目标的一组，并说明假设。
- 引用证据优先使用相对路径。

## 大文件策略

对大图数据、大 JSON、大 CSV：
1. 先用 `rg -n` 锁定主机名、用户名、组名、边类型、权限关键字。
2. 再用 `jq` 或局部 Python 提取相关节点和边。
3. ATT&CK 数据优先用 `scripts/lookup_attack_stix.py`，不要整文件读取 STIX。

## 核心工作流

1. 明确起点、目标和约束。
   - 起点：当前主机、会话、凭据或身份。
   - 目标：域控、高价值主机、业务系统或数据域。
   - 约束：噪声、权限边界、操作风险。

2. 盘点可用边。
   - 身份边：组成员、委派、ACL、票据、凭据复用。
   - 服务边：WinRM、SMB、RDP、计划任务、服务控制、代理链路。
   - 资产边：会话、相邻网段、信任关系、跳板机。

3. 组合候选路径。
   - 优先最短、最稳、最容易验证的链路。
   - 每一步都标注前置条件、所需凭据、预期结果和检测面。

4. 做 ATT&CK 映射。
   - 只映射有证据支撑的 tactic / technique。
   - 若需要 technique 名称、ID 或 tactic，调用 helper script 查询。

5. 输出主路径和备选路径。
   - 标注 `confirmed / likely / speculative`。
   - 明确哪一步最值得先验证。

## 输出格式

```text
Path Summary
- Start:
- Target:
- Recommended path:
- Backup path:

Step Breakdown
- Step:
  evidence:
  prerequisites:
  detection surface:
  confidence:

ATT&CK Mapping
- Technique:
  reason:

Next Validation
- Check 1:
- Check 2:

References Used
- Working directory evidence:
- Bundled ATT&CK references:
- Configured local mirrors:
```

## 护栏

- 不要把理论可能性直接写成确认路径。
- 不要为了“看起来完整”而拼很长的攻击链。
- ATT&CK 映射必须能回溯到具体证据。
- 若内置 ATT&CK reference 没有用到，明确写明本轮未使用。
