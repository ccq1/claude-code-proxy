# 攻击路径推演

## 1. 插件定位

`attack-path-mapper` 用于把 foothold、身份权限关系、资产拓扑和 ATT&CK 技术链组织成可执行攻击路径，帮助用户评估横向移动、提权与关键资产触达路线。

## 2. 目录结构

```text
attack-path-mapper/
├── .claude-plugin/plugin.json
├── config/runtime.json
├── skills/attack-path-mapper/
│   ├── SKILL.md
│   ├── references/
│   │   ├── REFERENCE_INDEX.md
│   │   └── attack/enterprise-attack.json
│   └── scripts/lookup_attack_stix.py
├── assets/icon.svg
└── README.md
```

## 3. 工作流程

```text
[扫描工作目录]
      |
      v
[识别起点 / 目标 / 约束]
      |
      v
[抽取身份边 / 服务边 / 资产边]
      |
      v
[组合候选攻击链]
      |
      v
[映射 ATT&CK 技术]
      |
      v
[输出推荐路径与备选路径]
```

## 4. 离线模式

- 插件自带 `skills/attack-path-mapper/references/attack/enterprise-attack.json`
- 支持 `skills/attack-path-mapper/scripts/lookup_attack_stix.py`
- 默认可在隔离环境中完成 ATT&CK 富化

## 5. 使用方式

- `/attack-path-mapper 根据这个目录里的导出结果，推演从当前权限到域控的路径`
- `/attack-path-mapper 帮我把这组凭据、会话和主机关系整理成可执行攻击链`
- `/attack-path-mapper 结合 ATT&CK 给我做一版主路径和备选路径`

## 5.1 一键生产模式

```bash
cd skills/attack-path-mapper
python scripts/build_attack_paths.py --workdir <your_case_dir> --start <start_node> --target <target_node>
```

## 6. 输出内容

- 推荐攻击路径
- 备选路径与阻塞点
- 每一步的前置条件、证据强度和检测面
- `ATT&CK Mapping`
- `References Used`

## 7. 注意事项

- 不要把理论可能性直接写成确认路径。
- 大图数据和大 STIX 文件优先用 helper script、`rg`、`jq` 做局部查询。
- 每一步都应标注 `confirmed`、`likely` 或 `speculative`。
