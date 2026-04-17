# 红队知识库

## 1. 插件定位

`redteam-kb` 用于连接私有红队知识库，帮助 Agent 快速检索工具代码、文章、PoC、配置片段与证据文件，适合技术调研、证据定位与实现比对。

## 2. 目录结构

```text
redteam-kb/
├── .claude-plugin/plugin.json
├── skills/redteam-kb/SKILL.md
├── assets/icon.svg
└── README.md
```

## 3. 工作流程

```text
[用户问题 / 关键词]
        |
        v
[skill 入口加载]
        |
        v
[知识库搜索粗筛]
        |
        v
[detail/tree/file/grep 精确确认]
        |
        v
[整理证据与结论]
```

## 4. 使用方式

- `/redteam-kb 检索和 Kerberoast 相关的工具实现与文章证据`
- `/redteam-kb 查找项目里是否有 RDP 横向移动的脚本或说明`
- `/redteam-kb 帮我搜 mimikatz 相关的代码片段和使用说明`

## 5. 输出内容

- 最相关的候选项目或文章
- 命中的文件路径、片段位置或摘要
- 证据与结论的对应关系
- 下一步值得继续展开阅读的方向

## 6. 注意事项

- 搜索是关键词检索，不是语义检索。
- 中文查询必须使用 `--data-urlencode`。
- 先粗筛再精读，避免把大量结果直接灌进上下文。
