# 认知地图工作台与 Agent 接入设计

## 背景

当前项目已经具备 ReAct Agent、多专家子 Agent、工具注册、`ExecutionContext`、`DataContextManager`、`TypedDataHandle` 和 UDF v2.0 数据标准化能力。现阶段的主要缺口不是工具数量，而是缺少一个稳定的语义中间层，让 Agent 能一致理解输入数据的含义、组织推理过程，并生成可追溯、有证据支撑的输出。

本设计引入“认知地图工作台”：用户可以主动上传业务文件，由系统抽取候选实体、关系、规则和证据，再由用户审核、修正、发布。发布后的认知地图按任务检索后接入 Agent，为专家分析、报告生成和证据化输出提供语义约束。

## 参考图提炼

参考图体现了三个关键设计原则：

1. **本体骨架与实体图谱并行**
   - 左侧或主区域展示实体关系网络，表达业务对象之间的关联。
   - 右侧展示本体骨架、属性、关系约束、问题诊断或规则分析。
   - 图谱不是只给人看的可视化，而是 Agent 认知输入的结构化来源。

2. **交互式多轮构建**
   - 第 1 轮：用户描述场景，AI 给出初始本体草稿。
   - 第 2 轮：用户补充细节，AI 优化实体、关系、属性和约束。
   - 第 3 轮：用户验证完整关系结构，AI 输出完整 Schema 或图谱结构。
   - 这说明认知地图不应是一次性自动抽取结果，而应支持“候选生成-人工确认-持续修正”的闭环。

3. **分层认知架构**
   - AI 应用层：智能体使用认知地图完成维护、诊断、优化、质量管控等任务。
   - 本体知识层：沉淀设备/工艺/故障/关系/规则等业务知识。
   - 物理或数据层：连接真实设备、监测数据、工具结果、文档证据。
   - 对本项目而言，应对应为“Agent 应用层-认知地图层-数据与工具层”。

## 目标

第一阶段目标是搭建最小可演进框架：

- 支持用户上传文件并构建认知地图草稿。
- 支持实体、关系、证据、规则的候选抽取。
- 支持前端展示、审核、编辑、合并、删除和发布。
- 支持认知地图按任务检索后注入 Agent。
- 支持 Agent 输出结论时引用地图证据和数据证据。
- 支持持续积累和修正实体模型，而不是一次性定义完整领域本体。

## 非目标

第一阶段不做以下内容：

- 不引入独立图数据库作为强依赖。
- 不自建完整知识图谱构建算法体系；优先封装成熟开源项目，项目内只保留稳定适配层。
- 不要求所有工具立即改造成结构化证据输出。
- 不全面改造助手、社交、办公模式。
- 不追求 LLM 自动抽取结果完全正确。
- 不把整张认知地图直接塞进 prompt。
- 不做复杂权限体系，只保留后续扩展字段。

## 总体架构

```text
文件输入
  ↓
文档解析与切块
  ↓
候选实体/关系/规则/证据抽取
  ↓
用户审核与修正
  ↓
发布认知地图版本
  ↓
Agent 按任务检索 CognitiveMapView
  ↓
注入 ExecutionContext / Prompt
  ↓
Agent 生成证据化输出
```

第三方开源能力只接入后端，不嵌入其前端。项目自己的前端工作台、API、数据模型和 Agent contract 保持稳定，开源项目作为可替换 provider：

```text
Vue 认知地图工作台
  ↓
FastAPI Cognitive Map API
  ↓
backend/app/agent/cognition/
  ├─ DocumentParserProvider   # MarkItDown / Unstructured / Docling
  ├─ GraphExtractorProvider   # LlamaIndex Property Graph / Cognee / 自研兜底
  ├─ GraphStoreProvider       # JSON/关系表 / Kuzu / Neo4j / FalkorDB
  └─ ViewBuilder              # 项目内稳定实现，输出 CognitiveMapView
  ↓
Agent ExecutionContext / Prompt / claims.evidence_refs
```

系统分为三层：

