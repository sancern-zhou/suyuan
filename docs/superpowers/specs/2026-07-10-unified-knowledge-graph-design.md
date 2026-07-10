# 知识库与知识图谱统一增量架构设计

## 1. 背景

当前系统存在两条相互独立的数据链路：

- 知识库链路将文档解析为 Chunk，只在 PostgreSQL 保存知识库和文档元数据，在 Qdrant 保存 Chunk 正文、稠密向量和稀疏向量。
- 认知地图链路再次上传和解析文件，将实体、关系、证据、审核状态分别保存为 JSON 和 LlamaIndex `SimplePropertyGraphStore`。

这种分离造成同一份资料需要重复上传、重复解析和重复删除，知识库检索无法利用图谱关系扩展召回，图谱也无法稳定回溯知识库 Chunk。认知地图的 `extraction.json`、`evaluation.json` 和 PropertyGraphStore 还可能在编辑后产生版本漂移。

本设计将图谱定义为知识库的结构化索引。文档只进入一条摄取链路，Chunk、实体、关系、证据和向量都归属于同一个知识库，并随文档新增、替换和删除增量变化。

## 2. 已确认决策

1. 每个知识库拥有自己的图谱，图数据和权限均以 `kb_id` 隔离。
2. 跨知识库问答只在查询层融合，不建立跨库共享实体。
3. 文档入库时自动抽取候选实体和关系。
4. 普通 Chunk RAG 在索引成功后即可使用；Agent 图检索默认只使用 `confirmed`、`published`、`merged` 内容，候选内容只用于管理和审核。
5. 删除文档时删除其 Chunk 和图谱来源引用；共享实体不因单个文档删除而直接消失。
6. 自动抽取且失去全部来源的孤儿内容可以清理；人工创建、人工确认或锁定的内容必须保留。
7. 支持同一文档原位替换，通过 Chunk 内容差异只处理受影响部分。
8. 替换时直接以新文件为当前版本，不保留旧版本、不提供回滚，也不保留版本审计历史。
9. 不引入 Neo4j 或 Milvus。PostgreSQL 是唯一事实源，现有 Qdrant 是同一知识库的派生检索索引。
10. 最终取消独立认知地图的数据机制和 Agent 绑定机制，图谱管理并入知识库。

## 3. 目标与非目标

### 3.1 目标

- 一次上传同时完成文档检索索引和图谱增量构建。
- 一次删除或替换同步影响 Chunk、向量、实体/关系引用和图检索结果。
- 所有实体和关系能够回溯到知识库、文档、Chunk 和原文证据。
- 自动抽取结果经过统一审核状态控制，不允许未确认关系进入默认 Agent 图检索。
- 利用现有 Qdrant 对 Chunk、实体和关系进行语义召回，并与图遍历结果融合。
- 保留现有大气领域 Schema、实体编辑、关系编辑、合并、审核和 Agent 指导能力。
- 所有跨 PostgreSQL/Qdrant 操作可重试、可对账，失败时不会把残缺数据标记为可用。

### 3.2 非目标

- 不建设跨知识库全局图谱或跨库实体自动合并。
- 不保存文档历史版本或提供版本回滚。
- 不要求首次上线即实现社区发现、全局摘要等完整 GraphRAG 算法。
- 不把 Qdrant 当作图谱事实源，也不在 Qdrant 中维护关系拓扑。
- 不继续维护一套独立的认知地图上传、存储和绑定产品。
- 不在本阶段引入新的数据库、中间件或分布式事务协调器。

## 4. 方案比较

### 4.1 方案一：PostgreSQL 统一事实源 + Qdrant 派生索引（采用）

PostgreSQL 保存文档 Chunk、实体、关系、来源引用、审核状态和任务状态。Qdrant 在每个知识库现有 Collection 中保存三种带类型的检索记录：`chunk`、`entity`、`relation`。图遍历和引用清理由 PostgreSQL 完成。

优点：

- 复用现有基础设施和权限边界。
- 可以用数据库事务保证 Chunk、图谱引用和审核状态的一致性。
- 不新增双写数据库，运维和迁移成本最低。
- 当前图谱规模下 PostgreSQL 邻接查询足够，后续仍可替换图查询实现。

