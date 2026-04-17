---
description: 使用 bundled Ghidra headless 导入样本、检索符号并做函数级反编译
---

先加载 `ghidra-decompiler` skill，并全程使用中文输出。

使用 `skill: "ghidra-decompiler"`，然后按下面的顺序执行：
1. 若用户还没给出样本路径，先用一句简短中文确认目标二进制路径。
2. 首次处理某个样本时，先调用 `mcp__ghidra-decompiler__import_binary`。
3. 需要函数入口时，优先调用 `mcp__ghidra-decompiler__search_symbol` 或 `mcp__ghidra-decompiler__list_functions`。
4. 做函数级分析时，再调用 `mcp__ghidra-decompiler__decompile_function`。
5. 需要字符串侧线索时，调用 `mcp__ghidra-decompiler__export_strings`，优先使用 `query` 和较小的 `limit`，把 `artifact_path` 当成全量筛选结果。
6. 若 MCP 返回 Java / Ghidra runtime 缺失错误，明确说明缺少 JDK 21 或 bundled runtime 不完整，不要伪造反编译结果。
