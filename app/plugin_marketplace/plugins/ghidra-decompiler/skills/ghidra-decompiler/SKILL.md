---
name: ghidra-decompiler
description: 对本地二进制提供导入、程序元信息、符号检索、交叉引用、反汇编、字符串导出、调用关系分析与函数级反编译能力，适合 ELF/PE/Mach-O 的离线逆向分析。
user-invocable: true
argument-hint: "本地样本路径、关注函数/符号（可选）"
---

# Ghidra 反编译

## 何时使用

当用户需要下面这些能力时使用本 skill：
- 导入本地 ELF / PE / Mach-O 样本并建立分析工程
- 查看程序元信息、段信息、函数列表、导入导出和数据类型
- 搜索符号、查看交叉引用、读取原始字节、输出反汇编与调用关系
- 对指定函数做函数级反编译并结合字符串线索分析

## 核心约束

1. 这是本地 headless 反编译工作流，不依赖公网分析服务。
2. 若用户还没给出样本路径，先问一个最小必要问题，再继续。
3. 首次处理某个样本时，必须先调用 `import_binary`。
4. 先用 `get_program_metadata` 看入口与建议起点，再用 `search_symbol` / `list_functions` 缩小范围。
5. `export_strings` 默认只返回一小页预览，并把筛选结果落到 artifact 文件。优先使用 `query` / `offset` 缩小范围，不要把大量字符串原样贴进对话。
6. 这些能力由插件自带的本地 MCP server 提供。不要直接 shell 执行 `ghidra_mcp_server.py` 或 `ghidra_headless.py`，而是直接调用 MCP 动作。
7. 若 Java 21 或 Ghidra 安装不可用，直接说明缺失项；若 MCP 返回 `missing_jdk` / `unsupported_jdk` / `missing_ghidra_install`，明确提示用户补齐环境，不要编造结果。
8. 如果当前会话里看不到 `import_binary`、`list_functions`、`decompile_function`、`export_strings`、`search_symbol` 这些工具，优先判断插件 MCP 未成功加载，而不是自行退回到 `strings` / `xxd` / `file` 伪装成同等能力。

## 默认执行方式

- 全程使用中文输出。
- 若用户还没给出目标二进制路径，先用一句简短中文确认样本路径。
- 默认通过 skill 绑定的 MCP 工具工作，不绕过插件入口直接调用内部脚本。
- 输出分析结论时，优先给出关键函数、关键符号、字符串线索和对应路径/函数名，不要堆大段原始输出。

## 推荐顺序

1. 首次处理某个样本时，先调用 `import_binary`。
2. 立即调用 `get_program_metadata`，优先看 `entry_point`、`suggested_start_functions`、`main_candidates`、`analysis_hints`。
3. 需要函数入口时，优先调用 `search_symbol` 或 `list_functions`。
4. 需要调用关系或定位谁引用了谁时，调用 `get_xrefs` 或 `get_call_graph`。
5. 需要看汇编级细节时，调用 `disassemble`。
6. 做函数级分析时，再调用 `decompile_function`。
7. 需要字符串侧线索时，调用 `export_strings`，优先使用较小的 `limit` 和必要的 `query` / `offset`。
8. 需要段信息、导入导出、数据类型或原始字节时，分别调用 `list_segments`、`list_import_exports`、`list_data_types`、`read_memory`。
9. 若 `export_strings` 返回 `artifact_path`，把它当成全量筛选结果，不要把大量字符串原样贴进对话。

## MCP 动作

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
