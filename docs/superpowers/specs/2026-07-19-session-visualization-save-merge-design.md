# 历史会话图表保存合并设计

## 目标

修复 Web 会话续聊时，本轮生成的图表覆盖会话历史图表元数据，导致恢复后右侧面板只显示部分图表的问题。

## 范围

- 只修改保存端的图表元数据合并行为。
- 不修改会话恢复接口，不在恢复时扫描消息补齐图表。
- 不修改 Office 文档保存、恢复或数量上限。
- 不自动修复已经被覆盖的历史元数据；后续保存只基于保存前仍存在的元数据继续合并。

## 设计

`ConversationPersistenceService.append_metadata` 是图表增量合并的唯一实现：读取 `session.metadata.visualizations`，再合并本轮 `collected_visuals`。有 ID 的图表按 ID 去重，同一 ID 使用本轮最新记录；无 ID 图表保留现有兼容行为。

Web 路由的正常完成保存使用 `append_complete`，中断、未完成和异常保存使用 `append_terminal`。新会话的历史元数据为空，因此增量方法与原全量方法结果一致；续聊会话则保留历史图表。

ReActAgent 的 finally 元数据保存不得直接覆盖 `visual_ids` 和 `metadata.visualizations`，而是复用 `ConversationPersistenceService.append_metadata`。这样路由完成保存后，finally 的第二次保存仍保持相同合并语义。

## 数据流

1. 路由加载当前会话及已有 `metadata.visualizations`。
2. SSE 期间只收集本轮图表。
3. 终态保存将已有图表与本轮图表合并并持久化。
4. ReActAgent finally 从数据库重新加载会话元数据，将运行时图表再次按相同规则合并。
5. 现有恢复接口读取完整的会话级图表元数据并返回前端。

## 错误和兼容性

- 空的本轮图表列表不得清空历史 `visual_ids` 或 `metadata.visualizations`。
- 重复 ID 不增加记录数，本轮记录覆盖同 ID 的旧内容。
- 无 ID 图表继续作为匿名记录保存，避免破坏旧格式。
- 对话消息持久化、画板元数据和 Office 文档逻辑保持不变。

## 测试

- `append_complete` 保留历史图表并追加本轮图表。
- `append_terminal` 在异常终态保留历史图表。
- 相同图表 ID 使用本轮最新内容且不重复。
- ReActAgent finally 元数据应用保留数据库已有图表。
- 运行相关会话持久化与 API 测试，确认没有回归。