缺点：

- 复杂多跳查询需要专门设计索引和递归查询。
- Qdrant 与 PostgreSQL 之间仍需幂等任务和对账机制。

### 4.2 方案二：PostgreSQL + Qdrant + Neo4j

PostgreSQL 保存业务元数据和来源引用，Neo4j 保存图拓扑，Qdrant 保存向量。

优点是复杂图查询能力强；缺点是一次写入涉及三个存储系统，恰好放大当前最严重的一致性问题。现有数据规模和查询深度不足以抵消新增运维与同步成本，因此不采用。

### 4.3 方案三：全部保存在 Qdrant Payload

将实体、关系和来源都放入 Qdrant Payload，通过过滤和应用内遍历实现图查询。

优点是存储组件最少；缺点是关系约束、审核事务、引用计数、合并和级联删除难以可靠实现，也会把派生索引误用为事实源，因此不采用。

## 5. 统一架构

```text
KnowledgeBase
  ├─ Document
  │    └─ KnowledgeChunk
  │          ├─ Qdrant point(record_type=chunk)
  │          ├─ EntityMention ──> GraphEntity
  │          └─ RelationMention ──> GraphRelation
  ├─ GraphSchema / GraphBuildConfig
  ├─ GraphEntity ── Qdrant point(record_type=entity)
  └─ GraphRelation ── Qdrant point(record_type=relation)
```

各组件职责如下：

- `KnowledgeIngestionService`：唯一文档摄取入口，编排解析、Chunk 差异、向量索引和图谱抽取。
- `KnowledgeChunkRepository`：保存可追溯 Chunk 正文、位置、哈希和处理状态。
- `KnowledgeGraphRepository`：实体/关系归一化、来源引用、审核和孤儿清理。
- `KnowledgeVectorIndex`：在现有知识库 Qdrant Collection 中维护带 `record_type` 的派生索引。
- `GraphExtractionProvider`：输入单个或一批 Chunk 与知识库 Schema，输出候选实体、关系和证据。
- `KnowledgeRetrievalService`：统一普通 RAG、图语义召回、关系扩散、排名融合和来源恢复。
- `KnowledgeIndexOutboxWorker`：幂等同步 Qdrant，重试失败任务并执行对账。

图谱不再拥有独立文件上传入口。知识库详情页中的“图谱”只是同一知识库数据的结构化管理视图。

## 6. 数据模型

### 6.1 `knowledge_bases` 扩展

新增：

- `graph_enabled: bool`：默认开启；特殊知识库可暂停图抽取，但不改变数据模型。
- `graph_schema: jsonb`：实体类型、关系类型、合法三元组、别名和归一化规则。
- `graph_extractor_config: jsonb`：模型、并发、超时和抽取参数。
- `graph_updated_at: datetime`：最后一次图数据成功变化时间。

原有 `qdrant_collection` 继续表示该知识库唯一 Collection。

### 6.2 `documents` 扩展

新增：

- `content_generation: int`：当前内容代次，仅用于并发任务防护，不代表可回滚版本。
- `ingestion_status: pending | processing | partial | completed | failed`。
- `graph_status: pending | processing | completed | failed | disabled`。
- `processing_error: text`。

替换文档时更新当前 `Document` 行并递增 `content_generation`，不创建历史版本表。

### 6.3 `knowledge_chunks`

Chunk 必须从“只存在 Qdrant”提升为 PostgreSQL 事实数据：

- `id`：UUID。
- `kb_id`、`document_id`。
- `content_generation`。
- `chunk_key`：文档内稳定差异键。
- `content_hash`：规范化正文 SHA-256。
- `chunk_index`。
- `content`、`embedding_text`、`context_prefix`。
- `start_char`、`end_char`、`page_number`、`section_path`、`metadata`。
- `vector_status`、`graph_status`、`last_error`。
- `created_at`、`updated_at`。

唯一约束为 `(document_id, chunk_key)`。`chunk_key` 根据规范化正文哈希和相同正文在文档中的出现序号生成，避免同一段重复出现时发生冲突。

### 6.4 `knowledge_graph_entities`