```text
Agent 应用层
- query Agent
- expert Agent
- report Agent
- deliberation_* Agent
- call_sub_agent 多专家链路

认知地图层
- CognitiveMap
- Entity
- Relation
- Evidence
- Rule
- Finding
- Hypothesis
- CognitiveMapView

数据与工具层
- UploadedFile
- DocumentChunk
- DataContextManager
- TypedDataHandle
- Tool Observation
- Data Registry
```

## 开源能力封装策略

本项目不直接依赖某个外部知识图谱产品的数据结构，而是在 `backend/app/agent/cognition/providers/` 下封装第三方能力。封装目标是：可以跟随社区项目迭代，同时避免前端、Agent 和业务数据模型被外部项目绑死。

### Provider 边界

```text
DocumentParserProvider
- 输入：SourceFile
- 输出：DocumentChunk[]
- 候选实现：MarkItDown、Unstructured、Docling

GraphExtractorProvider
- 输入：DocumentChunk[]、CognitiveSchema、ExtractionOptions
- 输出：ExtractionResult(candidate_entities, candidate_relations, candidate_rules, evidence)
- 候选实现：LlamaIndex Property Graph、Cognee、自研规则兜底

GraphStoreProvider
- 输入：已审核 Entity/Relation/Evidence/Rule
- 输出：存储结果和查询能力
- 候选实现：本地 JSON/关系表、Kuzu、Neo4j、FalkorDB

GraphRetrieverProvider
- 输入：task、agent_mode、entity_hints、data_ids
- 输出：与任务相关的实体、关系、规则、证据
- 候选实现：项目内检索、LlamaIndex retriever、Cognee search、图数据库查询
```

所有 provider 的输出都必须转换为项目内模型：

```text
Entity
Relation
Evidence
Rule
CognitiveMapView
```

前端和 Agent 不直接消费 LlamaIndex、Cognee、Neo4j、FalkorDB 等外部项目的原始对象。

### 推荐第一阶段组合

第一阶段推荐组合：

```text
文档解析：MarkItDown 或 Unstructured
实体关系抽取：LlamaIndex Property Graph，使用 schema-guided extraction
存储：项目本地 JSON/关系表
检索：项目内 ViewBuilder + 简单关键词/实体类型过滤
前端：项目 Vue 工作台
Agent 接入：CognitiveMapView
```

选择理由：

- Python 生态，容易嵌入当前 FastAPI 后端。
- 支持先定义实体类型、关系类型和约束，再在约束内抽取候选图谱。
- 不强制绑定独立图数据库。
- 前端完全由项目控制，保持交互和视觉一致。
- 后续可以把 provider 替换为 Cognee、Kuzu、Neo4j、FalkorDB，不影响前端和 Agent。

### 备选演进组合

如果后续更重视 Agent 长期记忆和跨会话知识积累，可以引入 Cognee 作为 `GraphExtractorProvider` 和 `GraphRetrieverProvider`。

如果图谱规模变大、关系查询复杂，可以引入 Kuzu、Neo4j 或 FalkorDB 作为 `GraphStoreProvider`。

如果需要完整 GraphRAG 社区摘要和多层检索，可以借鉴 Microsoft GraphRAG 的 TextUnit、Entity、Relationship、Claim、Community Report 结构，但仍然转换为项目内模型。

### 禁止耦合点

为了避免再次形成难以替换的体系，第一阶段禁止：

- 前端直接调用第三方图谱项目 API。
- Agent prompt 直接引用第三方原始 JSON。
- 把第三方项目的实体类型作为项目唯一 schema。
- 把外部图数据库作为发布地图的唯一事实来源。
- 绕过审核队列把 LLM 抽取结果直接发布。

### 开源项目选型矩阵

