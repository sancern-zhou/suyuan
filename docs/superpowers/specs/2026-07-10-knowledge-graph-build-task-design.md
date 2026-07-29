# 知识库级图谱构建任务设计规格

## 目标

为每个知识库提供可重复、可观测、可重试的图谱构建任务，补齐已有文档的图谱补建能力，同时继续复用现有 Chunk、实体、关系、Mention、PostgreSQL 事实源和 Outbox。文档摄取产生的增量构建与手动全库补建使用同一套抽取和写入逻辑。

## 背景与边界

当前文档摄取会对新增或变化 Chunk 自动抽取图谱，但 Agent 的 `mode=graph` 只有 `knowledge_graph_query` 查询工具，没有启动构建任务的能力；现有 `graph/reindex` 只重建已有实体/关系的 Qdrant 派生索引，不会扫描 Chunk 进行抽取。本规格增加知识库级构建任务，不把 Qdrant 作为事实源，也不新增第二套图谱数据库。

本次不改变：

- 文档原位替换、generation 防护和 Mention 引用清理规则。
- 每个知识库独立图谱和统一 PostgreSQL 事实模型。
- Agent 查询工具的返回格式。
- 旧认知地图 JSON 迁移和运行时下线策略。

## 任务模型

构建任务以知识库为粒度，同一 `kb_id` 同时只能有一个 active 任务。任务状态为 `queued`、`running`、`completed`、`partial`、`failed`、`cancelled`。任务记录至少包含：

- `kb_id`、任务 ID、创建者、创建时间和完成时间。
- `total_chunks`、`processed_chunks`、`failed_chunks`、`remaining_chunks`。
- `last_error` 和失败 Chunk ID 列表或可分页错误明细。
- 构建模式：`pending`（只处理未完成 Chunk）或 `reset_and_build`。

任务实现复用现有后台任务/生命周期机制，不在 HTTP 请求中执行长时间 LLM 调用。创建任务时通过数据库或任务队列的唯一约束防止同一知识库重复运行。

## 构建流程

### Pending 构建

1. 校验知识库存在、图谱已启用且调用者具有管理权限。
2. 查询该知识库 `graph_status != completed` 的 Chunk，快照总数。
3. 后台 worker 以受控并发调用现有 `KnowledgeGraphExtractor`。
4. 每个 Chunk 的抽取结果在短事务内写入统一 Graph Repository：实体按 `(kb_id, entity_type, normalized_name)` 去重，关系按 `(kb_id, source, relation_type, target)` 去重，Mention 记录 Chunk 证据。
5. 同一事务写实体、关系和 Outbox；Qdrant 只由 Outbox worker 更新。
6. 成功后标记 Chunk `graph_status=completed`；失败只标记该 Chunk `graph_status=failed` 和错误，不影响其他 Chunk。
7. 任务结束时重新统计 pending/failed 数，全部成功则 `completed`，存在失败则 `partial`。

已经完成的 Chunk 不重复抽取；文档替换产生的新 generation 由现有 stale generation 防护拒绝旧任务写入。

### Reset and Build

`reset_and_build` 在启动任务前清理该知识库的图谱派生事实、Mention 和图谱 Outbox/Point，但保留知识库、原文档和 Chunk；然后将所有 Chunk 标记为待构建并执行 pending 流程。该操作必须是显式管理操作，并拒绝与摄取或其他图谱任务并发执行。

## API

路由前缀：`/api/knowledge-base/{kb_id}/graph/build`。

- `POST /`：创建构建任务。请求支持 `mode=pending|reset_and_build`、`batch_size`，返回 `202`、任务 ID 和初始状态；存在 active 任务返回 `409`。
- `GET /`：返回当前或最近一次任务状态、计数、错误摘要和更新时间；没有任务时返回空状态与当前 pending 统计。
- `POST /retry`：仅重置失败 Chunk 为 pending 并创建新的 pending 构建任务；已有 active 任务返回 `409`。
- `POST /cancel`：请求取消 queued/running 任务，worker 在 Chunk 边界检查取消信号并把任务标为 `cancelled`。

所有写操作复用知识库管理权限；查询状态至少需要知识库检索权限。API 不接受任意 KB 列表，所有任务严格绑定单个 `kb_id`。

## Agent 与前端

知识库图谱工作台显示：当前配置、pending/failed/完成数量、最近任务状态、进度和错误列表，并提供“构建待处理”“重试失败”“重置并重建”“取消”操作。工作台操作调用上述 API，不在浏览器中执行抽取。

`mode=graph` 的 Agent 仍以查询和解释为主。当请求语义明确要求构建时，Agent 必须要求或使用当前选定的单个知识库，并通过受控任务入口提交构建；没有选定知识库时返回选择知识库提示，不调用 `knowledge_graph_query` 冒充构建。

## 并发、失败与恢复

- 知识库级 active 锁防止两个构建任务同时扫描和写入。
- Chunk 级事务失败可独立重试；已成功 Chunk 不重复处理。
- worker 崩溃后，任务租约超时可恢复为 queued/running；Outbox 自身继续使用现有 processing lease 恢复机制。
- LLM 抽取失败不删除已有事实；文档替换/删除仍由现有 generation 和 Mention 清理流程负责。
- Qdrant 不可用只影响 Outbox 派生索引，事实事务仍可提交，任务状态记录索引 backlog 而不是回滚事实。

## 验收标准

- 已有 Chunk 可以通过 pending 构建任务产生实体、关系、Mention 和 Outbox。
- 重复提交同一知识库构建返回 `409`，任务完成后再次提交只处理新增 pending Chunk。
- 单个 Chunk 失败时其他 Chunk 成功，任务为 `partial`，retry 只处理失败 Chunk。
- reset and build 不删除原文档和 Chunk，且旧图谱事实不会残留。
- 构建任务状态和进度可被前端轮询，API 权限按知识库隔离。
- Agent 在未选知识库时不会把查询工具当作构建工具调用。
- 现有文档摄取增量测试、融合检索测试、前端图谱测试继续通过。