- `id`：稳定 UUID。
- `kb_id`。
- `entity_type`。
- `name`、`normalized_name`、`canonical_name`、`aliases`、`description`、`attributes`。
- `review_status: candidate | confirmed | rejected | merged | published | archived`。
- `created_by: extractor | user | agent | migration`。
- `locked_by_user: bool`。
- `merged_into_id`。
- `mention_count`。
- `created_at`、`updated_at`。

唯一身份默认使用 `(kb_id, entity_type, normalized_name)`。别名只参与匹配，不直接创建跨类型合并。人工合并后保留 `merged_into_id`，所有查询解析到目标实体。

### 6.5 `knowledge_graph_relations`

- `id`。
- `kb_id`。
- `source_entity_id`、`target_entity_id`。
- `relation_type`、`description`、`attributes`。
- `review_status`、`created_by`、`locked_by_user`。
- `mention_count`。
- `created_at`、`updated_at`。

默认唯一身份为 `(kb_id, source_entity_id, relation_type, target_entity_id)`，关系有方向。Schema 明确声明为对称关系时，归一化端点顺序后再计算身份。

### 6.6 来源引用表

`knowledge_graph_entity_mentions`：

- `entity_id`、`kb_id`、`document_id`、`chunk_id`。
- `evidence_text`、`evidence_start`、`evidence_end`、`page_number`。
- `confidence`、`extractor_name`、`extraction_run_id`。
- 唯一约束 `(entity_id, chunk_id)`。

`knowledge_graph_relation_mentions`：

- `relation_id`、`kb_id`、`document_id`、`chunk_id`。
- 同样的证据位置、置信度和抽取元数据。
- 唯一约束 `(relation_id, chunk_id)`。

Mention 是删除和替换的核心。实体/关系本身表示知识概念，Mention 表示某个 Chunk 对该概念的贡献。

### 6.7 Outbox

`knowledge_index_outbox` 保存 Qdrant 派生索引任务：

- `id`、`kb_id`、`record_type`、`record_id`。
- `operation: upsert | delete`。
- `payload_version`、`payload`。
- `status: pending | processing | completed | failed`。
- `attempts`、`next_retry_at`、`last_error`。

唯一幂等键为 `(record_type, record_id, operation, payload_version)`。

## 7. Qdrant 统一索引

每个知识库只使用现有的一个 Qdrant Collection。所有 Point 共享同一套稠密/稀疏向量配置，并通过 Payload 区分：

```json
{
  "record_type": "chunk | entity | relation",
  "kb_id": "kb_xxx",
  "record_id": "uuid",
  "document_id": "仅 chunk 使用",
  "review_status": "实体和关系使用",
  "content": "用于展示的文本",
  "embedding_text": "用于向量化的文本"
}
```

检索必须显式过滤 `record_type`：

- 普通知识检索只查 `chunk`。
- 图谱种子召回查 `entity` 和 `relation`，并默认过滤可信审核状态。
- 管理端候选搜索可以包含 `candidate`。

Point ID 使用基于 `record_type + record_id` 生成的确定性 UUID，替代当前基于 `document_id + chunk_index` 的整数 ID，确保 Chunk 重排不会误覆盖其他记录。

Qdrant 只是可重建索引。任何 Point 都必须能从 PostgreSQL 重新生成。

## 8. 增量摄取流程

### 8.1 新增文档

```text
上传文件
  → 创建 Document(content_generation=1, processing)
  → 解析并切块
  → 写入 knowledge_chunks
  → 创建 chunk upsert outbox
  → 对新增 Chunk 抽取候选实体/关系/证据
  → PostgreSQL 事务内 upsert 实体、关系和 Mention
  → 创建 entity/relation upsert outbox
  → Worker 同步 Qdrant
  → 更新 Chunk/Document 状态
```

解析或 Chunk 向量化失败时，文档状态为 `failed`，不可用于检索。Chunk 已可检索但图抽取失败时，状态为 `partial`：普通 RAG 可用，图抽取任务自动重试。这样仍是一条状态机，而不是两套上传和管理机制。

### 8.2 原文档直接替换

替换沿用原 `document_id`，不创建历史版本：

