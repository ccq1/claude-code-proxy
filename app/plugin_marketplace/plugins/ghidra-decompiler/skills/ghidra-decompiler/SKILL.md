---
name: ghidra-decompiler
description: 使用 bundled Ghidra headless 对本地二进制做导入、函数检索、字符串导出与函数级反编译，适合 ELF/PE/Mach-O 的离线逆向分析。
---

# Ghidra 反编译

## 何时使用

当用户需要下面这些能力时使用本 skill：
- 导入本地 ELF / PE / Mach-O 样本并建立 headless project
- 枚举样本里的函数、导出字符串、搜索符号
- 对指定函数做函数级反编译
- 在离线或内网环境里使用固定版 Ghidra runtime 做稳定交付

## 核心约束

1. 这是本地 headless 反编译工作流，不依赖公网分析服务。
2. 若用户还没给出样本路径，先问一个最小必要问题，再继续。
3. 首次处理某个样本时，必须先调用 `import_binary`。
4. 先用 `search_symbol` / `list_functions` 缩小范围，再用 `decompile_function`。
5. `export_strings` 默认只返回一小页预览，并把筛选结果落到 artifact 文件。优先使用 `query` / `offset` 缩小范围，不要把大量字符串原样贴进对话。
6. 若 Java 21 或 bundled runtime 不可用，直接说明缺失项；若 MCP 返回 `missing_jdk` / `unsupported_jdk`，明确提示用户需要 JDK 21+，不要编造结果。

## MCP 动作

- `import_binary`
- `list_functions`
- `decompile_function`
- `export_strings`
- `search_symbol`

## 工作流

1. 确认输入样本。
   - 优先使用用户明确给出的文件路径。
   - 若工作目录中已有明显目标样本，可在说明假设后直接处理。

2. 导入样本。
   - 首次处理时调用 `import_binary`。
   - 记住返回的 `program_id`，后续动作都基于这个 `program_id`。

3. 做范围收缩。
   - 按关键词找函数或命名符号，优先 `search_symbol`。
   - 需要浏览函数总体结构时用 `list_functions`。
   - 需要 IOC / 常量 / 明文线索时用 `export_strings`。
   - 优先带上 `query`，只看小页预览；若命中很多，再用 `offset` 翻页。
   - 若返回里带 `artifact_path`，把它当成全量筛选结果的落盘工件，不要把整份文件内容直接塞进上下文。

4. 做函数级反编译。
   - 已知函数名时直接按名字反编译。
   - 只有入口地址时按地址反编译。
   - 若同名函数较多，先把候选列给用户，再选目标继续。

5. 组织输出。
   - 说明导入对象和 `program_id`
   - 说明你是如何定位到目标函数或符号的
   - 给出反编译结果中的关键逻辑、调用关系、常量或字符串线索
   - 若结果不稳定或存在自动分析误差，要明确标注

## 输出格式

```text
分析对象
- 样本:
- program_id:

定位过程
- 使用的动作:
- 命中的函数 / 符号:

反编译结论
- 主要逻辑:
- 关键常量 / 字符串:
- 值得继续跟进的位置:

限制与风险
- 若有自动分析偏差、符号缺失或未命中，明确说明
```

## 护栏

- 不要在没导入样本时直接假设 `program_id`。
- 不要把整页函数列表原样塞给用户；要先做筛选和归纳。
- 不要把大批字符串原样贴给用户；优先返回关键词命中、代表性样本和 artifact 路径。
- 不要把反编译输出当成绝对真相；遇到可疑的栈变量、类型或控制流要提示可能受自动分析影响。
- 若样本过大或函数过长，先给摘要，再按用户指定函数继续深入。
