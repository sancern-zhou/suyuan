# Decision Tree Template

适用于规则判断、诊断树、条件路径、风险分级。目标是表达“根据什么判断，走向哪个结论”。

## P0 硬规则

- 根节点必须是一个判断问题。
- 判断节点使用 `diamond`，结论节点使用 `rect` 或 `stadium`。
- 每条边必须有条件标签。
- 深度超过 4 层或叶子超过 10 个时，先合并低价值分支。
- 同一层级的问题粒度要一致，不能一边是业务条件，一边是执行动作。

## 结构模型

- 根问题：最能分流的核心条件。
- 中间判断：只放必要二级条件。
- 叶子结论：风险等级、处理建议、下一步动作。
- 例外路径：用虚线或“人工复核”结论收束。

## 推荐布局

- `direction="TB"`：根节点在上，结论在下。
- 若分支很多，先改写为两级判断，不要让一个 diamond 扇出 6 条边。
- 相同结论应复用同一节点，避免重复叶子。

## 推荐参数

- `diagram_type`: `decision_tree`
- 渲染采用工具内置 draw.io 风格模板，不需要指定布局引擎。
- `direction`: `TB`
- `steps`: 判断 `diamond`，结论 `rect`，人工复核 `stadium`
- `edges`: 全部带 `label`

## 示例

```json
{
  "steps": [
    {"id": "root", "label": "是否超标？", "shape": "diamond"},
    {"id": "persist", "label": "连续超标？", "shape": "diamond"},
    {"id": "high", "label": "高风险\n启动排查", "shape": "rect"},
    {"id": "medium", "label": "中风险\n持续观察", "shape": "rect"},
    {"id": "normal", "label": "正常\n归档记录", "shape": "rect"}
  ],
  "edges": [
    {"from": "root", "to": "persist", "label": "是"},
    {"from": "root", "to": "normal", "label": "否"},
    {"from": "persist", "to": "high", "label": "是"},
    {"from": "persist", "to": "medium", "label": "否"}
  ]
}
```

## 视觉要求

- 树的左右两侧保持视觉平衡。
- 条件标签是阅读关键，不能省略。
- 结论节点可用少量色彩区分风险等级，但不要超过 3 种颜色。

## 禁止事项

- 不要把普通顺序流程伪装成决策树。
- 不要让判断节点输出无标签边。
- 不要把一个复杂政策条款拆成十几个并列叶子；先归类。
