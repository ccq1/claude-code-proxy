---
description: 从当前 foothold、身份和资产关系中推演可执行的攻击路径
allowed-tools:
  - Bash(rg:*)
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(head:*)
  - Bash(tail:*)
  - Bash(jq:*)
  - Bash(python:*)
  - Bash(python3:*)
  - Bash(curl:*)
---

使用 `attack-path-mapper` skill 协助当前任务。

执行原则：
1. 先扫描当前工作目录，优先寻找资产关系、AD/BloodHound 导出、凭据记录、网络拓扑、主机清单、事件日志与笔记。
2. 若当前目录中存在单一明显的导出结果或上下文文件，直接以它为起点，不要先让用户再补参数。
3. 若有多个候选数据源，优先选与用户目标最接近、结构最完整的一组，并在回答开头说明你采用了哪些相对路径。
4. 在输出中始终使用相对路径引用证据文件。
5. 先明确起点、目标资产、约束和可接受噪声级别。
6. 每一跳都标清前置条件、证据强度和潜在检测面。
7. 优先给出最短、最稳、最易验证的攻击链，而不是最长的理论路径。
8. 映射到 ATT&CK 时只引用有证据支撑的阶段与技术。
9. 对大 JSON 或图数据不要整文件读取；优先 `rg -n` 搜 technique、主机名、用户、组或边类型，再用 `jq` / helper script 精取需要的对象。

若配置了本地 ATT&CK 镜像目录，优先从 `{{ATTACK_DATA_ROOT}}` 读取 STIX 数据做离线映射。
