---
name: poc-engineering
description: 将公告、请求样本、漏洞说明和利用思路工程化为可复现、可交付的 POC 模板。
---

# POC 工程化

## 何时使用

当用户要回答下面这些问题时使用本 skill：
- 把零散 exploit note、HTTP 请求或验证思路整理成可复用模板
- 将一次性验证步骤固化为安全验证版和更自动化版
- 基于 CVE / KEV / 公告背景补齐版本判断、前置检查和成功判定
- 降低误报、减少副作用、明确交付边界

## skill 基目录约定

本 skill 加载后，以下路径都相对于 skill 基目录：
- `references/REFERENCE_INDEX.md`
- `references/vuln/known_exploited_vulnerabilities.json`
- `references/vuln/nvdcve-2.0-recent.json`
- `scripts/lookup_vuln_mirror.py`
- `scripts/poc_oneclick.py`
- `scripts/scaffold_poc.py`
- `scripts/run_batch_verify.py`

涉及 CVE / KEV / 厂商公告背景时，优先运行：
```bash
python scripts/lookup_vuln_mirror.py CVE-2026-34197
```

## 生产快速路径（默认）

当用户通过 `/poc-engineering ...` 触发时，默认执行一键流水线，不要求用户逐个输入参数：

```bash
python scripts/poc_oneclick.py --workdir .
```

档位映射（仅在用户明确提到时切换）：
- 保守 / safe -> `--profile safe`
- 默认 / balanced -> `--profile balanced`
- 激进 / aggressive -> `--profile aggressive`

只有在用户明确要求“拆开执行”时，才使用分步命令。

分步命令如下：

```bash
python scripts/scaffold_poc.py --workdir . --name incident_case
```

需要更稳的成功判定时：
```bash
python scripts/scaffold_poc.py --workdir . --name incident_case --success-status 200,204 --signal-status 401,403 --success-keyword success
```

批量验证时：
```bash
python scripts/run_batch_verify.py --targets-file ./targets.txt --manifest ./generated_poc_pack/manifest.json --workers 20
```

规则：
- 首版必须基于脚本产物，不要从零手写整套模板
- 输出中必须引用 `generated_poc_pack/manifest.json`
- 若要提升风险等级，必须先明确获得用户授权

## 工作目录优先

优先扫描：
- `*.http`
- `*.txt`
- `*.md`
- `*.json`
- `*.yaml`
- `*.pcap`
- `*.har`
- `request*`
- `response*`
- `poc*`
- `exploit*`
- `cve*`
- `advisory*`

规则：
- 有明显主请求、主公告或主 POC 草稿就直接开始。
- 有多个候选材料时，选最完整、最贴近目标系统的一组，并说明假设。
- 引用证据优先使用相对路径。

## reference 检查是必做步骤

扫描完工作目录后，必须做一次短 reference check：
1. 读取 `references/REFERENCE_INDEX.md`
2. 涉及 CVE / KEV / 版本研判时，运行 `python scripts/lookup_vuln_mirror.py <query>`
3. 在输出末尾增加 `References Used`

如果本轮没有用到插件内置漏洞 reference，要明确写明。

## 大文件策略

对大公告集合、大抓包和大请求转储：
1. 先用 `rg -n` 找产品名、版本、路径、参数、状态码、错误关键字。
2. 漏洞镜像优先 helper script。
3. 再用 `jq` 或局部 Python 读取目标对象。
4. 只读关键请求/响应片段，不整份灌入上下文。

## 默认姿态

默认优先**低影响安全验证**：
- 先 fingerprint
- 再 prerequisite check
- 最后才给验证请求
- 只有用户明确需要时，才向更高风险利用推进

## 自动化默认

只要用户给了请求样本、漏洞说明、POC 草稿或 exploit note，就直接产出首版工程化结果，不要停留在分析。

默认首版必须包含：
- 操作员摘要
- 漏洞与请求归一化分析
- 一版安全验证模板或脚本
- 一版更自动化的变体
- 成功 / 失败判定
- 误报控制、副作用和假设

不要以“要不要脚本 / 要不要批量 / 要不要报告”收尾。

## 提问策略

只有在缺少关键信息且会显著改变结果时，才允许提问，例如：
- 协议不明确
- 认证必需但缺失
- 动作可能具有破坏性且用户未授权
- 缺少最小输入材料（请求样本或目标清单）

如果必须提问：
- 必须使用 `AskUserQuestion`
- 最多一个简短阻塞问题
- 先把目录和本地 reference 中能提取的信息都提取完
- 如果不影响安全首版结果，就直接带假设继续，不要提问

Slash 命令特殊规则：
- 不要问“要不要脚本 / 要不要批量 / 要不要报告”。
- 不要让用户逐个输入 `workers/timeout/success-status/signal-status`。
- 默认用 profile 预设跑通首版，再在结果中说明采用的 profile 与关键参数。

## 核心工作流

1. 明确目标契约。
   - 产品 / 版本
   - 协议
   - 认证要求
   - 成功判定
   - 副作用边界

2. 拆分请求流。
   - fingerprint
   - prerequisite checks
   - exploit / validation request
   - 动态变量提取
   - success matcher
   - false-positive suppression

3. 选实现形式。
   - HTTP 声明式检查优先模板
   - 多步骤状态逻辑可用 Python / Bash 脚手架
   - 如有必要，同时给简版模板和脚本版

4. 补工程质量。
   - 超时与重试
   - 重定向处理
   - 认证捕获
   - token / nonce / CSRF 提取
   - 幂等性与清理说明

## 输出格式

```text
Operator Summary
- Target assumption:
- Vulnerability class:
- Default posture:

Normalized Analysis
- Entry point:
- Preconditions:
- Key variables:
- Success signal:
- Failure signal:

Primary Deliverable
<single template or script>

Automation Variant
<second variant if feasible>

Safety Notes
- Side effects:
- False positives:
- Assumptions:

References Used
- Working directory evidence:
- Bundled references:
- Configured local mirrors:
```

## 护栏

- 不要隐藏副作用。
- 不要把版本猜测当作漏洞已证实。
- 解释清楚哪一步才是真正的 proof。
- 若信号脆弱，明确标注 best-effort，而不是冒充高置信结果。