| 能力 | 第一选择 | 备选 | 项目内封装点 | 说明 |
| --- | --- | --- | --- | --- |
| 文档转 Markdown/文本块 | MarkItDown | Unstructured、Docling | `DocumentParserProvider` | 第一阶段优先跑通常见文档；复杂 PDF 和表格后续增强 |
| 结构化切块 | Unstructured | Docling | `DocumentParserProvider` | 需要保留标题、页码、表格位置时优先 |
| Schema-guided KG 抽取 | LlamaIndex Property Graph | LangChain LLMGraphTransformer | `GraphExtractorProvider` | 第一阶段核心 provider，必须输出候选实体、关系、证据 |
| Agent 图记忆 | Cognee | Graphiti | `GraphExtractorProvider` / `GraphRetrieverProvider` | 第二阶段评估，用于长期记忆和跨会话检索 |
| 本地图存储 | 本地 JSON/关系表 | Kuzu | `GraphStoreProvider` | 第一阶段避免运维新数据库 |
| 图数据库 | Kuzu | Neo4j、FalkorDB、Memgraph | `GraphStoreProvider` | 关系查询复杂后再引入 |
| GraphRAG 检索 | 项目内 ViewBuilder | Microsoft GraphRAG 思路、FalkorDB GraphRAG-SDK | `GraphRetrieverProvider` | 先输出 Agent 可用 view，再逐步增强 |

### 第一阶段 Spike

正式实现前先做一个独立 Spike，目标是验证 provider 方案是否能稳定产出项目模型：

1. 选 2-3 份大气环境业务文档。
2. 用 MarkItDown 或 Unstructured 解析为 `DocumentChunk`。
3. 定义最小 `CognitiveSchema`：
   - 实体：`Station`、`Pollutant`、`Metric`、`Region`、`DataSource`、`AnalysisMethod`、`EmissionSource`、`Finding`。
   - 关系：`located_in`、`measures`、`affects`、`indicates`、`requires_data`、`derived_from`、`supports`。
4. 用 LlamaIndex Property Graph provider 抽取候选实体、关系和证据。
5. 转换为项目内 `CandidateEntity`、`CandidateRelation`、`Evidence`。
6. 人工抽样检查 30 条候选项：
   - 名称是否正确。
   - 类型是否合理。
   - 关系方向是否正确。
   - 是否有可回溯证据。
7. 生成一个最小 `CognitiveMapView`，注入 expert/report prompt 做一次端到端试跑。

Spike 通过标准：

- 至少 70% 的高置信候选实体可直接确认。
- 每条关系都能回溯到 chunk 或人工创建说明。
- Provider 失败时不会污染已发布地图。
- 输出能被前端工作台和 Agent 同时消费。

## 前端工作台设计

新增“认知地图工作台”页面。页面采用三栏工作台布局：

```text
左侧：文件、地图、版本、构建任务
中间：图谱视图 / 表格视图 / 分层视图
右侧：实体、关系、证据、规则详情编辑面板
```

### 左侧导航

左侧用于管理输入来源和地图版本：

- 地图列表：名称、领域、状态、发布时间、实体数量、关系数量。
- 文件列表：文件名、类型、解析状态、来源、上传时间。
- 构建任务：等待中、解析中、抽取中、待审核、失败、已完成。
- 版本列表：草稿版本、已审核版本、已发布版本、历史版本。
- Agent 使用范围：query、expert、report、指定专家 Agent、指定任务类型。

### 中间主视图

中间提供三种视图，可切换：

1. **图谱视图**
   - 节点表示实体，边表示关系。
   - 节点颜色表示实体类型。
   - 节点大小可表示引用次数、连接度或置信度。
   - 边样式区分支持、影响、隶属、来源、约束等关系。
   - 支持缩放、拖拽、框选、聚焦实体、按来源文件过滤。

2. **表格视图**
   - 实体表：名称、类型、别名、属性、置信度、审核状态、证据数量。
   - 关系表：起点、关系类型、终点、置信度、证据数量、审核状态。
   - 证据表：来源文件、段落位置、文本片段、关联对象、抽取方式。
   - 规则表：规则名称、适用对象、条件、结论、证据、状态。