1. 保存新原文件并递增 `content_generation`，文档立即进入 `processing`。
2. 解析新文件，生成新 Chunk 集合。
3. 根据 `chunk_key + content_hash` 与当前 Chunk 比较：
   - 未变化：保留 Chunk、向量和 Mention。
   - 新增：插入 Chunk，并执行向量化和图抽取。
   - 修改：按删除旧 Chunk贡献、插入新 Chunk处理。
   - 消失：删除 Chunk 及其所有 Mention，并创建 Qdrant 删除任务。
4. 新文件成为唯一当前原文件，旧原文件立即清理。
5. 不保留旧 Chunk、旧向量、旧 Mention、旧文件或版本元数据。

用户已明确选择直接替换，因此替换失败时不恢复旧文件和旧索引。文档标记为 `failed`，仅保留当前失败信息，用户可以重试或重新上传。所有异步任务携带 `content_generation`；旧代次任务发现代次不匹配时必须停止写入。

### 8.3 删除文档

1. 将文档标记为 `deleting`，阻止新任务写入。
2. 删除该文档的 Chunk Qdrant Point。
3. 删除该文档的 EntityMention 和 RelationMention。
4. 重新计算受影响实体和关系的 `mention_count`。
5. 对失去全部 Mention 的内容执行孤儿规则。
6. 删除 PostgreSQL Chunk、原文件和 Document。
7. 更新知识库统计。

孤儿规则：

- `created_by=extractor` 且从未人工确认/锁定的孤儿关系直接删除。
- 删除关系后，不再被 Mention 或有效关系引用的自动候选实体直接删除。
- 人工创建、人工确认、已发布或锁定内容转为 `archived`，不进入检索，但保留人工知识。
- 一个实体仍被其他文档 Mention 或有效关系引用时必须保留。

### 8.4 删除知识库

删除知识库仍是一个业务动作：先停止摄取任务，再删除该知识库 Qdrant Collection，最后依靠 PostgreSQL 外键级联删除文档、Chunk、图谱和 Outbox。失败状态可重试，不单独保留“图谱删除”入口。

## 9. 审核与人工编辑

抽取结果进入 `candidate`。审核行为如下：

- 确认实体/关系：转为 `confirmed`，立即进入默认图检索索引。
- 发布知识库图谱：将选中的已确认内容转为 `published`；发布不是文档可检索的前置条件。
- 拒绝：转为 `rejected` 并从 Qdrant 图种子索引删除。
- 合并实体：更新目标实体、迁移 Mention、重写关系端点、去重关系，再更新索引。
- 人工编辑：设置 `locked_by_user=true`；后续抽取只能增加 Mention，不能覆盖人工名称、类型、描述和审核状态。

候选内容可以在知识库图谱管理页展示和搜索，但默认 Agent 图检索只允许：

```text
confirmed, published, merged目标
```

普通 Chunk 检索不受图审核状态影响。Agent 输出必须携带 Chunk 来源；图关系只用于扩展和排序，不能替代原文证据。

## 10. 统一检索

查询流程：

```text
用户问题
  ├─ Qdrant record_type=chunk 的稠密/稀疏混合召回
  ├─ Qdrant record_type=entity/relation 的可信图种子召回
  └─ 从普通 Chunk 命中的 Mention 补充图种子
           ↓
      PostgreSQL 按 kb_id 做有限深度关系扩散
           ↓
      通过 Mention 找到相关 Chunk
           ↓
      图路径 Chunk 排名
           ↓
      RRF 融合普通召回和图召回
           ↓
      现有 Reranker（启用时）
           ↓
      返回 Chunk、来源、命中实体/关系和图路径摘要
```

首期图扩散最大深度为 2，最大实体数和关系数有硬限制。图查询通过 `KnowledgeGraphRepository` 封装，初期使用 PostgreSQL 索引查询和应用内有界 BFS；接口保持稳定，以便规模增长后替换实现。

RRF 只融合排名，不把不同检索器的原始分数直接相加。返回结果保留：

- `fusion_sources`：`chunk`、`graph`。
- `matched_entity_ids`、`matched_relation_ids`。
- `graph_paths` 的有界摘要。
- `document_id`、`chunk_id`、页码和原文位置。

