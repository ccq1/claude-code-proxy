---
name: detection-rule-engineering
description: 基于样本、IOC、漏洞信息和行为证据生成并优化 YARA、Sigma 等检测规则。
---

# 检测规则工程

## 何时使用

当用户要回答下面这些问题时使用本 skill：
- 基于样本、IOC 或配置片段生成 YARA
- 基于日志、行为或攻击链生成 Sigma
- 围绕 CVE、KEV、ATT&CK 富化规则解释和验证计划
- 把红队发现整理成可交付、可验证、误报可控的检测内容

## skill 基目录约定

本 skill 加载后，以下路径都相对于 skill 基目录：
- `references/REFERENCE_INDEX.md`
- `references/vuln/known_exploited_vulnerabilities.json`
- `references/vuln/nvdcve-2.0-recent.json`
- `references/attack/enterprise-attack.json`
- `scripts/lookup_vuln_mirror.py`
- `scripts/lookup_attack_stix.py`
- `scripts/build_detection_pack.py`
- `scripts/validate_detection_artifacts.py`

只要任务涉及 CVE / KEV / ATT&CK：
- 先查 helper script
- 再做 `rg -n`
- 必要时最后才做 `jq` 或局部 Python 读取

## 生产快速路径（默认）

默认先执行自动化脚本，再做人工收敛：

```bash
python scripts/build_detection_pack.py --workdir . --family incident_pack
python scripts/validate_detection_artifacts.py --workdir ./generated_detection_pack
```

规则：
- 如果校验失败，不能标记 `high-confidence` 或 `production-ready`
- 必须基于校验报告中的错误项做修正
- 输出中必须引用 `generated_detection_pack/manifest.json` 和 `validation_report.json`

## 工作目录优先

优先扫描：
- `*.yar`
- `*.yara`
- `*.sigma`
- `*.log`
- `*.evtx`
- `*.json`
- `*.csv`
- `*.txt`
- `*.pcap`
- `sample*`
- `ioc*`
- `report*`
- `cve*`

规则：
- 有明显主样本或主报告就直接开始。
- 有多组材料时，优先选证据最稳定、最贴近用户目标的一组。
- 引用证据优先使用相对路径。

## reference 检查是必做步骤

扫描完工作目录后，必须做一次短 reference check：
1. 读取 `references/REFERENCE_INDEX.md`
2. 若任务涉及 CVE / KEV，运行：
   ```bash
   python scripts/lookup_vuln_mirror.py CVE-2026-34197
   ```
3. 若任务涉及 ATT&CK，运行：
   ```bash
   python scripts/lookup_attack_stix.py T1497
   ```
4. 在输出末尾增加 `References Used`

如果本轮没有用到插件内置 reference，要明确写：
`bundled references not consulted for this pass`

## 大文件策略

不要整文件读取漏洞镜像或 STIX。

顺序固定：
1. helper script
2. `rg -n "CVE-|technique-id|family-name|keyword"`
3. `jq` 或局部 Python

## 选择规则类型

- **YARA**：文件、二进制、资源、节区、稳定字符串、构建标记
- **Sigma**：进程、命令行、网络、注册表、文件事件、认证事件
- **KQL / SPL**：只有在目标平台明确时才作为补充，并且必须保持“可直接执行”的纯查询文本

## 交付范围硬约束

默认最多输出：
- `1` 条高置信 YARA
- `1-3` 条可落地 Sigma
- `0-2` 条补充 KQL / SPL

证据不足时，宁可减少规则数量，也不要拼装“大全套”。

## 可执行产物格式约束

1. 一个文件或一个 fenced block 只放一个可执行对象。
2. `.yml` 里只放一条 Sigma。
3. `.yar` 里只放一条主规则。
4. `.kql` / `.spl` 只放可直接执行的查询文本。
5. 元数据、误报说明、验证计划写在外层说明里，不要混进 `.kql` / `.spl`。

禁止：
- 把多条 Sigma 糊成一个 YAML 文档
- 在 `.kql` 里混 `name:`、`description:`、`tags:`
- 输出伪 Sigma 语法
- 用随手拼的草稿冒充“production-ready”

## YARA 规则方法

1. 先找强锚点。
   - 家族特异字符串
   - 稳定配置键
   - 命名管道、互斥体、节区、构建标记
   - 足够稳定的 PE / 文件结构特征

2. 条件要有约束力。
   - 优先“多个强字符串 + 一个结构条件”
   - 除非每个候选字符串都非常特异，否则不要使用 `any of them`
   - 明确指出哪些弱锚点被故意排除

3. 必须交代误报面。
   - 哪些正常文件可能撞上
   - 哪些版本差异会导致漏报

## Sigma 规则方法

1. 先明确日志源。
   - process creation
   - registry
   - file event
   - network
   - PowerShell / script logging
   - auth / directory services

2. 规则刻画行为，不是堆字段。
   - 父子进程链
   - 关键参数组合
   - 操作顺序
   - 高价值字段组合

3. 语法必须有效。
   - 一条规则一个 YAML 文档
   - 使用标准字段和有效 YAML
   - 条件写在 detection 结构内

## 质量闸门

只有同时满足下面条件，才能标 `production-ready` 或 `high-confidence`：
1. 已运行 `scripts/validate_detection_artifacts.py` 且结果为 pass
2. 规则由少量强锚点构成
3. 误报边界已说明
4. 验证计划具体

否则：
- 标成 `hunting` 或 `draft`
- 缩范围，不要补大包

## 输出格式

```text
Rule Choice
- Recommended family:
- Why:
- Scope label:

Deliverables
- Count:
- File split:
- Why not more:

Rule
<single executable artifact>

Rationale
- Stable anchors:
- Weak anchors deliberately excluded:
- ATT&CK or behavior mapping:

Validation Plan
- Positive set:
- Negative set:
- Likely false positives:
- Tuning knobs:

Format Checks
- Syntax check performed:
- Executable artifact type:
- Constraints satisfied:

References Used
- Working directory evidence:
- Bundled references:
- Configured local mirrors:
```

## 护栏

- 不要把所有字符串都塞进 YARA。
- 不要把 Sigma 写成自由格式的 SIEM 查询。
- 若不能保证可执行性，就坦诚给“规则骨架 + 缺口 + 验证计划”。
