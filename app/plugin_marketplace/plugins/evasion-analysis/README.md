# 沙箱对抗分析

## 1. 插件定位

`evasion-analysis` 用于识别样本中的反沙箱、反调试、反虚拟机、环境探测与延时触发逻辑，帮助用户判断哪些检查真正影响载荷释放，哪些只是噪声或降噪手段。

## 2. 目录结构

```text
evasion-analysis/
├── .claude-plugin/plugin.json
├── skills/evasion-analysis/
│   ├── SKILL.md
│   └── references/REFERENCE_INDEX.md
├── assets/icon.svg
└── README.md
```

## 3. 工作流程

```text
[扫描工作目录]
      |
      v
[定位样本 / 报告 / trace]
      |
      v
[搜索反沙箱 / 反调试线索]
      |
      v
[区分硬门槛 / 软门槛 / 噪声]
      |
      v
[分析触发后果]
      |
      v
[输出规避能力总结与复现建议]
```

## 4. 使用方式

- `/evasion-analysis 帮我看这个目录里的样本有没有反沙箱和反调试`
- `/evasion-analysis 这个样本的反虚拟机和延时触发逻辑是什么`
- `/evasion-analysis 给我总结一下需要补哪些环境才能触发真实行为`

## 5. 输出内容

- `Evasion Summary`
- `Key Checks`
- `Reproduction Priorities`
- `References Used`

## 6. 注意事项

- 不是所有 `sleep` 或环境探测都等于真正规避。
- 应解释每个检查怎样影响真实行为，而不是只堆 API 名称。
- 若没有插件内置静态 reference 参与分析，要明确说清楚。
