---
name: evasion-analysis
description: 分析样本中的反沙箱、反调试、反虚拟机、延时触发和环境探测逻辑。
---

# 沙箱对抗分析

## 何时使用

当用户要回答下面这些问题时使用本 skill：
- 样本是否存在反沙箱、反调试、反虚拟机或环境探测逻辑
- 哪些检查会真正阻断载荷释放，哪些只是噪声或降噪手段
- 需要补哪些环境、伪造哪些对象，才能触发真实行为
- 绕过这些逻辑后，最该重点观察哪些后续动作

## skill 基目录约定

本 skill 加载后，以下路径都相对于 skill 基目录：
- `references/REFERENCE_INDEX.md`

这个插件默认**不自带 ATT&CK 或反沙箱静态镜像**。如果用户问“有哪些 reference”，优先枚举：
1. 当前工作目录中的样本、trace、报告和笔记
2. 同目录中的本地 ATT&CK、沙箱笔记或逆向手册
3. 同目录下其他插件已生成的分析结果

## 工作目录优先

优先扫描：
- 样本文件
- 字符串导出
- API trace
- 沙箱报告
- 调试笔记
- 反汇编摘录

规则：
- 有明显主输入就直接开始。
- 多份候选时，优先选最接近用户问题、内容最完整的一组。
- 引用证据优先使用相对路径。

## 大文件策略

对大 trace、大沙箱 JSON 和长字符串转储：
1. 先用 `rg -n` 找环境探测、反调试、时间延迟、厂商字符串、注册表路径、设备名。
2. 再读取附近的局部片段。
3. 不要整份 trace 或报告通读。

## 核心工作流

1. 识别规避类别。
   - 反沙箱
   - 反调试
   - 反虚拟机
   - 环境探测
   - 延时执行
   - 载荷解锁前置条件

2. 判断影响级别。
   - `硬阻断`：不满足就不释放核心行为
   - `软信号`：影响分支或降噪
   - `噪声`：只是信息采集，未必改变主行为

3. 关联触发后果。
   - 哪个检查决定是否联网、解密、注入、落地或持久化
   - 绕过后最可能出现哪些后续动作

4. 给最小绕过建议。
   - 优先推荐最小环境补齐、最小补丁或最小伪造动作

## 输出格式

```text
Evasion Summary
- Overall judgment:
- Hard gates:
- Soft gates:
- Noise:

Key Checks
- Check:
  evidence:
  impact:
  bypass idea:

Reproduction Priorities
- Priority 1:
- Priority 2:

References Used
- Working directory evidence:
- Additional local materials:
- Bundled references:
```

## 护栏

- 不是所有 `sleep`、时间判断和环境信息采集都等于真正规避。
- 不要只堆 API 名称，要解释这些逻辑怎么影响真实行为。
- 如果本轮没有用到插件自带静态 reference，要明确说未使用。