跨知识库查询对每个 `kb_id` 独立召回和遍历，再在查询层统一融合。绝不把一个知识库的实体 ID 用作另一个知识库的图种子。

## 11. API 与前端融合

### 11.1 API

保留知识库主资源：

- `POST /api/knowledge-base/{kb_id}/documents`
- `PUT /api/knowledge-base/{kb_id}/documents/{doc_id}/content`：直接替换当前文档。
- `DELETE /api/knowledge-base/{kb_id}/documents/{doc_id}`。
- `POST /api/knowledge-base/search`：统一检索，可配置是否启用图扩展。

图谱成为知识库子资源：

- `GET /api/knowledge-base/{kb_id}/graph/status`
- `GET/PUT /api/knowledge-base/{kb_id}/graph/schema`
- `POST /api/knowledge-base/{kb_id}/graph/query`
- `GET/POST/PATCH/DELETE .../graph/entities`
- `GET/POST/PATCH/DELETE .../graph/relations`
- `POST .../graph/entities/{entity_id}/merge`
- `POST .../graph/retry-failed`
- `POST .../graph/reindex`：从 PostgreSQL 重建 Qdrant 图索引，不重新上传文档。

所有接口复用知识库现有权限校验。管理与写入要求 `can_manage`，查询要求 `can_search`。

### 11.2 前端

知识库详情页统一包含：

- 文档
- 检索测试
- 图谱
- Schema 与审核
- 处理任务/失败重试

上传、替换和删除只出现在“文档”入口。图谱页不再提供独立上传和独立构建按钮，只显示随知识库摄取产生的状态，并允许审核、修正、合并、查询和重试。

现有认知地图可视化、实体/关系编辑和 Graph 对话编辑能力迁入知识库详情页。Agent 不再绑定认知地图 ID，而是使用请求中已有的 `knowledge_base_ids`；工具从这些知识库中查询图谱。

## 12. 迁移策略

迁移分四步进行：

1. 建立 PostgreSQL Chunk/图谱/Outbox 表和统一服务，但旧认知地图保持只读。
2. 将现有知识库 Qdrant Chunk 回填到 `knowledge_chunks`；无法恢复完整位置的记录保留现有 payload，并标记 `metadata_recovered=false`。
3. 将每张现有认知地图导入一张对应知识库：
   - 原文件进入知识库文档。
   - 实体、关系、证据和审核状态导入 PostgreSQL。
   - Schema 导入该知识库 `graph_schema`。
   - 现有 Agent 模式绑定转换为知识库选择配置。
4. 校验数量、来源和查询结果后，删除旧 `backend_data_registry/cognitive_maps` 运行时读取路径和独立 API；旧目录只在部署迁移完成后由人工备份/清理流程移除。

迁移脚本必须可重复执行：每个来源对象带稳定迁移键，重复执行不得创建重复实体、关系或 Mention。

## 13. 一致性与错误处理

PostgreSQL 是提交边界，Qdrant 是最终一致的派生索引：

- 业务事务同时写事实表和 Outbox，不在事务中直接依赖 Qdrant 成功。
- Worker 按幂等 Point ID 执行 upsert/delete，成功后更新状态。
- 查询只使用 `vector_status=indexed` 且审核状态允许的记录。
- 定期对账 PostgreSQL 活跃记录和 Qdrant Point，补建缺失 Point、删除无主 Point。
- 每个任务携带 `content_generation`，防止替换前的旧任务回写。
- 同一文档只允许一个摄取/替换任务运行；同一知识库允许受控并发处理不同文档。

状态语义：

- `completed`：Chunk 与图抽取均完成，派生索引已同步。
- `partial`：Chunk 可检索，但图抽取或图索引仍失败；系统自动重试并明确展示。
- `failed`：当前文档不可检索，需要用户重试或替换。
- `deleting`：不参与新查询，等待清理完成。

禁止以静默 fallback 隐藏索引损坏。系统可以在 `partial` 状态提供普通 RAG，但必须返回并记录图扩展未生效的原因。

## 14. 可观测性

每次摄取记录以下指标：

