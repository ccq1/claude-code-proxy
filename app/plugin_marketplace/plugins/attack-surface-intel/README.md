# 目标攻击面情报

## 1. 插件定位

`attack-surface-intel` 用于把资产清单、域名、IP、URL、证书、IOC 与样本索引等材料转化为攻击面情报结果，帮助团队快速发现高价值入口与可疑暴露面。

## 2. 目录结构

```text
attack-surface-intel/
├── .claude-plugin/plugin.json
├── skills/attack-surface-intel/
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
[定位资产 / IOC / 证书 / 扫描结果]
      |
      v
[归一化域名 / IP / URL / 组织名]
      |
      v
[构建基础设施关联]
      |
      v
[区分事实 / 关联 / 推断]
      |
      v
[输出高价值入口与验证建议]
```

## 4. 离线模式

- 默认先用工作目录材料
- 可选使用 `intelWorkspace`
- 可接内部情报服务
- 不默认依赖公网

## 5. 使用方式

- `/attack-surface-intel 根据这个目录里的资产和 IOC，给我做一份攻击面情报研判`
- `/attack-surface-intel 看看这个目标有哪些高价值入口和可疑暴露面`
- `/attack-surface-intel 帮我把这个目录里的域名、证书和扫描结果串起来`

## 6. 输出内容

- `Target Surface Summary`
- `Evidence Table`
- `Recommended Next Actions`
- `References Used`

## 7. 注意事项

- 共享证书、共享 ASN、共享云资源不等于强归属。
- 需要显式区分 `Facts`、`Pivots`、`Hypotheses`。
- 只有在用户明确要求且环境允许时，才使用远程情报源。
