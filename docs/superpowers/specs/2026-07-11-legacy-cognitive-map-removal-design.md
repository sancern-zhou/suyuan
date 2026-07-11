# 旧认知地图永久清除设计

## 决策

旧认知地图不保留、不备份、不迁移，永久删除。当前知识库图谱仍复用的抽取模型和 provider 必须先迁入知识库模块并完成引用切换，随后删除整个旧认知地图运行机制。

## 目标状态

- 运行时代码不再引用 `app.agent.cognition`。
- 后端不存在旧认知地图路由、工具、独立构建、站点地图、Spike、视图或评估机制。
- 前端不存在 `CognitiveMap*` 组件、API、工具函数或运行时术语。
- `backend/backend_data_registry/cognitive_maps/` 及其全部文件永久删除。
- 历史迁移脚本和仅服务旧机制的测试删除。
- Python 缓存中的旧模块字节码删除。
- 新知识库图谱的文档抽取、构建、查询、审核、可视化和 Agent 操作保持可用。

## 保留能力的迁移

新建 `backend/app/knowledge_base/graph_extraction/`，承接当前知识库图谱仍使用的通用抽取能力：

- schema、source file、document chunk、extracted entity/relation 和 extraction result 模型；
- LLM factory；
- parser/extractor provider factory；
- text、PDF、DOCX、MarkItDown、local 和 LlamaIndex provider。

类型名称从旧认知地图语义改成知识图谱抽取语义。`KnowledgeGraphExtractor` 和 `KnowledgeIngestionService` 只能引用新目录。迁移完成并通过测试后才能删除 `app/agent/cognition`。

旧机制专属类型 `CognitiveMapQuery`、`CognitiveMapView` 及相关视图构建逻辑不迁移。

## 永久删除范围

### 数据

永久删除：

```text
backend/backend_data_registry/cognitive_maps/
```

包括 `agent_bindings.json`、所有 `cm_*` 目录、原文件、`map.json`、`files.json`、`schema.json`、`extraction.json`、`property_graph_store.json`、`evaluation.json` 和 `build_runs.json`。

### 后端

迁移共享抽取能力后删除：

```text
backend/app/agent/cognition/
backend/scripts/migrate_cognitive_maps_to_knowledge_bases.py
backend/tests/knowledge_base/test_cognitive_map_migration.py
```

删除所有 `cognitive_map_routes` 残留字节码和 cognition `__pycache__`。

### 前端

将 `CognitiveMapGraphChat.vue` 改名为 `KnowledgeGraphChat.vue` 并更新知识库图谱页引用。删除无运行时引用的：

```text
cognitiveMapGraphLinks.js
cognitiveMapHierarchy.js
cognitiveMapRefresh.js
```

删除只验证旧机制的测试；保留并改名仍验证新知识库图谱对话的测试。

### 提示词与上下文

- 将知识库图谱运行上下文中的“认知地图”改为“知识库图谱”。
- 删除禁止访问旧 `cognitive_maps` 目录的临时兼容提示。
- 不修改确实表达一般认知地图概念、且与旧运行机制无关的业务文档，除非其内容指向旧接口或旧目录。

## 执行顺序

1. 为新抽取目录增加导入和契约测试。
2. 迁移共享模型、factory 和 provider。
3. 切换知识库图谱运行时引用。
4. 验证文档图谱抽取和知识库测试。
5. 改名前端图谱对话组件并清理未使用工具。
6. 删除旧后端代码、迁移脚本和测试。
7. 永久删除旧地图数据目录和缓存。
8. 扫描运行时代码，确保不再引用 `cognitive_maps`、`CognitiveMapPanel`、旧路由或 `app.agent.cognition`。
9. 执行后端测试、前端测试和生产构建。

## 安全边界

- 旧地图删除不提供恢复路径。
- 不删除 PostgreSQL 知识库图谱事实表、Qdrant 数据或当前知识库文档。
- 不删除 `knowledge_graph_*` API、构建任务、Outbox、G6 可视化或 Graph Agent 工具。
- 删除前必须先证明新抽取目录已被运行时使用；删除后必须证明旧目录导入会失败且新图谱测试通过。

## 验收

- `rg` 在运行时代码中找不到 `app.agent.cognition`、`cognitive_maps`、`CognitiveMapPanel` 和旧 cognitive map API。
- `backend/backend_data_registry/cognitive_maps` 不存在。
- `backend/app/agent/cognition` 不存在。
- 知识库文档自动图谱抽取测试通过。
- 图谱构建、快照、证据、查询和 Agent 工具测试通过。
- 前端图谱对话、G6 工作台测试和生产构建通过。