- 新增、复用、修改、删除 Chunk 数。
- 新增/复用实体数和关系数。
- 新增/删除 Mention 数。
- 候选、确认、拒绝和孤儿清理数量。
- 解析、向量化、图抽取、Qdrant 同步耗时与失败数。
- 普通召回、图召回和融合结果数量。

日志统一携带 `kb_id`、`document_id`、`content_generation`、`chunk_id`、`extraction_run_id`。管理页显示文档级阶段状态和可重试错误，不再分别查看知识库任务与认知地图任务。

## 15. 测试设计

### 15.1 数据模型与仓储测试

- 同一实体在同一知识库内归一化复用，在不同知识库中保持隔离。
- 同一三元组多 Chunk 引用只创建一个关系和多个 Mention。
- 实体合并正确迁移 Mention、关系端点并去重。
- 删除 Mention 后 `mention_count` 和孤儿规则正确。
- 人工锁定内容不被后续自动抽取覆盖。

### 15.2 增量摄取测试

- 新增文档只处理新增 Chunk。
- 原位替换复用未变化 Chunk，只重建变化部分。
- 删除段落撤销对应 Mention，并保留仍被其他文档支持的实体。
- 替换后旧原文件、旧 Chunk、旧向量和旧 Mention不存在。
- 替换任务失败不恢复旧版本，文档进入 `failed`。
- 旧 `content_generation` 任务不能覆盖当前数据。

### 15.3 索引一致性测试

- PostgreSQL 事务回滚时不产生可执行 Outbox。
- Qdrant 暂时失败后重试得到唯一 Point，不重复写入。
- 对账任务可以补齐缺失 Point并删除无主 Point。
- 删除知识库后 Collection 和事实数据均被清理。

### 15.4 审核与权限测试

- Candidate 可在管理端看到，但不进入默认 Agent 图检索。
- Confirmed/Published 立即进入图种子检索。
- Rejected/Archived 不进入检索。
- 普通用户不能修改无管理权限知识库的图谱。
- 多知识库查询不会越过知识库权限或混合实体身份。

### 15.5 检索测试

- 普通 Chunk 检索行为保持兼容。
- 图种子召回和两跳扩散能找到间接相关 Chunk。
- RRF 正确去重并保留融合来源。
- 图索引失败时普通 RAG 可用且明确标记降级原因。
- 返回结果能回溯文档、Chunk、页码和证据片段。

### 15.6 迁移测试

- 现有三张认知地图的实体、关系、审核状态、Schema 和文件数量对账一致。
- 重复运行迁移脚本不产生重复数据。
- 迁移后原有 `ops` 模式能通过知识库选择获取同等图谱指导。

## 16. 验收标准

1. 用户只在知识库上传一次文件，即可同时获得 Chunk 检索和候选图谱。
2. 每个实体和关系都能查询到所属知识库及至少一个来源；人工内容明确标记为人工来源。
3. 新增文档不重建其他文档图谱。
4. 原位替换只处理 Chunk 差异，成功后不存在旧版本数据或回滚入口。
5. 删除文档不会删除仍被其他文档支持的共享实体/关系。
6. 候选关系不会进入默认 Agent 图检索，确认后无需整库重建即可生效。
7. 普通 RAG 与图召回通过同一搜索服务返回统一 Chunk 结果和来源。
8. PostgreSQL 可独立重建全部 Qdrant Chunk、实体和关系索引。
9. 知识库权限同时约束文档检索、图查询和图谱编辑。
10. 现有认知地图数据迁移完成后，运行时不再读取独立 JSON/PropertyGraphStore。
11. 新增、替换、删除、审核、合并、融合检索和迁移关键路径均有自动化测试。

## 17. 实施边界建议

该设计应拆成连续但可独立验收的实施阶段：

1. PostgreSQL Chunk/图谱/Outbox 数据模型与仓储。
2. 统一新增、替换、删除摄取状态机和 Qdrant typed point。
3. 图抽取、Mention 和审核管理迁入知识库。
4. 统一 GraphRAG 检索与 Agent 工具改造。
5. 前端知识库图谱工作台融合。
6. 旧认知地图迁移和旧运行时删除。

每个阶段都必须保持知识库主链路可运行，并在进入下一阶段前完成对应数据一致性测试。