3. **分层视图**
   - 按业务本体层级组织：
     - 领域
     - 实体类型
     - 实体
     - 属性
     - 关系
     - 证据
   - 适合用户检查本体骨架是否完整。

### 右侧详情面板

右侧用于查看和编辑选中对象：

- 实体详情：名称、类型、别名、属性、说明、来源证据、审核状态。
- 关系详情：起点、终点、关系类型、说明、约束、证据、置信度。
- 证据详情：来源文件、页码或段落、原文片段、关联实体和关系。
- 规则详情：触发条件、推理结果、适用范围、限制条件、证据。
- 操作按钮：确认、修改、合并、拆分、删除、标记待确认、发布变更。

### 审核队列

工作台必须提供候选项审核队列：

- 高置信度候选：支持批量确认。
- 低置信度候选：需要人工逐条确认。
- 冲突候选：同名不同类型、属性冲突、关系方向冲突。
- 重复候选：建议合并实体或别名。
- 缺证据候选：允许保留为假设，但不能发布为确定事实。

审核状态：

```text
candidate
confirmed
rejected
needs_review
merged
published
```

## 认知地图数据模型

### CognitiveMap

```text
map_id
name
domain
description
status: draft | reviewing | published | archived
version
source_file_ids
entity_count
relation_count
evidence_count
rule_count
agent_scopes
created_by
created_at
updated_at
published_at
```

### SourceFile

```text
file_id
map_id
filename
content_type
storage_path
parse_status
build_status
chunk_count
metadata
created_at
```

### DocumentChunk

```text
chunk_id
file_id
map_id
chunk_index
page_number
section_title
text
token_count
metadata
```

### Entity

```text
entity_id
map_id
entity_type
name
canonical_name
aliases
description
attributes
source_evidence_ids
confidence
review_status
created_by: system | user | agent
updated_at
```

第一批实体类型：

```text
Station
Pollutant
Metric
TimeWindow
Region
DataSource
AnalysisMethod
EmissionSource
ProcessMechanism
ControlMeasure
StandardRule
Finding
Hypothesis
Dataset
Tool
AgentRole
```

### Relation

```text
relation_id
map_id
source_entity_id
target_entity_id
relation_type
description
attributes
source_evidence_ids
confidence
review_status
created_by
updated_at
```

第一批关系类型：

```text
located_in
measures
has_alias
belongs_to_category
affects
indicates
supports
contradicts
requires_data
derived_from
regulated_by
applies_to
produces
consumes
uses_method
has_limitation
handled_by_agent
```

### Evidence

```text
evidence_id
map_id
source_file_id
chunk_id
location
text_span
normalized_summary
linked_entity_ids
linked_relation_ids
confidence
created_by
created_at
```

### Rule

```text
rule_id
map_id
name
description
condition
conclusion
applies_to_entity_types
source_evidence_ids
confidence
review_status
```

### CognitiveMapView

Agent 不直接读取完整地图，而是读取任务相关视图：

```text
view_id
map_id
task
agent_mode
agent_role
entities
relations
rules
evidence_summaries
open_questions
limitations
prompt_summary
```

## 构建流程

### 1. 文件上传

用户在工作台上传文件，并选择或创建认知地图：

- 支持 PDF、Word、Excel、Markdown、TXT。
- 图片和扫描件可以后续接 OCR。
- 上传后创建 `SourceFile`。
- 文件只作为来源，不直接进入已发布地图。

### 2. 文档解析

后端把文件解析为 `DocumentChunk`：

- 保留页码、标题、表格位置等来源信息。
- 对 Excel 保留 sheet、行列范围。
- 对 Markdown 保留标题层级。
- 对 PDF 保留页码和段落位置。
- 文档解析通过 `DocumentParserProvider` 完成，第一阶段优先封装 MarkItDown 或 Unstructured，不在项目内自建复杂解析器。

### 3. 候选抽取

抽取分两类：

1. **确定性抽取**
   - 从文件元数据、表头、字段名、schema、`TypedDataHandle`、工具 metadata 中抽取。
   - 适合站点、污染物、指标、时间窗、数据集、工具名等。

