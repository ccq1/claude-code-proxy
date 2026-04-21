---
name: designer-studio
description: 在内网和离线环境中完成前端设计选型与离线 Tailwind 框架分发，避免依赖外网 UI 库与 CDN。
user-invocable: true
argument-hint: "目标项目路径、行业类型、风格偏好（可选）"
---

# 前端离线能力包（Designer Studio）

## 何时使用

当用户要回答下面这些问题时使用本 skill：
- 内网环境做前端，不允许依赖公网 npm/CDN/UI 库
- 需要先选设计风格，再让 Agent 落地页面
- 希望直接复用离线 Tailwind 包，快速进入实现阶段
- 需要在本地素材目录中发现可复用的字体、图标、图片和 CSS 资产

## skill 基目录约定

本 skill 加载后，以下路径都相对于 skill 基目录：
- `references/REFERENCE_INDEX.md`
- `references/design_index.json`
- `references/frameworks/tailwindcss/tailwind.min.css`
- `references/design/<slug>/DESIGN.md`
- `scripts/frontend_offline_tool.py`

说明：
- Agent 只允许读取 `references/design/<slug>/DESIGN.md` 作为风格规范来源。
- `preview.html` 和 `preview-dark.html` 仅供人类手动预览，不允许作为 Agent 的读取输入。
- `scripts/frontend_offline_tool.py` 是插件内部实现细节；默认不要直接 shell 执行它。
- 不要把相对路径 `scripts/frontend_offline_tool.py` 自行展开成绝对路径。
- 若需要确认当前插件真实根目录，先调用 MCP 动作 `server_info`，不要猜测仓库路径。

优先通过 Designer Studio 自带 MCP 动作读取 references，不要凭记忆描述样式，也不要自己拼脚本绝对路径：
- `list_presets`
- `search_design`
- `inspect_design`
- `list_frameworks`
- `install_framework`
- `install_tailwind`
- `inventory_assets`
- `server_info`

## 生产快速路径（默认）

默认先完成“框架接入 + 样式选型”，再进入页面实现：

1. 调用 `install_tailwind` 或 `install_framework` 完成离线框架接入。
2. 调用 `search_design` 找候选风格。
3. 调用 `inspect_design` 读取选中风格的 `DESIGN.md`。

规则：
- 先给可运行的离线框架落地路径，再给风格建议。
- 若用户配置了 `preferredCssPack`，可用 `install-framework` 走默认框架偏好；当前内置包默认仍是 `tailwindcss`。
- 风格建议必须引用实际 `DESIGN.md` 路径。
- 若未找到匹配样式，明确说明并给出最接近候选，不允许捏造来源。

## 工作目录优先

默认认为用户会把项目放在当前工作目录，按以下顺序处理：
- 先识别目标项目目录（包含 `package.json`、`index.html`、`src/`、`app/` 等）
- 把 `tailwind.min.css` 复制到项目静态资源目录（如 `public/`、`assets/`）
- 输出引用方式（HTML `<link>` 或构建链路引入）

如用户提供资产目录，再调用 `inventory_assets` 做素材盘点。

## 大目录策略

对大型本地目录：
1. 先定位前端工程根和静态资源目录。
2. 再执行资产盘点，避免全盘扫描拖慢任务。
3. 只返回“可直接复用”的资源和路径，不输出噪声文件。

## 核心工作流

1. 明确目标页面类型与场景。
   - 例如：管理后台、营销落地页、设置页、工作台。

2. 先完成离线框架接入。
   - 调用 `install_tailwind` 或 `install_framework`，确认输出文件存在。

3. 再做设计样式选型。
   - 调用 `search_design` / `inspect_design`。
   - 引用 `DESIGN.md` 中的颜色、字体、间距和组件规则。
   - 不读取 `preview.html` / `preview-dark.html`；它们只给人类预览。

4. 必要时补充本地资产盘点。
   - 调用 `inventory_assets`，把字体/图标/图片纳入实现方案。

5. 输出可执行实现建议。
   - 必须包含实际文件路径与可落地步骤。

## 输出格式

```text
Execution Summary
- Project root:
- Installed framework file:
- Chosen design preset:

Design Decision
- Style source:
- Why this style fits:
- Key tokens to apply:

Implementation Plan
- Step 1:
- Step 2:
- Step 3:

References Used
- Bundled framework:
- Bundled design docs:
- Local assets (if any):
```

## 护栏

- 不默认建议公网 CDN（除非用户明确要求）。
- 不把 `DESIGN.md` 当作可直接运行代码；它是风格规范来源。
- 不引用不存在的样式文件或路径。
- 不要自行构造 `/root/.../designer-studio/.../frontend_offline_tool.py` 之类的绝对脚本路径。
- 默认只使用本插件的 MCP 动作；不要直接 shell 调用插件内部脚本。
- 若本轮没有使用 references，必须明确说明“未使用内置 references”。
