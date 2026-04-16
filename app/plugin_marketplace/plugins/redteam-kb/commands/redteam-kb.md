---
description: 使用红队知识库检索资料和代码证据
allowed-tools:
  - Bash(curl:*)
---

使用红队知识库服务 `{{REDTEAM_KB_BASE_URL}}` 协助当前任务。

执行原则：
1. 优先使用简短、具体的关键词检索。
2. 如果查询包含中文，必须使用 `--get --data-urlencode`。
3. 先用搜索接口粗筛，再根据结果继续 grep、tree 或 file 读取。
4. 回答时给出证据来源，不要只给结论。

常用接口：
- 搜索：`{{REDTEAM_KB_BASE_URL}}/rtkb/api/search`
- 软件列表：`{{REDTEAM_KB_BASE_URL}}/rtkb/api/software`
- 文章列表：`{{REDTEAM_KB_BASE_URL}}/rtkb/api/articles`

示例：
```bash
curl -s --get --data-urlencode "q=mimikatz" "{{REDTEAM_KB_BASE_URL}}/rtkb/api/search?top_k=5"
```