2. **LLM 辅助抽取**
   - 从文档段落中抽取业务实体、关系、规则、机制、限制条件。
   - 输出必须绑定证据片段。
   - 结果只进入候选区，不能直接发布。
   - 通过 `GraphExtractorProvider` 调用成熟开源框架，第一阶段优先封装 LlamaIndex Property Graph 的 schema-guided extraction。

抽取时必须传入项目定义的 `CognitiveSchema`：

```text
allowed_entity_types
allowed_relation_types
allowed_relation_triplets
required_evidence
domain_aliases
normalization_rules
```

`GraphExtractorProvider` 可以使用第三方框架完成抽取，但返回结果必须转换为项目候选对象：

```text
CandidateEntity
CandidateRelation
CandidateRule
Evidence
ExtractionDiagnostic
```

### 4. 人工审核

用户在前端确认或修正候选项：

- 确认实体。
- 修改实体类型和属性。
- 合并重复实体。
- 删除误抽取实体。
- 修正关系方向。
- 为规则补充适用范围。
- 把缺证据内容降级为假设。

### 5. 发布地图版本

发布前执行校验：

- 已发布实体必须有名称、类型、来源或人工创建说明。
- 已发布关系必须有起点、终点、关系类型。
- 规则必须有条件、结论、适用范围。
- 事实性结论必须有证据。
- 无证据内容只能作为 Hypothesis 或 open question。

发布后生成不可变版本号。后续修改进入新草稿版本。

## Agent 接入设计

### 接入原则

- Agent 不读取完整地图。
- Agent 只读取与当前任务相关的 `CognitiveMapView`。
- 地图内容作为语义约束和证据来源，不替代实时工具查询。
- 数据证据和地图证据都必须可以被引用。

### 接入位置

第一阶段接入三个位置：

1. `ExecutionContext`
   - 增加当前会话可用地图 ID。
   - 支持查询任务相关 `CognitiveMapView`。

2. `prompt_builder`
   - 对 `query`、`expert`、`report` 注入认知地图摘要。
   - 对其他模式暂不默认注入。

3. `call_sub_agent`
   - 主 Agent 调用专家 Agent 时传入相关地图视图 ID 或地图摘要。
   - 子 Agent 只能看到与自己任务相关的实体、关系、规则、证据。

### Agent 认知地图摘要模板

```text
## 当前认知地图

任务目标：
{task}

相关实体：
- {entity_type}: {name} ({description})

关键关系：
- {source} --{relation_type}--> {target}: {description}

适用规则：
- {rule_name}: 当 {condition} 时，{conclusion}

可引用证据：
- [{evidence_id}] {source_file}:{location} {summary}

已知限制：
- {limitation}

输出约束：
- 事实性结论必须引用 evidence_refs。
- 无证据内容只能作为 hypothesis 或 open_question。
- 与地图冲突时必须说明冲突来源。
```

### 证据化输出 Contract

专家和报告链路逐步迁移到以下结构：

```json
{
  "answer": "自然语言回答",
  "claims": [
    {
      "claim": "结论文本",
      "claim_type": "finding",
      "evidence_refs": ["map_evidence:ev_001", "data:weather:v1:xxx"],
      "related_entities": ["station:xxx", "pollutant:o3"],
      "confidence": "medium",
      "limitations": ["缺少边界层高度实测数据"]
    }
  ],
  "new_findings": [],
  "new_hypotheses": [],
  "open_questions": []
}
```

引用类型：

```text
map_evidence:{evidence_id}
map_entity:{entity_id}
map_relation:{relation_id}
data:{data_id}
tool:{tool_call_id}
finding:{finding_id}
```

## 后端模块规划

新增目录：

