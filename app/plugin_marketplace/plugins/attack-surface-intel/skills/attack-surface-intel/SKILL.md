---
name: attack-surface-intel
description: 将域名、IP、URL、资产清单、IOC 和基础设施线索整理为离线优先的攻击面情报结果。
---

# 攻击面情报研判

## 何时使用

当用户要回答下面这些问题时使用本 skill：
- 哪些域名、IP、URL、证书或服务最值得优先验证
- 哪些暴露面可能成为初始入口
- 哪些基础设施是真实归属，哪些只是共享资源或噪声
- 现有材料里哪些是事实，哪些只是可继续 pivot 的线索

## skill 基目录约定

本 skill 加载后，以下路径都相对于 skill 基目录：
- `references/REFERENCE_INDEX.md`

这个插件默认**不自带公网情报镜像**。如果用户问“你有哪些 reference”，应按下面顺序枚举：
1. 当前工作目录中的证据
2. `{{INTEL_WORKSPACE}}`
3. 管理员显式配置的内部服务
4. 本次实际使用到的远程增强源

## 工作目录优先

默认认为用户会把材料放在当前工作目录。

先扫描：
- `domains*`
- `assets*`
- `inventory*`
- `ioc*`
- `hosts*`
- `cert*`
- `nmap*`
- `*.csv`
- `*.json`
- `*.txt`

规则：
- 如果有一组明显主输入，直接开始，不先追问参数。
- 如果候选很多，选最完整、最贴近用户问题的一组，并在开头说明假设。
- 引用证据优先使用相对路径。

## 离线优先

优先使用：
- 本地资产清单和 CMDB 导出
- 本地 IOC JSON / CSV / 文本导出
- 证书快照、DNS 导出、扫描结果
- 样本索引、沙箱报告、内部事件笔记
- `{{INTEL_WORKSPACE}}` 中已存在的材料

只有用户明确要求且环境允许时，才使用远程情报源。不要因为 skill 里提到增强来源，就主动访问公网。

## 大文件策略

对大型资产清单、扫描结果和 JSON 导出：
1. 先用 `rg -n` 或文件名模式锁定域名、IP、组织名、证书主题等关键字段。
2. JSON 再用 `jq` 或局部 Python 读取目标对象。
3. 只读取需要的片段，不整文件灌进上下文。

## 核心工作流

1. 归一化输入。
   - 统一域名、URL、IP、CIDR、组织名、证书主题和哈希。
   - 区分目标自有资产、第三方服务、CDN 和共享 SaaS。

2. 构建基础设施关联。
   - 结合域名、IP、证书、Banner、端口、组织名、托管商等信息做聚类。
   - 明确哪些是强归属，哪些只是弱关联。

3. 排序高价值入口。
   - 按可达性、认证暴露、可验证性和业务相关性排序。
   - 优先推荐低噪声验证路径。

4. 明确证据等级。
   - `Facts`：直接观察到、可复验。
   - `Pivots`：和目标相关，但仍需确认。
   - `Hypotheses`：基于证据推断的方向。

## 输出格式

```text
Target Surface Summary
- Scope anchor:
- Highest-value ingress candidates:
- Shared infrastructure or pivots:
- Historical or noisy observations:

Evidence Table
- Indicator:
  type:
  observation:
  confidence:
  next validation step:

Recommended Next Actions
- Action 1:
- Action 2:
- Action 3:

References Used
- Working directory evidence:
- Configured local workspace:
- Internal services:
- Remote enrichment actually used:
```

## 护栏

- 共享证书、共享 ASN、共享云资源本身不等于强归属。
- 历史数据、缓存数据和推断必须显式标注。
- 不要把单一信誉信号直接写成高置信结论。
- 若用户要求主动验证，先给最低噪声的验证动作。
