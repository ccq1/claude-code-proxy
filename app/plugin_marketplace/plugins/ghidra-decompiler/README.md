# Ghidra 反编译

## 1. 插件定位

`ghidra-decompiler` 是一个面向内网和离线环境的反编译插件。它把固定版本的官方 Ghidra runtime 直接随插件分发，通过 bundled `support/analyzeHeadless` 暴露最常用的 5 个高频动作：

- `import_binary`
- `list_functions`
- `decompile_function`
- `export_strings`
- `search_symbol`

这意味着交付时不是只发一个 `analyzeHeadless` 壳脚本，而是把完整可运行的 Ghidra runtime 一起带上，便于在内网环境稳定复用。

其中 `export_strings` 已按 Agent 使用场景做了收敛：默认只返回小页预览，支持 `query` / `offset`，并把筛选结果落成 workspace 下的 `jsonl` artifact 文件，避免一次性把大量字符串塞进上下文。

## 2. 固定版本与来源

- 固定版本：`Ghidra 12.0.4`
- 官方 release tag：`Ghidra_12.0.4_build`
- 官方 zip：`ghidra_12.0.4_PUBLIC_20260303.zip`
- 官方 SHA-256：
  `c3b458661d69e26e203d739c0c82d143cc8a4a29d9e571f099c2cf4bda62a120`

这里保留版本、发行标签、压缩包名称和 SHA-256，便于内网环境做来源核验；插件本身不再携带下载外链。

## 3. 目录结构

```text
ghidra-decompiler/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── .mcp.json
├── config/runtime.json
├── scripts/
│   ├── ghidra_mcp_server.py
│   ├── ghidra_headless.py
│   └── ghidra_scripts/
│       ├── common.py
│       ├── export_program_summary.py
│       ├── list_functions.py
│       ├── decompile_function.py
│       ├── export_strings.py
│       └── search_symbol.py
├── skills/ghidra-decompiler/SKILL.md
├── runtime/
│   └── ghidra_12.0.4_PUBLIC/
│       ├── LICENSE
│       ├── NOTICE
│       └── support/analyzeHeadless
├── assets/icon.svg
└── README.md
```

## 4. 运行方式

```text
[本地样本]
      |
      v
[MCP: import_binary]
      |
      v
[bundled analyzeHeadless]
      |
      v
[创建 / 打开 headless project]
      |
      +--> [list_functions]
      +--> [search_symbol]
      +--> [export_strings]
      +--> [decompile_function]
```

所有底层动作统一调用 bundled `support/analyzeHeadless`，而不是直接依赖用户自己装的 Ghidra 目录。

## 5. 交付方式说明

这是内网最推荐的交付方式：

- 固定版本，减少环境差异
- 整套 runtime 随插件分发，避免“只有脚本、没有 Ghidra 本体”的半成品
- 只暴露少量高频 MCP 动作，便于上层 Agent 使用
- `LICENSE` 和 `NOTICE` 跟随官方 runtime 一起保留

## 6. 仍需的外部依赖

插件会自带 Ghidra runtime，但仍然需要本机可用的 **JDK 21**。

优先级如下：
1. `GHIDRA_JAVA_HOME`
2. `JAVA_HOME`
3. `PATH` 中的 `java`

若三者都不可用，MCP server 会直接返回 `error_code=missing_jdk` 的结构化结果，而不是继续伪造结果。

## 7. 默认缓存位置

若未显式配置 `GHIDRA_WORKSPACE_ROOT`，MCP server 默认把 headless project 和注册表写到：

- Linux / macOS: `~/.cache/pandoraq-ghidra-decompiler`

这样即使插件目录本身是只读的，也能正常导入样本并重复使用已有工程。

## 8. 当前基础架构范围

这次先搭好的是“能分发、能起 MCP server、能统一调 analyzeHeadless”的基础层：

- bundled Ghidra runtime
- 本地 MCP server
- 5 个高频动作的输入 / 输出协议
- 统一的 headless wrapper
- Ghidra postScript 骨架

如果后面你要继续往下做，可以再补：

- 平台 / loader / language / cspec 显式选择
- 项目复用策略和缓存淘汰
- 更丰富的反编译上下文导出
- 交叉引用、调用图、数据流与批量函数导出

## 9. 官方许可文件

bundled runtime 中会保留官方 `LICENSE`，并额外提供一个顶层 `NOTICE` 入口文件：

- `runtime/ghidra_12.0.4_PUBLIC/LICENSE`
- `runtime/ghidra_12.0.4_PUBLIC/NOTICE`

说明：
- 官方 `Ghidra 12.0.4 PUBLIC` release zip 中包含 `LICENSE`、`licenses/` 和 `bom.json`
- 该 release zip 未提供顶层 `NOTICE`
- 本插件分发层补了一个顶层 `NOTICE`，用于把许可入口固定下来，便于内网分发和审计