```text
backend/app/agent/cognition/
├── __init__.py
├── models.py              # Pydantic 模型
├── repository.py          # 持久化访问
├── schema.py              # CognitiveSchema 与领域约束
├── document_parser.py     # provider 门面：文件解析与切块
├── extractor.py           # provider 门面：候选实体/关系/规则抽取
├── graph_store.py         # provider 门面：图谱存储与查询
├── retriever.py           # provider 门面：任务相关图谱检索
├── reviewer.py            # 审核状态与合并逻辑
├── map_builder.py         # 构建任务编排
├── view_builder.py        # Agent 任务视图构建
├── serializers.py         # prompt/json 序列化
├── evidence.py            # 证据引用与校验
└── providers/
    ├── __init__.py
    ├── base.py            # provider 协议定义
    ├── markitdown_parser.py
    ├── unstructured_parser.py
    ├── llamaindex_extractor.py
    ├── cognee_extractor.py
    ├── local_store.py
    ├── kuzu_store.py
    └── neo4j_store.py
```

Provider 协议草案：

```python
class DocumentParserProvider:
    async def parse(self, source_file: SourceFile) -> list[DocumentChunk]:
        ...


class GraphExtractorProvider:
    async def extract(
        self,
        chunks: list[DocumentChunk],
        schema: CognitiveSchema,
        options: ExtractionOptions,
    ) -> ExtractionResult:
        ...


class GraphStoreProvider:
    async def save_published_graph(self, map_version: CognitiveMapVersion) -> None:
        ...

    async def query_related(
        self,
        request: CognitiveMapQuery,
    ) -> GraphQueryResult:
        ...


class GraphRetrieverProvider:
    async def retrieve_view(
        self,
        request: CognitiveMapQuery,
    ) -> CognitiveMapView:
        ...
```

新增 API：

```text
POST   /api/cognitive-maps
GET    /api/cognitive-maps
GET    /api/cognitive-maps/{map_id}
PATCH  /api/cognitive-maps/{map_id}

POST   /api/cognitive-maps/{map_id}/files
GET    /api/cognitive-maps/{map_id}/files
POST   /api/cognitive-maps/{map_id}/build
GET    /api/cognitive-maps/{map_id}/build-tasks/{task_id}

GET    /api/cognitive-maps/{map_id}/entities
POST   /api/cognitive-maps/{map_id}/entities
PATCH  /api/cognitive-maps/{map_id}/entities/{entity_id}
DELETE /api/cognitive-maps/{map_id}/entities/{entity_id}

GET    /api/cognitive-maps/{map_id}/relations
POST   /api/cognitive-maps/{map_id}/relations
PATCH  /api/cognitive-maps/{map_id}/relations/{relation_id}
DELETE /api/cognitive-maps/{map_id}/relations/{relation_id}

GET    /api/cognitive-maps/{map_id}/evidence
GET    /api/cognitive-maps/{map_id}/review-queue
POST   /api/cognitive-maps/{map_id}/publish

POST   /api/cognitive-maps/query-context
```

`query-context` 请求：

```json
{
  "task": "分析某站点臭氧污染过程",
  "agent_mode": "expert",
  "agent_role": "meteorology",
  "map_ids": ["map_001"],
  "data_ids": ["weather:v1:xxx"],
  "entity_hints": ["臭氧", "深圳", "2026-05-01"]
}
```

`query-context` 响应：

```json
{
  "map_view": {
    "entities": [],
    "relations": [],
    "rules": [],
    "evidence_summaries": [],
    "limitations": [],
    "prompt_summary": "..."
  }
}
```

## 持久化策略

第一阶段优先使用现有后端数据目录和数据库能力，不强制引入图数据库。图存储能力通过 `GraphStoreProvider` 封装，外部图数据库只是 provider 实现，不是项目核心数据模型。

建议持久化路径：

```text
backend/backend_data_registry/cognitive_maps/
├── maps/{map_id}.json
├── files/{file_id}/source
├── files/{file_id}/chunks.jsonl
├── builds/{task_id}.json
└── versions/{map_id}/{version}.json
```

如果项目已有数据库表迁移体系，后续可迁移到关系表：

```text
cognitive_maps
cognitive_map_files
cognitive_map_chunks
cognitive_map_entities
cognitive_map_relations
cognitive_map_evidence
cognitive_map_rules
cognitive_map_versions
```

