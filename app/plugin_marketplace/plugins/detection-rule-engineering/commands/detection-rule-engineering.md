---
description: 基于行为与样本证据编写并优化 YARA、Sigma 等检测规则
allowed-tools:
  - Bash(rg:*)
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(head:*)
  - Bash(tail:*)
  - Bash(file:*)
  - Bash(strings:*)
  - Bash(sha256sum:*)
  - Bash(jq:*)
  - Bash(python:*)
  - Bash(python3:*)
  - Bash(curl:*)
---

使用 `detection-rule-engineering` skill 协助当前任务。

执行原则：
1. 先扫描当前工作目录，优先寻找样本、IOC、日志、沙箱报告、现有规则和漏洞说明文件。
2. 若当前目录里已有明显的主要输入，直接开始写规则，不要先要求用户整理参数。
3. 若有多份候选材料，优先采用最接近用户目标、证据最稳定的一组，并在回答开头说明使用了哪些相对路径。
4. 在输出里引用证据时优先使用相对路径。
5. 先收集稳定特征，再决定写 YARA、Sigma，还是两者都写。
6. 规则必须同时给出命中依据、约束边界和可能误报面。
7. 生成规则后，优先补验证策略，而不是只给出一段文本。
8. 避免把脆弱 IOC 堆砌成规则；优先行为模式、稳定字符串和结构特征。
9. 对 `references/vuln/*.json`、`references/attack/*.json` 这类大文件，优先使用 helper script、`rg -n` 和 `jq` 精确提取，不要整文件 `cat`。

若配置了本地数据目录，优先从 `{{VULN_DATA_ROOT}}` 和 `{{ATTACK_DATA_ROOT}}` 读取离线漏洞与 ATT&CK 数据。
