# 插件市场说明文档索引

本文档汇总当前插件市场中的红队插件说明文档。

## 统一组织方式

当前 PandoraQ 自定义红队插件统一采用以下结构：

```text
plugin/
├── .claude-plugin/plugin.json
├── skills/<skill-name>/
│   ├── SKILL.md             # 中文执行合同
│   ├── references/...       # skill 本地 reference
│   └── scripts/...          # skill helper script
├── config/runtime.json      # 可选，插件级运行时配置
├── assets/icon.svg
└── README.md
```

这套结构的目标是：
- slash command 直接进入 `skills/<skill-name>/SKILL.md`
- skill 在自己的基目录内直接访问 `references/` 和 `scripts/`
- 文案和执行合同统一使用中文

## 插件清单

| 插件 | 说明文档 | 核心定位 |
| --- | --- | --- |
| `redteam-kb` | [redteam-kb/README.md](./redteam-kb/README.md) | 检索私有红队知识库中的工具、文章、代码与证据 |
| `attack-surface-intel` | [attack-surface-intel/README.md](./attack-surface-intel/README.md) | 研判资产、IOC 与基础设施暴露面，定位高价值入口 |
| `attack-path-mapper` | [attack-path-mapper/README.md](./attack-path-mapper/README.md) | 结合资产、身份与 ATT&CK 关系推演攻击路径 |
| `malware-capability-review` | [malware-capability-review/README.md](./malware-capability-review/README.md) | 从样本与报告中提炼恶意能力画像 |
| `evasion-analysis` | [evasion-analysis/README.md](./evasion-analysis/README.md) | 分析反沙箱、反调试、反虚拟机与环境探测逻辑 |
| `detection-rule-engineering` | [detection-rule-engineering/README.md](./detection-rule-engineering/README.md) | 生成并优化 YARA / Sigma 等检测规则 |
| `poc-engineering` | [poc-engineering/README.md](./poc-engineering/README.md) | 将漏洞验证思路工程化为可复现、可批量的模板 |
| `superpowers` | [superpowers/README.md](./superpowers/README.md) | 用规范化流程增强编码代理的规划、TDD、调试与协作能力 |
| `ghidra-decompiler` | [ghidra-decompiler/README.md](./ghidra-decompiler/README.md) | 随插件分发固定版 Ghidra runtime，通过 headless 能力完成导入、符号检索与函数反编译 |

## 统一使用原则

- 优先把样本、报告、请求、IOC、导出结果放到当前工作目录。
- skill 默认先扫描工作目录，再决定是否读取 skill 自带 `references/` 和 `scripts/`。
- 对大文件优先使用 `rg`、`jq`、helper script 等方式快速缩小范围，不整文件灌入上下文。
- 只有关键输入缺失且会显著改变结果时才提问；否则直接给首版结果。
- 离线环境优先使用本地镜像、插件自带 reference 和内部服务，不依赖公网。