Provider 状态也需要持久化：

```text
cognitive_map_provider_runs
- run_id
- map_id
- provider_type
- provider_name
- provider_version
- input_file_ids
- options
- status
- diagnostics
- started_at
- finished_at
```

这样可以追踪每次抽取使用了哪个开源 provider、哪个版本、哪些参数，便于复现和升级回归。

## 前端模块规划

新增目录：

```text
frontend/src/views/CognitiveMapWorkbench.vue
frontend/src/components/cognitive-map/
├── MapSidebar.vue
├── FileUploadPanel.vue
├── BuildTaskList.vue
├── GraphCanvas.vue
├── EntityTable.vue
├── RelationTable.vue
├── EvidenceTable.vue
├── ReviewQueue.vue
├── DetailInspector.vue
└── PublishDialog.vue
frontend/src/api/cognitiveMap.js
```

图谱渲染可优先使用 ECharts graph，项目已经依赖 `echarts`，不需要第一阶段额外引入图谱库。

## 第一阶段交付范围

第一阶段实现以下能力：

- 创建认知地图。
- 上传文件。
- 通过 `DocumentParserProvider` 解析文件为 chunks。
- 通过 `GraphExtractorProvider` 抽取候选实体、关系、证据，默认优先封装 LlamaIndex Property Graph。
- 前端展示图谱和表格。
- 支持实体和关系的增删改。
- 支持候选项审核。
- 支持发布地图版本。
- 通过 `GraphStoreProvider` 保存发布后的地图，第一阶段默认本地存储。
- 支持 `query-context` 为 Agent 返回压缩地图视图。
- 在 `expert` 和 `report` prompt 中注入地图摘要。
- 专家/报告输出支持 `claims.evidence_refs`。

## 验收标准

功能验收：

- 用户能上传至少一个 Markdown 或 TXT 文件并生成候选实体。
- 构建任务记录中能看到使用的 parser/extractor provider 名称和版本。
- 用户能在前端确认、修改、删除实体。
- 用户能创建或修改实体关系。
- 用户能查看每个候选实体或关系对应的证据片段。
- 用户能发布一个认知地图版本。
- Agent 能通过 `query-context` 获取任务相关地图摘要。
- ReportAgent 输出的主要结论包含 `evidence_refs`。

质量验收：

- 候选抽取失败不影响已发布地图。
- 发布版本不可变，修改必须进入新草稿。
- 无证据事实不能作为 confirmed/published 事实发布。
- Prompt 注入内容有长度控制，避免整张地图进入上下文。
- 所有 Agent 引用的地图证据都能回溯到来源文件和位置。

## 风险与对策

1. **LLM 抽取不稳定**
   - 对策：抽取结果只进候选区；发布必须经过审核或规则校验。

2. **图谱过大导致前端卡顿**
   - 对策：默认显示局部子图；支持按类型、文件、置信度过滤。

3. **Prompt 过长**
   - 对策：Agent 只读取 `CognitiveMapView`，并限制实体、关系、证据数量。

4. **实体类型早期不完善**
   - 对策：允许用户新增类型，但发布时要求映射到一级通用类型。

5. **证据引用与工具数据割裂**
   - 对策：统一 evidence ref 格式，支持 `map_evidence`、`data`、`tool` 混合引用。

## 后续演进

第二阶段可以扩展：

- OCR 图片文档解析。
- Excel 表格结构化抽取。
- 实体冲突检测和自动合并建议。
- 图谱差异对比。
- 跨会话地图检索。
- 与 `DataContextManager.save_data()` 自动联动，工具结果自动登记为 `Dataset` 实体。
- 引入图数据库或向量检索作为性能优化，而不是第一阶段前置依赖。

第三阶段可以扩展：

- 多地图组合检索。
- 专家 Agent 反向写入新发现。
- 报告结论审计面板。
- 领域本体模板库。
- Agent 任务过程可视化为认知轨迹。
