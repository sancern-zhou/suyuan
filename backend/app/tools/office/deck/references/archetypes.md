# PPT Slide Archetypes

`slide.archetype` 表示成熟 PPT 页面视觉类型，不是底层绘图类型。

## 核心类型

| archetype | 用途 | 推荐字段 |
|---|---|---|
| `cover` | 封面 | `title`, `subtitle` |
| `agenda` | 目录 | `content.items` |
| `section_divider` | 章节页 | `title`, `subtitle` |
| `executive_summary` | 管理摘要 | `message`, `content.items` |
| `key_message` | 单一核心判断 | `message`, `content.items` 或 `visual` |
| `three_column_points` | 三点式能力/价值/问题 | `content.items` 3项 |
| `metric_dashboard` | 指标看板 | `metrics` |
| `comparison_matrix` | 对比矩阵 | `table` |
| `timeline` | 时间线 | `content.steps` |
| `roadmap` | 路线图 | `content.steps` |
| `process_flow` | 流程图 | `content.steps` |
| `architecture_overview` | 架构总览 | `visual.asset` 或 `content.items` |
| `data_flow` | 数据流 | `visual.asset` 或 `content.steps` |
| `map_story` | 地图故事 | `visual.asset`, `message`, `content.bullets` |
| `chart_story` | 图表故事 | `chart` 或 `visual.asset` |
| `evidence_table` | 证据表 | `table` |
| `risk_matrix` | 风险矩阵 | `table` |
| `budget_breakdown` | 投资/预算拆分 | `table` 或 `metrics` |
| `implementation_plan` | 实施安排 | `content.steps` |
| `responsibility_matrix` | 责任分工 | `table` |
| `closing_actions` | 结论和行动 | `content.items` |

## 选择规则

- 有阶段、批次、时间顺序：优先 `timeline`、`roadmap`、`implementation_plan`。
- 有系统组成、平台能力：优先 `architecture_overview`。
- 有流程闭环：优先 `process_flow`。
- 有数字指标：优先 `metric_dashboard` 或 `chart_story`。
- 有对比和清单：优先 `comparison_matrix` 或 `evidence_table`。
- 有风险、问题、保障措施：优先 `risk_matrix`。
