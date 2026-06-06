# PPT Deck V2 Reference Index

调用 `create_pptx_from_deck` 前，必须先判断 `deck_type`，再读取 `archetypes.md`、对应 deck 类型文档和 `checklist.md`。

## 设计依据

- Agent 负责叙事、业务判断、页面选择和结构化内容。
- 工具负责版式、字体、位置、颜色、渲染和质量校验。
- 先判断整套 PPT 的任务类型，再为每页选择成熟页面视觉类型。
- 不要把 `create_pptx` 的底层 `title`、`bullets`、`table`、`image_full` 传给本工具。

## deck_type

| deck_type | 适用请求 | 必读文档 |
|---|---|---|
| `implementation_proposal` | 实施方案、建设方案、项目二期方案 | `implementation-proposal.md` |
| `government_briefing` | 政府汇报、领导汇报、专题汇报 | `government-briefing.md` |
| `data_analysis_report` | 数据分析、监测分析、趋势研判 | `data-analysis-report.md` |
| `business_report` | 通用经营或业务汇报 | `archetypes.md` |
| `project_plan` | 项目计划、排期、里程碑 | `implementation-proposal.md` |
| `technical_solution` | 技术方案、系统设计 | `implementation-proposal.md` |
| `product_pitch` | 产品介绍、方案宣讲 | `archetypes.md` |
| `research_summary` | 研究总结、调研报告 | `data-analysis-report.md` |

## 调用前四步

1. 写出 `deck_type`。
2. 写出 5-9 页的叙事主线。
3. 为每页选择一个 `slide.archetype`。
4. 检查内容页是否提供 `content.items`、`metrics`、`chart`、`table` 或 `visual`。
