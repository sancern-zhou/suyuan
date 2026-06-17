# Process Diagram Template

适用于业务流程、审批流程、任务执行步骤和顺序链路。目标是表达“先做什么、再做什么、哪里分支、如何结束”。

## P0 硬规则

- 流程必须有明确起点和终点。
- 主路径应一眼可读，分支不能压过主路径。
- 判断节点必须用 `diamond`，边必须写条件标签。
- 超过 8 步时拆阶段，每个阶段用 `group`。
- 每个节点用动词短语，不写整句说明。

## 结构模型

常见结构：

- 线性流程：开始 -> 步骤 1 -> 步骤 2 -> 结束。
- 阶段流程：申请阶段 -> 审核阶段 -> 执行阶段 -> 归档阶段。
- 带回退流程：提交 -> 审核 -> 通过/退回 -> 修改后重提。
- 并行流程：主流程保持单线，旁路只画关键同步点。

## 推荐布局

- `direction="TB"`：审批、诊断、任务链路。
- `direction="LR"`：横向阶段、生产流水线、报告生成链路。
- 主路径用实线，异常/回退用虚线。

## 推荐参数

- `diagram_type`: `process`
- `direction`: 默认 `TB`，阶段型用 `LR`
- `steps`: 普通步骤 `rect`，判断 `diamond`，开始/结束 `stadium`
- `edges`: 条件分支必须带 `label`

## 示例

```json
{
  "steps": [
    {"id": "start", "label": "接收申请", "shape": "stadium", "group": "提交"},
    {"id": "check", "label": "材料完整？", "shape": "diamond", "group": "审核"},
    {"id": "approve", "label": "审批通过", "shape": "rect", "group": "审核"},
    {"id": "fix", "label": "补充材料", "shape": "rect", "group": "退回"},
    {"id": "end", "label": "归档办结", "shape": "stadium", "group": "完成"}
  ],
  "edges": [
    {"from": "start", "to": "check"},
    {"from": "check", "to": "approve", "label": "是"},
    {"from": "check", "to": "fix", "label": "否", "style": "dashed"},
    {"from": "fix", "to": "start", "label": "重提", "style": "dashed"},
    {"from": "approve", "to": "end"}
  ]
}
```

## 视觉要求

- 流程图默认采用传统 draw.io 风格：白色画布、细边框节点、明确箭头和短标签。
- 主线尽量保持一条直线或轻微折线。
- 分支只在判断节点处分出，避免任意节点多叉。
- 回退线使用虚线，减少视觉压迫。
- 边标签短到 1-4 个字，例如“是”“否”“超标”“通过”。

## 禁止事项

- 不要把系统分层、组织结构或模块架构误判成流程。
- 不要把说明文字堆进节点；规则说明放在图外正文，图表本身不渲染底部说明。
- 不要生成没有终点的流程。
