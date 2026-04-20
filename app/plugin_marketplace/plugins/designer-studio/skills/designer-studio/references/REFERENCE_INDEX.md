# Designer Studio Reference Index

以下路径都相对于 `skills/designer-studio/`：

## Bundled References

- `references/frameworks/tailwindcss/tailwind.min.css`
  - 离线 Tailwind CSS 包（静态版）
  - 用 `install-tailwind` 复制到目标项目

- `references/frameworks/frameworks_index.json`
  - 内置离线框架索引
  - 用 `list-frameworks` / `install-framework` 读取可用框架

- `references/design_index.json`
  - 离线设计样本索引缓存
  - 由 `frontend_offline_tool.py rebuild-index` 生成

- `references/design/<slug>/DESIGN.md`
  - 单个设计样本说明文档
  - 每个样本通常配套 `preview.html` 和 `preview-dark.html`

## Helper Script

- `scripts/frontend_offline_tool.py`
  - 统一入口，支持：
  - `list-frameworks`
  - `install-framework <output_dir> [--framework tailwindcss] [--filename tailwind.min.css]`
  - `install-tailwind <output_dir> [--filename tailwind.min.css]`
  - `list-presets`
  - `search-design <query>`
  - `inspect-design <slug>`
  - `rebuild-index`
  - `inventory-assets --root <path>`

## 使用规则

1. 先框架后样本：先 `install-tailwind` 或 `install-framework`，再按需看 design-md 参考。
2. 本地素材扫描控制范围：`inventory-assets` 只扫明确目录，避免无界递归。
3. 输出结果必须带路径，保证可追溯和可复现。
