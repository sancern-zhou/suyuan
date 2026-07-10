# 项目协作说明

## 统一知识库图谱

- 每个知识库拥有自己的图谱；图谱是知识库的结构化索引，不是独立资源。
- PostgreSQL 保存 Chunk、实体、关系、Mention、审核状态和 Outbox，是唯一事实源；Qdrant 只保存可重建的 `chunk/entity/relation` 派生索引。
- 文档新增、原位替换和删除必须通过 `KnowledgeIngestionService`，不得直接写 Qdrant 或独立图谱 JSON。
- 原位替换递增 `content_generation`，复用未变化 Chunk，删除旧文件、消失 Chunk、旧向量和旧 Mention；失败不恢复旧版本。
- 默认图检索只使用 `confirmed/published`，候选内容只在知识库图谱管理页审核。
- Agent 图谱工具接收 `knowledge_base_ids`；不得读取 `backend_data_registry/cognitive_maps`。
- 知识库现有 `can_search/can_manage` 权限同时约束文档、图查询和图编辑。

发布与迁移步骤见 `docs/knowledge-base-graph-operations.md`。
