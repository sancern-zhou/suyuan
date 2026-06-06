# PPT Deck V2 Checklist

## P0 结构检查

- 已读取 `index.md`、`archetypes.md`、对应 deck 类型文档和本 checklist。
- `version` 必须是 `suyuan.deck.v2`。
- 每页使用 `archetype`，不使用 `type`。
- 不传 `title`、`bullets`、`table`、`image_full` 这类底层 slide type。
- 每页只表达一个核心 `message`。
- 内容页不能只有标题和长段文字。
- 内容页必须提供 `content.items`、`content.steps`、`metrics`、`chart`、`table` 或 `visual`。
- 页面标题优先控制在 24 个中文字符内。

## 视觉选择检查

- 三个并列能力用 `three_column_points`。
- 时间顺序用 `timeline`、`roadmap` 或 `implementation_plan`。
- 系统组成用 `architecture_overview`。
- 业务闭环用 `process_flow`。
- 表格证据用 `evidence_table`。
- 责任主体用 `responsibility_matrix`。

## 失败信号

- 全部页面都是 `key_message`。
- 内容大量堆在 `content.bullets`。
- 没有指标、图表、表格、图片或结构化步骤。
- 标题像段落。
- 一页试图同时讲背景、建设内容、预算和保障。
