# Ghidra 反编译插件

## 1. 插件定位

`ghidra-decompiler` 是一个面向内网和离线环境的反编译插件。
它提供一组面向逆向分析的高频动作：

- `import_binary`
- `get_program_metadata`
- `list_functions`
- `list_segments`
- `get_xrefs`
- `disassemble`
- `decompile_function`
- `get_call_graph`
- `export_strings`
- `search_symbol`
- `list_import_exports`
- `list_data_types`
- `read_memory`

`export_strings` 默认只返回小页预览，支持 `query` / `offset`，并把筛选结果落盘为 workspace 下的 `jsonl` artifact，避免把大量字符串塞进上下文。

## 2. 运行链路

标准调用链路如下：

1. 插件管理器根据 `.mcp.json` 拉起本地 MCP server。
2. `scripts/ghidra_mcp_server.py` 以标准 `FastMCP` `stdio` 方式注册工具。
3. MCP 工具内部再调用 `scripts/ghidra_headless.py`，由它负责探测本机 Ghidra、JDK 和 workspace。
4. `ghidra_headless.py` 最终调用本机 `support/analyzeHeadless` 和 `ghidra_scripts/*` 完成导入、检索、交叉引用、反汇编、反编译、类型查看与内存读取。

正常使用时，agent 应直接调用 MCP 动作，不要手工 shell 执行 `ghidra_mcp_server.py` 或 `ghidra_headless.py`。

## 3. 必要依赖

- 本机 Ghidra 安装，且存在 `support/analyzeHeadless`
- 本机 JDK 21+
- `python3`

### Ghidra 入口解析顺序

1. `GHIDRA_INSTALL_DIR`，可指向安装目录，或直接指向 `analyzeHeadless`
2. 自动发现常见目录，如 `/opt/ghidra*`、`/usr/local/ghidra*`、`~/ghidra*`

### Java 解析顺序

1. `GHIDRA_JAVA_HOME`
2. `JAVA_HOME`
3. `PATH` 中的 `java`

## 4. MCP 配置约定

插件使用标准 `stdio` MCP 配置，入口在 [.mcp.json](./.mcp.json)。
关键约定如下：

- `type` 使用 `stdio`
- `command` 使用 `python3`
- `args` 通过 `${CLAUDE_PLUGIN_ROOT}/scripts/ghidra_mcp_server.py` 指向插件内脚本
- 环境变量通过 `settingsSchema` 占位符注入，如 `{{GHIDRA_INSTALL_DIR}}`

这套写法比手工维护相对路径或自定义协议层更稳，Claude Code / PandoraQ 都可以直接复用。

## 5. 目录结构

```text
ghidra-decompiler/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── .cursor-plugin/plugin.json
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
├── assets/icon.svg
└── README.md
```

## 6. 默认缓存位置

若未显式配置 `GHIDRA_WORKSPACE_ROOT`，默认写到：

- Linux / macOS: `~/.cache/pandoraq-ghidra-decompiler`

该目录保存 headless project、注册表、临时产物与字符串 artifact。
