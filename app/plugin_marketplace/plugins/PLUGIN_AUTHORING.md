# PandoraQ 插件市场新建插件指南

这份文档是当前 `plugin_marketplace/plugins/` 的标准构造约定，目标是让新插件默认就满足 PandoraQ / Claude Code 的加载方式，避免再踩目录结构、MCP 协议和 metadata 漂移的坑。

## 1. 推荐目录结构

```text
my-plugin/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── .cursor-plugin/plugin.json
├── .mcp.json
├── skills/my-plugin/
│   └── SKILL.md
├── commands/
│   └── my-plugin.md
├── scripts/
│   └── my_mcp_server.py
├── config/
│   └── runtime.json
├── assets/
│   └── icon.svg
└── README.md
```

最小可用集通常是：

- `.claude-plugin/plugin.json`
- `skills/<skill-name>/SKILL.md`
- `README.md`

如果插件要暴露本地工具，再加：

- `.mcp.json`
- `scripts/`

如果插件需要 slash command，再加：

- `commands/`

## 2. 几条硬规则

1. `skill` 是主入口，`commands/` 只是可选入口。
2. 有 MCP server 时，优先使用标准 `FastMCP`，不要自己手写 `stdio` 协议循环。
3. `.claude-plugin/plugin.json` 里的 `settingsSchema.placeholderToken` 必须和 `.mcp.json`、`config/runtime.json` 中的占位符一致。
4. `name`、`version`、`publisher`、`description` 这些核心 metadata 尽量以 manifest 为单一事实来源，不要在 `store.py` 再手写一份。
5. `README.md` 讲清楚插件定位、依赖、目录结构和运行链路；`SKILL.md` 讲清楚 agent 的执行合同和约束。

## 3. manifest 约定

### `.claude-plugin/plugin.json`

这是 PandoraQ / Claude Code 侧最关键的 manifest，至少应包含：

```json
{
  "name": "my-plugin",
  "version": "0.1.0",
  "description": "一句话说明插件做什么。",
  "author": {
    "name": "PandoraQ Labs"
  },
  "skills": ["./skills/my-plugin"],
  "mcpServers": "./.mcp.json",
  "settingsSchema": {
    "title": "插件配置",
    "description": "用于把用户填写的配置注入到本地 MCP server。",
    "fields": [
      {
        "key": "workspaceRoot",
        "label": "工作目录",
        "type": "text",
        "required": false,
        "placeholderToken": "WORKSPACE_ROOT"
      }
    ]
  }
}
```

### `.codex-plugin/plugin.json`

如果这个插件要进入你当前的 `llm_proxy` 插件市场，建议同时维护 `.codex-plugin/plugin.json`，因为 `store.py` 的 `_build_manifest_backed_catalog_entry()` 会从 `.claude-plugin` 和 `.codex-plugin` 读取展示 metadata。

这里的重点不是内容更多，而是把 `interface.displayName`、`interface.shortDescription`、`interface.longDescription`、`developerName` 这些 UI 字段补齐。

### `.cursor-plugin/plugin.json`

如果要兼容 Cursor，再补这一份；描述、版本、技能和 MCP 配置要和前两份保持一致，不要三份文案分叉。

## 4. MCP server 标准写法

`.mcp.json` 推荐写成下面这样：

```json
{
  "mcpServers": {
    "my-plugin": {
      "type": "stdio",
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/my_mcp_server.py"],
      "env": {
        "WORKSPACE_ROOT": "{{WORKSPACE_ROOT}}",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

关键点：

- 一定要写 `"type": "stdio"`
- 插件内脚本优先用 `${CLAUDE_PLUGIN_ROOT}`，不要赌当前工作目录
- 配置项通过 `{{PLACEHOLDER}}` 从 `settingsSchema` 注入
- 如果 server 本身依赖固定工作目录，再考虑 `cwd`

Python server 推荐最小骨架：

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-plugin")

@mcp.tool()
def ping() -> dict:
    return {"ok": True}

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

不要再自己实现 `initialize`、`tools/list`、`Content-Length` 或裸 stdin 读写协议；Claude Code 和 PandoraQ 的兼容性成本太高。

## 5. SKILL 和 commands 的边界

`SKILL.md` 应该写：

- 何时使用这个 skill
- 推荐调用顺序
- 关键约束
- 缺失依赖时如何报错

`commands/*.md` 只在你明确要给用户提供 slash command 时才加。没有这个需求时，不要为了“看起来完整”硬加一个 `commands/` 目录。

## 6. 接入 `store.py`

插件目录建好后，还要把它接进 [store.py](../store.py)：

1. 在 `PLUGIN_CATALOG` 里加条目。
2. 新插件优先走 `_build_manifest_backed_catalog_entry()`。
3. `overrides` 里只保留 marketplace 特有字段，比如：
   - `tags`
   - `installable`
   - `kind`
   - `iconPath`
   - `iconText`
   - `slashCommands`
4. 不要再在 `store.py` 里重复写 `name`、`version`、`publisher`、`description`、`settingsSchema`。

推荐模式：

```python
"my-plugin": _build_manifest_backed_catalog_entry(
    "my-plugin",
    overrides={
        "tags": ["标签1", "标签2"],
        "installable": True,
        "kind": "skill-plugin",
        "iconPath": "/plugins/my-plugin/assets/icon.svg",
        "iconText": "MP",
        "slashCommands": [
            {
                "name": "my-plugin",
                "forwardName": "my-plugin:my-plugin",
                "description": "一句话说明 slash command 做什么。",
            }
        ],
    },
),
```

## 7. 推荐验证流程

新插件建完后，至少做这几步：

1. `python3 -m py_compile scripts/*.py`
2. `python3 - <<'PY'` 解析三份 `plugin.json` 和 `.mcp.json`，确认 JSON 合法
3. 本地用 `claude -p --debug-file /tmp/plugin_debug.txt "Return exactly ok"` 启一次
4. 检查 debug 日志里是否出现 `Successfully connected (transport: stdio)`
5. 如果有工具，再确认 `hasTools: true`

## 8. 一句话经验

- 先把 `skill` 做扎实，再决定要不要 `commands/`
- 先把 `FastMCP` 跑通，再往里塞复杂业务逻辑
- 先让 manifest 成为单一事实来源，再把 marketplace 展示层挂上去
