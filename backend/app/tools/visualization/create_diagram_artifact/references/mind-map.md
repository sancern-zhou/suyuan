# Mind Map Template

适用于知识梳理、方案拆解、复盘总结、要点归类。目标是表达“一个中心主题向外发散出哪些分支”，不是表达严格顺序或依赖。

## P0 硬规则

- 必须有一个中心主题；默认使用第一个没有 `parent_id` 的 step。
- 分支节点可用 `parent_id` / `parent` 指向父节点，也可在节点内写 `children` 嵌套分支。
- 每个节点只写短词或短语，不写整句说明。
- 分支层级优先 2-3 层；超过 3 层时拆成多张图或合并节点。
- 不画复杂交叉关系；如果需要表达流向，改用 `process` 或 `data_flow`。

## 推荐参数

- `diagram_type`: `mind_map`
- `direction`: 可省略；模板默认左右发散。
- `steps`: 中心主题和分支节点，字段包含 `id`、`label`、`parent_id`、`children`。
- `edges`: 通常不需要；父子关系由 `parent_id` 表达。

## 示例

```json
{
  "diagram_type": "mind_map",
  "steps": [
    {"id": "root", "label": "项目复盘"},
    {"id": "goal", "label": "目标", "parent_id": "root"},
    {"id": "risk", "label": "风险", "parent_id": "root"},
    {"id": "action", "label": "行动项", "parent_id": "root"},
    {"id": "owner", "label": "责任人", "parent_id": "action"}
  ]
}
```

## 视觉要求

- 使用传统 draw.io 风格：白色画布、中心主题、左右分支、细线连接。
- 中心主题视觉权重最高，一阶分支次之，子分支更轻。
- 左右分支数量尽量均衡；模板会自动交替分配一阶分支。
- 主图必须自解释，不渲染底部说明。

## 禁止事项

- 不要用思维导图表达审批流程、数据流、系统分层或部署拓扑。
- 不要在节点中写长段说明。
- 不要依赖 `edges` 表达交叉引用。
