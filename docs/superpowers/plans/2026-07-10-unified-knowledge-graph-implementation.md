# Unified Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将知识图谱收敛为每个知识库内置的结构化索引，使文档新增、原位替换和删除能够增量更新 Chunk、向量、实体、关系与证据，并让普通 RAG 和图检索返回同一套可追溯 Chunk 结果。

**Architecture:** PostgreSQL 是 Chunk、实体、关系、Mention、审核状态和 Outbox 的唯一事实源；现有 Qdrant Collection 保存 `chunk/entity/relation` 三类可重建派生索引。文档摄取通过统一状态机计算 Chunk 差异、抽取候选图谱并写 Outbox；查询通过普通混合召回、可信图种子召回、有界关系扩散和 RRF 融合产生结果。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy Async、PostgreSQL、Qdrant、Pydantic v2、pytest/pytest-asyncio、Vue 3、Node test runner

---

## 实施约束

- 所有 Python 命令使用 `conda run -p /root/miniconda3/envs/backend_py311`。
- 开始执行前使用 `using-git-worktrees` 创建隔离工作树；当前主工作树已有用户未提交改动，不在其上直接实施。
- 每个任务遵循红-绿-重构；只提交该任务列出的文件。
- 不引入 Neo4j、Milvus、Kuzu 或新任务队列。
- 不在 Qdrant 中保存唯一事实；所有 Point 必须能从 PostgreSQL 重建。
- 原文档替换不保留旧版本、不回滚旧数据；失败时当前文档进入 `failed`。
- 旧认知地图只在迁移阶段保持只读；完成对账前不得删除原目录。

## 文件结构

新增的后端模块按职责拆分：

```text
backend/app/knowledge_base/
├── graph_models.py          # SQLAlchemy Chunk/图谱/Mention/Outbox 模型
├── graph_schemas.py         # 图谱领域 Pydantic 输入输出模型和状态常量
├── chunk_diff.py            # 纯函数 Chunk 稳定键和差异计算
├── chunk_repository.py      # Chunk 持久化与 generation 防护
├── graph_repository.py      # 实体/关系/Mention、审核、合并、BFS、孤儿清理
├── index_outbox.py          # Outbox 仓储、Qdrant typed-point worker、对账
├── graph_extractor.py       # 现有 cognition extractor 到知识库模型的适配层
├── ingestion_service.py     # 新增/替换/删除统一状态机
└── retrieval_service.py     # Chunk + 图召回与 RRF 融合

backend/app/api/
└── knowledge_graph_routes.py # 知识库图谱子资源 API

backend/scripts/
├── migrate_unified_knowledge_graph.py
└── migrate_cognitive_maps_to_knowledge_bases.py

frontend/src/components/management/knowledge-base/
├── KnowledgeGraphTab.vue
├── KnowledgeGraphReview.vue
└── KnowledgeGraphStatus.vue
```

已有 `backend/app/knowledge_base/service.py` 只保留知识库用例入口，具体摄取和检索委托给新服务；不继续扩大该文件。已有 cognition provider 暂时复用，迁移完成后才删除旧 JSON 路由和工具。

---

## Phase 1：事实模型和增量基础

### Task 1: 建立统一 SQLAlchemy 模型和数据库迁移

**Files:**

- Create: `backend/app/knowledge_base/graph_models.py`
- Create: `backend/app/alembic/versions/create_unified_knowledge_graph.py`
- Modify: `backend/app/knowledge_base/models.py`
- Modify: `backend/app/db/database.py`
- Test: `backend/tests/knowledge_base/test_unified_graph_models.py`

- [ ] **Step 1: 写模型元数据失败测试**

```python
from app.db.database import Base
from app.knowledge_base.graph_models import (
    KnowledgeChunk,
    KnowledgeGraphEntity,
    KnowledgeGraphEntityMention,
    KnowledgeGraphRelation,
    KnowledgeGraphRelationMention,
    KnowledgeIndexOutbox,
)


def test_unified_graph_tables_and_constraints_are_registered():
    expected = {
        "knowledge_chunks",
        "knowledge_graph_entities",
        "knowledge_graph_relations",
        "knowledge_graph_entity_mentions",
        "knowledge_graph_relation_mentions",
        "knowledge_index_outbox",
    }
    assert expected <= set(Base.metadata.tables)
    assert KnowledgeChunk.__table__.c.content_generation.nullable is False
    assert KnowledgeGraphEntity.__table__.c.kb_id.nullable is False
    assert KnowledgeGraphRelation.__table__.c.source_entity_id.nullable is False
    assert KnowledgeGraphEntityMention.__table__.c.chunk_id.nullable is False
    assert KnowledgeGraphRelationMention.__table__.c.chunk_id.nullable is False
    assert KnowledgeIndexOutbox.__table__.c.payload_version.nullable is False


def test_knowledge_base_and_document_have_graph_state_columns():
    from app.knowledge_base.models import Document, KnowledgeBase

    assert KnowledgeBase.__table__.c.graph_enabled.default.arg is True
    assert "graph_schema" in KnowledgeBase.__table__.c
    assert "content_generation" in Document.__table__.c
    assert "ingestion_status" in Document.__table__.c
    assert "graph_status" in Document.__table__.c
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_unified_graph_models.py -q
```

Expected: collection fails with `ModuleNotFoundError: app.knowledge_base.graph_models`.

- [ ] **Step 3: 实现模型**

在 `graph_models.py` 定义以下枚举和值，所有枚举以字符串列保存，避免 PostgreSQL Enum 后续难迁移：

```python
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, Index,
)

from app.db.database import Base


def new_id() -> str:
    return str(uuid4())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_key", name="uq_knowledge_chunk_document_key"),
        Index("ix_knowledge_chunk_kb_status", "kb_id", "vector_status", "graph_status"),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    content_generation = Column(Integer, nullable=False)
    chunk_key = Column(String(96), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_text = Column(Text, nullable=False)
    context_prefix = Column(Text, nullable=False, default="")
    start_char = Column(Integer)
    end_char = Column(Integer)
    page_number = Column(Integer)
    section_path = Column(JSON, nullable=False, default=list)
    chunk_metadata = Column(JSON, nullable=False, default=dict)
    vector_status = Column(String(20), nullable=False, default="pending")
    graph_status = Column(String(20), nullable=False, default="pending")
    last_error = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeGraphEntity(Base):
    __tablename__ = "knowledge_graph_entities"
    __table_args__ = (
        UniqueConstraint("kb_id", "entity_type", "normalized_name", name="uq_kg_entity_identity"),
        Index("ix_kg_entity_kb_review", "kb_id", "review_status"),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(80), nullable=False)
    name = Column(String(512), nullable=False)
    normalized_name = Column(String(512), nullable=False)
    canonical_name = Column(String(512))
    aliases = Column(JSON, nullable=False, default=list)
    description = Column(Text)
    attributes = Column(JSON, nullable=False, default=dict)
    review_status = Column(String(20), nullable=False, default="candidate")
    created_by = Column(String(20), nullable=False, default="extractor")
    locked_by_user = Column(Boolean, nullable=False, default=False)
    merged_into_id = Column(String(36), ForeignKey("knowledge_graph_entities.id", ondelete="SET NULL"))
    mention_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeGraphRelation(Base):
    __tablename__ = "knowledge_graph_relations"
    __table_args__ = (
        UniqueConstraint(
            "kb_id", "source_entity_id", "relation_type", "target_entity_id",
            name="uq_kg_relation_identity",
        ),
        Index("ix_kg_relation_kb_review", "kb_id", "review_status"),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    source_entity_id = Column(String(36), ForeignKey("knowledge_graph_entities.id", ondelete="CASCADE"), nullable=False)
    target_entity_id = Column(String(36), ForeignKey("knowledge_graph_entities.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(120), nullable=False)
    description = Column(Text)
    attributes = Column(JSON, nullable=False, default=dict)
    review_status = Column(String(20), nullable=False, default="candidate")
    created_by = Column(String(20), nullable=False, default="extractor")
    locked_by_user = Column(Boolean, nullable=False, default=False)
    mention_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class _MentionColumns:
    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_id = Column(String(36), ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False)
    evidence_text = Column(Text, nullable=False, default="")
    evidence_start = Column(Integer)
    evidence_end = Column(Integer)
    page_number = Column(Integer)
    confidence = Column(Float)
    extractor_name = Column(String(120), nullable=False)
    extraction_run_id = Column(String(36), nullable=False)


class KnowledgeGraphEntityMention(_MentionColumns, Base):
    __tablename__ = "knowledge_graph_entity_mentions"
    __table_args__ = (UniqueConstraint("entity_id", "chunk_id", name="uq_kg_entity_mention"),)
    entity_id = Column(String(36), ForeignKey("knowledge_graph_entities.id", ondelete="CASCADE"), nullable=False)


class KnowledgeGraphRelationMention(_MentionColumns, Base):
    __tablename__ = "knowledge_graph_relation_mentions"
    __table_args__ = (UniqueConstraint("relation_id", "chunk_id", name="uq_kg_relation_mention"),)
    relation_id = Column(String(36), ForeignKey("knowledge_graph_relations.id", ondelete="CASCADE"), nullable=False)


class KnowledgeIndexOutbox(Base):
    __tablename__ = "knowledge_index_outbox"
    __table_args__ = (
        UniqueConstraint(
            "record_type", "record_id", "operation", "payload_version",
            name="uq_knowledge_index_outbox_idempotency",
        ),
        Index("ix_knowledge_index_outbox_pending", "status", "next_retry_at"),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    record_type = Column(String(20), nullable=False)
    record_id = Column(String(36), nullable=False)
    operation = Column(String(10), nullable=False)
    payload_version = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_error = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

在 `models.py` 为 `KnowledgeBase` 增加 `graph_enabled`、`graph_schema`、`graph_extractor_config`、`graph_updated_at`；为 `Document` 增加 `content_generation`、`ingestion_status`、`graph_status`、`processing_error`。在 `init_db()` 中显式导入 `app.knowledge_base.graph_models`。

迁移脚本用 SQLAlchemy `text()` 创建相同列、表、唯一约束和索引；提供 `upgrade()`，不提供自动 destructive downgrade，回滚由部署备份恢复。脚本入口为：

```python
if __name__ == "__main__":
    import asyncio
    asyncio.run(upgrade())
```

- [ ] **Step 4: 运行模型测试和迁移导入检查**

Run:

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_unified_graph_models.py -q
cd backend && conda run -p /root/miniconda3/envs/backend_py311 python -m py_compile app/knowledge_base/graph_models.py app/alembic/versions/create_unified_knowledge_graph.py
```

Expected: tests pass; `py_compile` exits 0.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/graph_models.py backend/app/knowledge_base/models.py backend/app/db/database.py backend/app/alembic/versions/create_unified_knowledge_graph.py backend/tests/knowledge_base/test_unified_graph_models.py
git commit -m "feat: 建立统一知识图谱事实模型"
```

### Task 2: 定义图谱领域契约和 Chunk 差异算法

**Files:**

- Create: `backend/app/knowledge_base/graph_schemas.py`
- Create: `backend/app/knowledge_base/chunk_diff.py`
- Test: `backend/tests/knowledge_base/test_chunk_diff.py`

- [ ] **Step 1: 写稳定键与差异测试**

```python
from app.knowledge_base.chunk_diff import build_chunk_drafts, diff_chunks


def test_duplicate_text_gets_distinct_stable_keys():
    drafts = build_chunk_drafts([
        {"content": "同一段", "embedding_text": "同一段"},
        {"content": "同一段", "embedding_text": "同一段"},
    ])
    assert drafts[0].content_hash == drafts[1].content_hash
    assert drafts[0].chunk_key != drafts[1].chunk_key


def test_diff_reuses_unchanged_and_replaces_changed_chunks():
    old = build_chunk_drafts([{"content": "A"}, {"content": "B"}])
    new = build_chunk_drafts([{"content": "A"}, {"content": "C"}])
    result = diff_chunks(old, new)
    assert [item.content for item in result.reused] == ["A"]
    assert [item.content for item in result.added] == ["C"]
    assert [item.content for item in result.removed] == ["B"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_chunk_diff.py -q
```

Expected: import fails because `chunk_diff.py` does not exist.

- [ ] **Step 3: 实现契约和纯函数**

`graph_schemas.py` 定义：

```python
from typing import Any, Literal
from pydantic import BaseModel, Field

ReviewStatus = Literal["candidate", "confirmed", "rejected", "merged", "published", "archived"]
TrustedReviewStatus = {"confirmed", "published"}


class ExtractedEntity(BaseModel):
    local_id: str
    entity_type: str
    name: str
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_text: str = ""
    confidence: float | None = None


class ExtractedRelation(BaseModel):
    source_local_id: str
    target_local_id: str
    relation_type: str
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_text: str = ""
    confidence: float | None = None


class ChunkGraphExtraction(BaseModel):
    chunk_id: str
    extractor_name: str
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
```

`chunk_diff.py` 使用 NFKC、换行和空白归一化后计算 SHA-256；`chunk_key` 格式为 `{content_hash}:{occurrence}`。定义不可变 `ChunkDraft`、`ChunkDiff`，`diff_chunks()` 按 `chunk_key` 复用，内容或检索文本变化时归入 remove + add。

- [ ] **Step 4: 运行测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_chunk_diff.py -q
```

Expected: 2 tests pass.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/graph_schemas.py backend/app/knowledge_base/chunk_diff.py backend/tests/knowledge_base/test_chunk_diff.py
git commit -m "feat: 定义图谱契约和分块差异算法"
```

### Task 3: 实现 Chunk 仓储和 generation 防护

**Files:**

- Create: `backend/app/knowledge_base/chunk_repository.py`
- Test: `backend/tests/knowledge_base/test_chunk_repository.py`

- [ ] **Step 1: 写仓储行为测试**

使用 SQLite async 测试库创建 `KnowledgeBase`、`Document` 和新表，验证 `replace_document_chunks()`：相同 `chunk_key` 复用原 ID；新增 Chunk 插入；消失 Chunk 返回待清理 ID；传入旧 generation 抛出 `StaleContentGeneration`。

核心断言：

```python
result = await repository.replace_document_chunks(
    kb_id=kb.id,
    document_id=doc.id,
    content_generation=2,
    drafts=build_chunk_drafts([{"content": "A"}, {"content": "C"}]),
)
assert [chunk.content for chunk in result.reused] == ["A"]
assert [chunk.content for chunk in result.added] == ["C"]
assert [chunk.content for chunk in result.removed] == ["B"]

with pytest.raises(StaleContentGeneration):
    await repository.replace_document_chunks(
        kb_id=kb.id,
        document_id=doc.id,
        content_generation=1,
        drafts=[],
    )
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_chunk_repository.py -q
```

Expected: import failure for `chunk_repository`.

- [ ] **Step 3: 实现仓储**

公开契约固定为：

- `StaleContentGeneration(RuntimeError)`：任务 generation 与当前文档不一致时抛出。
- `PersistedChunkDiff(reused, added, removed)`：三个字段均为 `list[KnowledgeChunk]`。
- `KnowledgeChunkRepository(session: AsyncSession)`。
- `list_by_document(document_id) -> list[KnowledgeChunk]`。
- `get_by_ids(kb_id, chunk_ids) -> list[KnowledgeChunk]`，必须同时过滤 `kb_id`。
- `replace_document_chunks(kb_id, document_id, content_generation, drafts) -> PersistedChunkDiff`。
- `mark_vector_status(chunk_ids, status, error=None)` 和 `mark_graph_status(chunk_ids, status, error=None)`。

`replace_document_chunks()` 首先用 `select(Document).where(Document.id == document_id).with_for_update()` 锁定文档，严格比较 generation；reused Chunk 保留 ID 和 Mention，但更新 `content_generation`、`chunk_index`、位置和 metadata；只插入 added，不立即删除 removed，由 ingestion service 在删除 Mention 和写 Outbox 后统一删除。

- [ ] **Step 4: 运行测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_chunk_repository.py -q
```

Expected: all tests pass.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/chunk_repository.py backend/tests/knowledge_base/test_chunk_repository.py
git commit -m "feat: 实现增量分块仓储"
```

### Task 4: 实现实体、关系、Mention 和孤儿清理仓储

**Files:**

- Create: `backend/app/knowledge_base/graph_repository.py`
- Test: `backend/tests/knowledge_base/test_graph_repository.py`

- [ ] **Step 1: 写复用、来源和孤儿测试**

测试同一知识库相同 `(type, normalized_name)` 复用，不同知识库隔离；两个文档支持同一关系时删除其中一个不删除关系；删除最后 Mention 时自动候选关系删除，人工锁定实体转 `archived`。

```python
first = await repository.upsert_chunk_extraction(kb_id="kb1", document_id="d1", extraction=extraction1)
second = await repository.upsert_chunk_extraction(kb_id="kb1", document_id="d2", extraction=extraction2)
assert first.entity_ids == second.entity_ids

await repository.remove_chunk_contributions(kb_id="kb1", chunk_ids=["chunk1"])
relation = await repository.get_relation(first.relation_ids[0])
assert relation.mention_count == 1

await repository.remove_chunk_contributions(kb_id="kb1", chunk_ids=["chunk2"])
assert await repository.get_relation(first.relation_ids[0]) is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_repository.py -q
```

Expected: import failure for `graph_repository`.

- [ ] **Step 3: 实现仓储公开 API**

公开契约固定为：

- `GraphUpsertResult` 包含 `entity_ids`、`relation_ids`、`changed_entity_ids`、`changed_relation_ids` 四个 `list[str]` 字段。
- `upsert_chunk_extraction(kb_id, document_id, extraction, extraction_run_id) -> GraphUpsertResult`。
- `remove_chunk_contributions(kb_id, chunk_ids) -> tuple[list[str], list[str]]`，返回需要从向量索引删除的 entity/relation ID。
- `set_review_status(kb_id, kind, record_id, status)`，其中 kind 只能为 `entity | relation`。
- `merge_entities(kb_id, source_id, target_id)`。
- `query_entities(kb_id, text, statuses, limit) -> list[KnowledgeGraphEntity]`。
- `traverse(kb_id, seed_entity_ids, statuses, depth, limit) -> tuple[entities, relations]`。
- `chunk_ids_for_graph_records(kb_id, entity_ids, relation_ids) -> list[str]`。

归一化使用 NFKC + trim + lowercase 英文，不删除中文标点。Upsert 冲突时只合并 aliases/attributes；`locked_by_user=true` 时不得覆盖人工字段。Mention upsert 后用数据库 `COUNT(*)` 回写计数。孤儿清理严格使用设计规格的自动删除/人工归档规则。

- [ ] **Step 4: 运行测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_repository.py -q
```

Expected: all tests pass.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/graph_repository.py backend/tests/knowledge_base/test_graph_repository.py
git commit -m "feat: 实现知识图谱关系仓储"
```

---

## Phase 2：Qdrant 派生索引和抽取适配

### Task 5: 为现有 Qdrant Collection 增加 typed point 协议

**Files:**

- Modify: `backend/app/knowledge_base/vector_store.py`
- Test: `backend/tests/knowledge_base/test_typed_vector_store.py`
- Test: `backend/tests/knowledge_base/test_legacy_chunk_search_compat.py`

- [ ] **Step 1: 写确定性 ID、过滤和删除测试**

用 fake Qdrant client 捕获请求；兼容测试构造一个没有 `record_type` 的旧 Chunk Point，断言旧普通 `search()` 仍将其作为 Chunk 返回，但 `search_records(record_types={"entity"})` 不返回它：

```python
point_id = store.typed_point_id("entity", "entity-1")
assert point_id == store.typed_point_id("entity", "entity-1")
assert point_id != store.typed_point_id("relation", "entity-1")

await store.search_records("collection", "臭氧", record_types={"entity"}, review_statuses={"confirmed"}, top_k=10)
query_filter = fake_client.query_points.call_args.kwargs["query_filter"]
assert query_filter.must[0].key == "record_type"

await store.delete_records("collection", "relation", ["relation-1"])
assert fake_client.delete.call_count == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_typed_vector_store.py tests/knowledge_base/test_legacy_chunk_search_compat.py -q
```

Expected: `KnowledgeVectorStore` lacks `typed_point_id`.

- [ ] **Step 3: 实现 typed point API**

在 `KnowledgeVectorStore` 增加：

```python
@staticmethod
def typed_point_id(record_type: str, record_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"suyuan:knowledge:{record_type}:{record_id}"))

async def upsert_records(
    self, collection_name: str, records: list[dict[str, Any]]
) -> int:
    """records require record_type, record_id, content, embedding_text and payload."""

async def delete_records(self, collection_name: str, record_type: str, record_ids: list[str]) -> None:
    point_ids = [self.typed_point_id(record_type, record_id) for record_id in record_ids]
    if point_ids:
        await asyncio.to_thread(self.qdrant_client.delete, collection_name=collection_name, points_selector=point_ids)
```

`search_records(collection_name, query, record_types, review_statuses, top_k)` 复用现有 query embedding 和 hybrid search，构造 `record_type` MatchAny 过滤；传入审核状态时再增加 `review_status` MatchAny 过滤，并把命中统一映射为 `{record_type, record_id, content, score, payload}`。不得复制一套新的 embedding 初始化逻辑。

修改现有 `add_chunks()` 产生 `record_type="chunk"`、`record_id=chunk.id`。保留旧 point 读取兼容：payload 缺少 `record_type` 时仅旧普通检索视为 chunk；所有新图检索拒绝无类型 Point。

- [ ] **Step 4: 运行 typed store 和现有知识库检索测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_typed_vector_store.py tests/knowledge_base/test_legacy_chunk_search_compat.py -q
```

Expected: typed tests and legacy untyped Chunk compatibility tests pass.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/vector_store.py backend/tests/knowledge_base/test_typed_vector_store.py backend/tests/knowledge_base/test_legacy_chunk_search_compat.py
git commit -m "feat: 统一知识库向量记录协议"
```

### Task 6: 实现 Outbox worker 和生命周期

**Files:**

- Create: `backend/app/knowledge_base/index_outbox.py`
- Modify: `backend/app/lifecycle/knowledge_base.py`
- Test: `backend/tests/knowledge_base/test_index_outbox.py`
- Test: `backend/tests/test_lifecycle_knowledge_base_outbox.py`

- [ ] **Step 1: 写幂等、重试和停止测试**

```python
await repository.enqueue_upsert(kb_id="kb1", record_type="entity", record_id="e1", payload_version=1, payload=payload)
await repository.enqueue_upsert(kb_id="kb1", record_type="entity", record_id="e1", payload_version=1, payload=payload)
assert await repository.pending_count() == 1

worker = KnowledgeIndexOutboxWorker(repository=repository, vector_store=failing_once_store, collection_resolver=resolver)
assert await worker.run_once() == 0
assert (await repository.get(item.id)).status == "pending"
assert await worker.run_once() == 1
assert (await repository.get(item.id)).status == "completed"
```

生命周期测试 monkeypatch `start_index_outbox_worker` 和 `stop_index_outbox_worker`，断言知识库服务启动/停止各调用一次。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_index_outbox.py tests/test_lifecycle_knowledge_base_outbox.py -q
```

Expected: import failure for `index_outbox`.

- [ ] **Step 3: 实现 Outbox**

公开 API：

- `KnowledgeIndexOutboxRepository.enqueue_upsert(kb_id, record_type, record_id, payload_version, payload)`。
- `enqueue_delete(kb_id, record_type, record_id, payload_version)`。
- `claim_batch(limit) -> list[KnowledgeIndexOutbox]`。
- `mark_completed(item_id)` 和 `mark_retry(item_id, error)`。
- `KnowledgeIndexOutboxWorker.run_once() -> int` 返回本轮成功数。
- `run_forever()` 持续 claim、同步和退避；`stop()` 设置停止事件并等待当前 batch 结束。

`claim_batch()` 使用 `FOR UPDATE SKIP LOCKED`。重试间隔为 `min(300, 2 ** attempts)` 秒；worker 空闲轮询 1 秒。模块提供进程内单例 `start_index_outbox_worker()` / `stop_index_outbox_worker()`，仅在 worker/all 角色生命周期启动。

- [ ] **Step 4: 运行测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_index_outbox.py tests/test_lifecycle_knowledge_base_outbox.py -q
```

Expected: all tests pass.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/index_outbox.py backend/app/lifecycle/knowledge_base.py backend/tests/knowledge_base/test_index_outbox.py backend/tests/test_lifecycle_knowledge_base_outbox.py
git commit -m "feat: 增加知识索引出站队列"
```

### Task 7: 适配现有图谱抽取器为 Chunk 增量抽取

**Files:**

- Create: `backend/app/knowledge_base/graph_extractor.py`
- Modify: `backend/app/agent/cognition/providers/llamaindex_extractor.py`
- Test: `backend/tests/knowledge_base/test_graph_extractor_adapter.py`

- [ ] **Step 1: 写单 Chunk 输出和证据映射测试**

构造 fake cognition provider 返回一个实体和一条关系，断言适配器输出 `ChunkGraphExtraction.chunk_id` 与输入一致、关系端点使用 local ID、证据文本来自当前 Chunk，输出不携带 `map_id`。

```python
result = await adapter.extract_chunk(
    kb_id="kb1",
    chunk=chunk,
    schema=CognitiveSchema.default_air_quality_schema(),
)
assert result.chunk_id == chunk.id
assert result.entities[0].name == "臭氧"
assert result.relations[0].source_local_id in {item.local_id for item in result.entities}
assert result.entities[0].evidence_text == chunk.content
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_extractor_adapter.py -q
```

Expected: import failure for `graph_extractor`.

- [ ] **Step 3: 实现适配器**

`KnowledgeGraphExtractor(provider=None)` 默认通过 `create_extractor_provider("llamaindex", llm=create_llamaindex_llm("project"))` 创建 provider；`extract_chunk(kb_id, chunk, schema) -> ChunkGraphExtraction` 将 `KnowledgeChunk` 转为单个 cognition `DocumentChunk`，调用 provider，建立旧 entity ID 到新 local ID 的映射，再将实体、关系和当前 Chunk 证据转换为 `graph_schemas.py` 模型。关系端点在映射中不存在时直接拒绝该关系并记录 diagnostic，不能创建悬空端点。

为 cognition provider 增加可选 `source_namespace`，稳定 ID 计算使用 `kb_id + chunk.id`，避免 map 语义渗透。适配器逐 Chunk 调用以支持失败重试和局部删除；并发由 ingestion service 的 semaphore 控制。

- [ ] **Step 4: 运行测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_extractor_adapter.py tests/test_cognitive_map_spike.py -q
```

Expected: adapter tests and legacy extractor tests pass.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/graph_extractor.py backend/app/agent/cognition/providers/llamaindex_extractor.py backend/tests/knowledge_base/test_graph_extractor_adapter.py
git commit -m "feat: 支持知识库分块增量抽图"
```

---

## Phase 3：统一摄取、替换和删除

### Task 8: 实现统一摄取状态机并接入新增文档

**Files:**

- Create: `backend/app/knowledge_base/ingestion_service.py`
- Modify: `backend/app/knowledge_base/service.py`
- Modify: `backend/app/knowledge_base/tasks.py`
- Test: `backend/tests/knowledge_base/test_ingestion_service.py`
- Test: `backend/tests/api/test_knowledge_base_upload_compat.py`

- [ ] **Step 1: 写新增文档编排测试**

使用 fake parser、repositories、extractor 和 outbox，验证顺序与状态：解析两个 Chunk，只写两个 Chunk；创建两个 chunk upsert；逐 Chunk 抽图；创建 entity/relation upsert；最终 `ingestion_status=completed`、`graph_status=completed`。图抽取失败时 `ingestion_status=partial` 且普通 Chunk outbox 仍存在。API 兼容测试固定现有 `POST /api/knowledge-base/{kb_id}/documents` multipart 字段和 `DocumentResponse` 主字段不变。

```python
result = await service.ingest_document(document_id="doc1")
assert result.added_chunks == 2
assert result.reused_chunks == 0
assert result.removed_chunks == 0
assert fake_document.ingestion_status == "completed"
assert fake_document.graph_status == "completed"
assert outbox.record_types == ["chunk", "chunk", "entity", "relation"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_ingestion_service.py tests/api/test_knowledge_base_upload_compat.py -q
```

Expected: import failure for `ingestion_service`.

- [ ] **Step 3: 实现状态机**

`IngestionResult` 是 dataclass，字段固定为 `document_id`、`content_generation`、`added_chunks`、`reused_chunks`、`removed_chunks`、`changed_entities`、`changed_relations`、`status`。`KnowledgeIngestionService` 公开 `ingest_document(document_id)`、`replace_document(document_id, new_file_path, file_metadata)` 和 `delete_document(kb_id, document_id)` 三个异步方法；三者必须通过构造器注入 session factory、processor、chunk repository factory、graph repository factory、extractor、outbox factory 和 file storage，测试不访问真实外部服务。

`ingest_document()` 获取当前 generation；解析和分块；事务内写 Chunk 和 chunk Outbox；事务外执行受控并发抽取；每个抽取结果在独立短事务写 graph + Outbox。只有 Chunk 事实和 Outbox 成功后才标记普通检索可用。图抽取失败记录 Chunk `graph_status=failed` 和文档 `partial`，不吞掉错误原因。

修改 `KnowledgeBaseService._process_document()` 委托新服务；`tasks.py` 不再直接调用旧的向量化流程。

- [ ] **Step 4: 运行新旧摄取测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_ingestion_service.py tests/api/test_knowledge_base_upload_compat.py -q
```

Expected: unified ingestion tests pass; selected legacy knowledge-base tests remain green.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/ingestion_service.py backend/app/knowledge_base/service.py backend/app/knowledge_base/tasks.py backend/tests/knowledge_base/test_ingestion_service.py backend/tests/api/test_knowledge_base_upload_compat.py
git commit -m "feat: 统一文档和图谱摄取流程"
```

### Task 9: 实现直接替换和级联删除语义

**Files:**

- Modify: `backend/app/knowledge_base/ingestion_service.py`
- Modify: `backend/app/knowledge_base/service.py`
- Modify: `backend/app/api/knowledge_base_routes.py`
- Modify: `backend/app/knowledge_base/schemas.py`
- Test: `backend/tests/knowledge_base/test_document_replace_delete.py`
- Test: `backend/tests/api/test_knowledge_base_document_replace.py`

- [ ] **Step 1: 写直接替换失败测试**

覆盖四种场景：未变化 Chunk 复用；变化 Chunk remove + add；旧 generation 任务被拒绝；新解析失败后旧文件、Chunk、向量和 Mention 已清除，Document 为 `failed`，不存在回滚数据。

API 测试：

```python
response = client.put(
    f"/api/knowledge-base/{kb_id}/documents/{doc_id}/content",
    files={"file": ("replacement.md", b"new content", "text/markdown")},
)
assert response.status_code == 200
assert response.json()["content_generation"] == 2
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_document_replace_delete.py tests/api/test_knowledge_base_document_replace.py -q
```

Expected: PUT route returns 405 or 404.

- [ ] **Step 3: 实现替换与删除**

替换进入服务后立即：锁定 Document、递增 generation、标记 processing、删除旧原文件引用和旧派生数据，再保存新文件并摄取；不创建版本表。删除顺序固定为：文档标记 deleting → graph Mention/孤儿 → chunk/entity/relation delete Outbox → Chunk 行 → 原文件 → Document → 统计重算。

新增 API：

```python
@router.put("/{kb_id}/documents/{doc_id}/content", response_model=DocumentResponse)
async def replace_document_content(
    kb_id: str,
    doc_id: str,
    file: UploadFile = File(),
    user_id: str = Header(default="anonymous", alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
    db: AsyncSession = Depends(get_db),
):
    service = KnowledgeBaseService(db)
    document = await service.replace_document_content(
        kb_id=kb_id,
        doc_id=doc_id,
        upload=file,
        user_id=user_id,
        is_admin=is_admin,
    )
    return _doc_to_response(document)
```

替换失败时返回 500，并确保查询 Document 可见 `status=failed` 和当前错误；不得从临时目录恢复旧文件。

- [ ] **Step 4: 运行测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_document_replace_delete.py tests/api/test_knowledge_base_document_replace.py -q
```

Expected: all tests pass.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/ingestion_service.py backend/app/knowledge_base/service.py backend/app/api/knowledge_base_routes.py backend/app/knowledge_base/schemas.py backend/tests/knowledge_base/test_document_replace_delete.py backend/tests/api/test_knowledge_base_document_replace.py
git commit -m "feat: 支持知识库文档直接替换"
```

---

## Phase 4：图谱 API、统一检索和 Agent

### Task 10: 增加知识库图谱子资源 API 和权限

**Files:**

- Create: `backend/app/api/knowledge_graph_routes.py`
- Modify: `backend/app/core/routing.py`
- Modify: `backend/app/knowledge_base/graph_schemas.py`
- Test: `backend/tests/api/test_knowledge_graph_routes.py`

- [ ] **Step 1: 写状态、查询、审核、合并和权限测试**

建立 FastAPI test app，override DB/session 和 service dependency。断言 `can_search` 用户可 GET/query，只有 `can_manage` 用户可 PATCH/merge/reindex；candidate 不出现在默认 query；confirmed 可返回。

```python
response = client.post(f"/api/knowledge-base/{kb_id}/graph/query", json={"query": "臭氧", "depth": 2})
assert response.status_code == 200
assert {item["review_status"] for item in response.json()["entities"]} == {"confirmed"}

response = client.patch(
    f"/api/knowledge-base/{kb_id}/graph/entities/{entity_id}",
    json={"review_status": "confirmed"},
    headers={"X-User-Id": "viewer"},
)
assert response.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/api/test_knowledge_graph_routes.py -q
```

Expected: router module missing.

- [ ] **Step 3: 实现路由和响应模型**

Router prefix 为 `/knowledge-base/{kb_id}/graph`，由 `core/routing.py` 再挂 `/api`。提供：status、schema GET/PUT、query、entities CRUD、relations CRUD、merge、retry-failed、reindex。路由只校验输入、权限和组装响应；业务调用 repository/ingestion/outbox service。

`GraphQueryRequest` 固定限制：`depth` 1..2、`limit` 1..200；默认状态为 confirmed/published。任何请求都先加载 KB 并调用现有 `KnowledgeBasePermissions`。

- [ ] **Step 4: 运行 API 测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/api/test_knowledge_graph_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/knowledge_graph_routes.py backend/app/core/routing.py backend/app/knowledge_base/graph_schemas.py backend/tests/api/test_knowledge_graph_routes.py
git commit -m "feat: 增加知识库图谱管理接口"
```

### Task 11: 实现普通 RAG 与图检索 RRF 融合

**Files:**

- Create: `backend/app/knowledge_base/retrieval_service.py`
- Modify: `backend/app/knowledge_base/service.py`
- Modify: `backend/app/knowledge_base/schemas.py`
- Test: `backend/tests/knowledge_base/test_graph_retrieval.py`
- Test: `backend/tests/knowledge_base/test_knowledge_qa_graph_compat.py`

- [ ] **Step 1: 写种子、BFS、RRF 和跨库隔离测试**

```python
results = await service.search(
    query="臭氧零点漂移",
    kb_ids=["kb1"],
    top_k=5,
    use_graph_retrieval=True,
)
assert results[0]["chunk_id"] == "graph-supported-chunk"
assert results[0]["fusion_sources"] == ["chunk", "graph"]
assert results[0]["matched_entity_ids"]
assert results[0]["graph_paths"]

cross_kb = await service.search(query="臭氧", kb_ids=["kb1", "kb2"], top_k=10, use_graph_retrieval=True)
assert all(path["kb_id"] == item["knowledge_base_id"] for item in cross_kb for path in item["graph_paths"])
```

另测 candidate/rejected/archived 不作为种子；关闭图检索时结果与旧 search 排名一致。兼容测试 monkeypatch `KnowledgeBaseService.search()`，验证 knowledge QA 路由仍消费统一 Chunk contract，并忽略新增 graph metadata 时不会破坏来源渲染。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_retrieval.py tests/knowledge_base/test_knowledge_qa_graph_compat.py -q
```

Expected: import failure for `retrieval_service`.

- [ ] **Step 3: 实现检索服务**

`KnowledgeRetrievalService.search()` 的参数固定为 `query`、`kb_ids`、`top_k`、`use_graph_retrieval=True`、`graph_depth=2`、`graph_seed_top_k=10`、`graph_chunk_top_k=20`、`graph_weight=1.0`，返回 `list[dict[str, Any]]`。静态方法 `reciprocal_rank_fusion(chunk_results, graph_results, graph_weight, k=60.0)` 以 `chunk_id` 去重，对普通排名增加 `1/(k+rank)`，对图排名增加 `graph_weight/(k+rank)`，降序返回并保留两侧 metadata。

每个 KB 独立执行：chunk hybrid search；entity/relation typed search；普通命中 Chunk 的 Mention 补种子；repository depth<=2 BFS；Mention 转相关 Chunk；按图路径支持数和种子排名排序；RRF 融合。最后复用现有 reranker。结果包含 `fusion_sources`、matched IDs、最多 10 条有界 graph path、文档和页码来源。

修改 `KnowledgeBaseService.search()` 委托新服务；给 SearchRequest 增加上述参数，保持默认普通调用兼容。

- [ ] **Step 4: 运行检索回归**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_retrieval.py tests/knowledge_base/test_knowledge_qa_graph_compat.py -q
```

Expected: graph tests pass; knowledge QA regression remains green.

- [ ] **Step 5: 提交**

```bash
git add backend/app/knowledge_base/retrieval_service.py backend/app/knowledge_base/service.py backend/app/knowledge_base/schemas.py backend/tests/knowledge_base/test_graph_retrieval.py backend/tests/knowledge_base/test_knowledge_qa_graph_compat.py
git commit -m "feat: 融合知识库和图谱检索"
```

### Task 12: 将 Agent 图谱工具改为使用知识库 ID

**Files:**

- Create: `backend/app/tools/knowledge/knowledge_graph_query/tool.py`
- Create: `backend/app/tools/knowledge/knowledge_graph_query/__init__.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent/prompts/tool_registry.py`
- Modify: `backend/app/agent/react_agent.py`
- Modify: `backend/app/agent/prompts/ops_prompt.py`
- Test: `backend/tests/tools/knowledge/test_knowledge_graph_query_tool.py`
- Test: `backend/tests/test_agent_knowledge_graph_context.py`

- [ ] **Step 1: 写工具与上下文测试**

```python
result = await KnowledgeGraphQueryTool(service=fake_service).execute(
    query="臭氧零漂",
    knowledge_base_ids=["kb1"],
    depth=2,
)
assert result["success"] is True
assert result["data"]["chunks"][0]["knowledge_base_id"] == "kb1"
assert "candidate" not in {e["review_status"] for e in result["data"]["entities"]}
```

Agent 测试断言 prompt/tool context 不再读取 `backend_data_registry/cognitive_maps`，并把请求已有 `knowledge_base_ids` 传给工具。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/tools/knowledge/test_knowledge_graph_query_tool.py tests/test_agent_knowledge_graph_context.py -q
```

Expected: tool module missing.

- [ ] **Step 3: 实现统一工具并切换 prompt**

工具 schema：

```python
{
    "name": "knowledge_graph_query",
    "description": "在已选择知识库内进行可信实体关系检索，并返回可追溯原文分块。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "knowledge_base_ids": {"type": "array", "items": {"type": "string"}},
            "depth": {"type": "integer", "minimum": 1, "maximum": 2},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["query", "knowledge_base_ids"],
    },
}
```

工具调用 `KnowledgeRetrievalService.search(use_graph_retrieval=True)`，返回统一 Chunk 结果而不是独立图 JSON。将 query/ops 模式旧 cognitive 工具替换为 `knowledge_graph_query`；保留 graph 编辑模式到前端迁移结束。删除 `react_agent.py` 的全局 cognitive map prompt 注入，知识库选择继续走现有 request/context。

- [ ] **Step 4: 运行 Agent 和工具测试**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/tools/knowledge/test_knowledge_graph_query_tool.py tests/test_agent_knowledge_graph_context.py tests/test_graph_agent_tools.py -q
```

Expected: new tool tests pass; graph editor tests remain until final cutover.

- [ ] **Step 5: 提交**

```bash
git add backend/app/tools/knowledge/knowledge_graph_query backend/app/tools/__init__.py backend/app/agent/prompts/tool_registry.py backend/app/agent/react_agent.py backend/app/agent/prompts/ops_prompt.py backend/tests/tools/knowledge/test_knowledge_graph_query_tool.py backend/tests/test_agent_knowledge_graph_context.py
git commit -m "feat: Agent按知识库使用图谱检索"
```

---

## Phase 5：前端统一工作台

### Task 13: 扩展知识库 API 客户端和前端契约

**Files:**

- Modify: `frontend/src/api/knowledgeBase.js`
- Create: `frontend/src/api/knowledgeBaseGraph.test.mjs`
- Modify: `frontend/src/stores/knowledgeBaseStore.js`

- [ ] **Step 1: 写 API URL 和方法契约测试**

```javascript
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./knowledgeBase.js', import.meta.url), 'utf8')

test('knowledge base client exposes replacement and graph child resources', () => {
  assert.match(source, /replaceDocument\(kbId, docId, file/)
  assert.match(source, /documents\/\$\{docId\}\/content/)
  assert.match(source, /getKnowledgeGraphStatus/)
  assert.match(source, /queryKnowledgeGraph/)
  assert.match(source, /updateKnowledgeGraphEntity/)
  assert.match(source, /mergeKnowledgeGraphEntities/)
  assert.match(source, /reindexKnowledgeGraph/)
})
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd frontend && node --test src/api/knowledgeBaseGraph.test.mjs
```

Expected: assertions fail for missing methods.

- [ ] **Step 3: 实现客户端和 store actions**

`knowledgeBase.js` 新增 `replaceDocument`、图 status/schema/query/entity/relation/merge/retry/reindex 方法，全部复用现有 `request()` 和 KB URL。Store 增加 `graphStatus`、`graphEntities`、`graphRelations`、`loadGraph()`、`replaceDocument()`；错误必须写入现有 error state，不静默吞掉。

- [ ] **Step 4: 运行 API 契约测试**

```bash
cd frontend && node --test src/api/knowledgeBaseGraph.test.mjs
```

Expected: test passes.

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/knowledgeBase.js frontend/src/api/knowledgeBaseGraph.test.mjs frontend/src/stores/knowledgeBaseStore.js
git commit -m "feat: 扩展知识库图谱前端协议"
```

### Task 14: 将图谱审核和可视化并入知识库详情

**Files:**

- Create: `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`
- Create: `frontend/src/components/management/knowledge-base/KnowledgeGraphReview.vue`
- Create: `frontend/src/components/management/knowledge-base/KnowledgeGraphStatus.vue`
- Modify: `frontend/src/components/management/KnowledgeBasePanel.vue`
- Modify: `frontend/src/components/management/CognitiveMapPanel.vue`
- Test: `frontend/src/components/management/knowledge-base/knowledge-graph-tab-contract.test.mjs`

- [ ] **Step 1: 写统一工作台契约测试**

测试源码必须包含知识库 `documents/retrieval/graph/schema` tab；文档列表有替换按钮；图谱组件不包含上传或独立 build；候选/确认/拒绝筛选和 merge action 存在；CognitiveMapPanel 显示只读迁移提示而不是新建入口。

```javascript
assert.match(panel, /activeTab/)
assert.match(panel, /value:\s*'graph'/)
assert.match(panel, /@replace-doc/)
assert.match(graphTab, /candidate/)
assert.match(graphTab, /confirmed/)
assert.match(graphTab, /rejected/)
assert.doesNotMatch(graphTab, /uploadCognitiveMapFile|buildCognitiveMap/)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd frontend && node --test src/components/management/knowledge-base/knowledge-graph-tab-contract.test.mjs
```

Expected: component files are missing.

- [ ] **Step 3: 实现三组件和面板集成**

`KnowledgeGraphStatus` 显示 Chunk/graph pending、failed、candidate、confirmed 计数和 retry/reindex；`KnowledgeGraphReview` 提供状态过滤、确认、拒绝、编辑、合并；`KnowledgeGraphTab` 复用 `cognitiveMapGraphLinks.js` 和认知地图 ECharts 配置展示 query 返回的实体关系。`KnowledgeBasePanel` 增加 tabs 和替换文件 input；所有图谱请求使用 current KB ID。

保留 `CognitiveMapPanel` 的只读入口用于迁移对账，但移除“新建、上传、构建、绑定”交互；页面明确显示“认知地图已并入知识库，请在知识库图谱页管理”。

- [ ] **Step 4: 运行前端测试和构建**

```bash
cd frontend && node --test src/api/knowledgeBaseGraph.test.mjs src/components/management/knowledge-base/knowledge-graph-tab-contract.test.mjs
cd frontend && npm run build
```

Expected: Node tests pass; Vite build exits 0.

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/management/knowledge-base frontend/src/components/management/KnowledgeBasePanel.vue frontend/src/components/management/CognitiveMapPanel.vue
git commit -m "feat: 将知识图谱并入知识库工作台"
```

---

## Phase 6：数据迁移和旧机制下线

### Task 15: 回填现有 Qdrant Chunk 到 PostgreSQL

**Files:**

- Create: `backend/scripts/migrate_unified_knowledge_graph.py`
- Test: `backend/tests/knowledge_base/test_chunk_backfill_migration.py`

- [ ] **Step 1: 写可重复执行迁移测试**

Fake Qdrant scroll 返回两个旧 payload；运行两次后 PostgreSQL 仍只有两个 Chunk，稳定键一致；缺少位置字段时 `chunk_metadata.metadata_recovered` 为 false。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_chunk_backfill_migration.py -q
```

Expected: migration module missing.

- [ ] **Step 3: 实现 dry-run 和 apply**

CLI：

```text
python scripts/migrate_unified_knowledge_graph.py --dry-run
python scripts/migrate_unified_knowledge_graph.py --apply --kb-id <id>
python scripts/migrate_unified_knowledge_graph.py --verify --kb-id <id>
```

默认必须 dry-run；`--apply` 才写库。按 `document_id + chunk_id/content_hash` 幂等 upsert；输出每 KB 的 Qdrant point、PostgreSQL Chunk、缺失文档和不可恢复元数据数量。不得打印正文或敏感配置。

- [ ] **Step 4: 运行测试和 CLI 帮助**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_chunk_backfill_migration.py -q
cd backend && conda run -p /root/miniconda3/envs/backend_py311 python scripts/migrate_unified_knowledge_graph.py --help
```

Expected: tests pass; help lists dry-run/apply/verify.

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/migrate_unified_knowledge_graph.py backend/tests/knowledge_base/test_chunk_backfill_migration.py
git commit -m "feat: 增加知识库分块回填迁移"
```

### Task 16: 迁移认知地图到知识库图谱

**Files:**

- Create: `backend/scripts/migrate_cognitive_maps_to_knowledge_bases.py`
- Test: `backend/tests/knowledge_base/test_cognitive_map_migration.py`

- [ ] **Step 1: 写三类数据迁移测试**

Fixture 包含 published、candidate、merged 实体，重复关系、Evidence、Schema 和 ops binding。断言迁移后审核状态、Mention、Schema 正确；有任意启用 binding 的导入知识库被标记为 `is_default=true`，供未显式传 `knowledge_base_ids` 的后台 Agent 使用；重复执行数量不变；无 Evidence 的人工内容 `created_by=migration` 且保留。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_cognitive_map_migration.py -q
```

Expected: migration module missing.

- [ ] **Step 3: 实现映射和对账 CLI**

CLI 支持 `--source-root`、`--dry-run`、`--apply`、`--verify`。每张 map 默认创建对应 KB；允许 `--map-to-kb map_id=kb_id` 合并到已有 KB。稳定迁移键写入 `attributes.migration_source`，格式 `cognitive-map:{map_id}:{source_id}`。存在启用 Binding 的地图将对应 KB 标记为 `is_default=true`；不迁移 mode-map 绑定表，也不增加新的绑定机制。Agent 显式传入 `knowledge_base_ids` 时始终以请求为准，未传时只选择有权限的默认知识库。

Verify 输出每张地图：文件、实体、关系、各审核状态、Mention 和 Schema 计数差异；任一不一致退出码为 1。

- [ ] **Step 4: 在测试 fixture 上执行 apply + verify**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_cognitive_map_migration.py -q
cd backend && conda run -p /root/miniconda3/envs/backend_py311 python scripts/migrate_cognitive_maps_to_knowledge_bases.py --help
```

Expected: tests pass; help exits 0.

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/migrate_cognitive_maps_to_knowledge_bases.py backend/tests/knowledge_base/test_cognitive_map_migration.py
git commit -m "feat: 迁移认知地图到知识库图谱"
```

### Task 17: 下线独立认知地图运行链路

**Files:**

- Delete: `backend/app/api/cognitive_map_routes.py`
- Delete: `backend/app/tools/cognition/cognitive_map_entity_query/`
- Delete: `backend/app/tools/cognition/cognitive_map_graph_traverse/`
- Delete: `backend/app/tools/analysis/cognitive_map_guidance/`
- Modify: `backend/app/core/routing.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent/prompts/tool_registry.py`
- Modify: `backend/app/agent/prompts/graph_prompt.py`
- Modify: `frontend/src/api/cognitiveMap.js`
- Modify: `frontend/src/components/AssistantSidebar.vue`
- Modify: `frontend/src/components/management/CognitiveMapGraphChat.vue`
- Delete: `frontend/src/components/management/CognitiveMapPanel.vue`
- Test: `backend/tests/test_legacy_cognitive_map_runtime_removed.py`
- Test: `frontend/src/components/management/knowledge-base/legacy-cognitive-map-removed.test.mjs`

- [ ] **Step 1: 写旧运行时删除契约测试**

Backend test 扫描 router registry、tool registry 和 react agent，断言没有 `app.api.cognitive_map_routes`、旧三个工具名或 `backend_data_registry/cognitive_maps`。Frontend test 断言侧栏没有独立 cognitive-map 项，Graph Chat 使用 `knowledge_base_id`，不存在 cognitive map API import。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_legacy_cognitive_map_runtime_removed.py -q
cd frontend && node --test src/components/management/knowledge-base/legacy-cognitive-map-removed.test.mjs
```

Expected: both fail because legacy runtime is still registered.

- [ ] **Step 3: 删除旧入口并迁移 Graph 对话**

删除旧 router/tools/panel；Graph 对话作为 `KnowledgeGraphTab` 子面板继续存在，context 改为：

```json
{
  "knowledge_base_id": "kb_xxx",
  "selected_item": {"kind": "entity", "id": "entity_xxx"},
  "visible_entity_ids": [],
  "visible_relation_ids": []
}
```

Graph prompt 只允许调用知识库图谱子资源，不再读写 JSON。删除 cognition 旧测试或将仍有价值的 extractor/view 测试移动到 knowledge_base 测试目录。不要在代码中自动删除磁盘上的旧 cognitive_maps 数据；部署对账成功后由操作步骤单独备份/清理。

- [ ] **Step 4: 运行删除契约和相关回归**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_legacy_cognitive_map_runtime_removed.py tests/tools/knowledge tests/knowledge_base -q
cd frontend && node --test src/components/management/knowledge-base/*.test.mjs src/api/knowledgeBaseGraph.test.mjs
cd frontend && npm run build
```

Expected: all selected tests pass; build exits 0.

- [ ] **Step 5: 提交**

```bash
git add -A backend/app/api/cognitive_map_routes.py backend/app/tools/cognition backend/app/tools/analysis/cognitive_map_guidance backend/app/core/routing.py backend/app/tools/__init__.py backend/app/agent/prompts frontend/src/api/cognitiveMap.js frontend/src/components/AssistantSidebar.vue frontend/src/components/management
git add backend/tests/test_legacy_cognitive_map_runtime_removed.py frontend/src/components/management/knowledge-base/legacy-cognitive-map-removed.test.mjs
git commit -m "refactor: 下线独立认知地图运行机制"
```

---

## Phase 7：验证、文档和发布门禁

### Task 18: 完成对账、性能门禁和运维文档

**Files:**

- Create: `backend/tests/integration/test_unified_knowledge_graph_flow.py`
- Create: `backend/tests/knowledge_base/test_graph_retrieval_limits.py`
- Create: `docs/knowledge-base-graph-operations.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 写完整端到端集成测试**

测试流程固定为：创建 KB → 上传文档 A → 确认关系 → 上传文档 B 支持同一关系 → 图融合检索 → 直接替换 A → 删除 B → 检查共享内容与孤儿 → 从 PostgreSQL 重建 Qdrant → 再次检索。断言每一步 PostgreSQL/Qdrant 计数和来源一致。

检索限制测试构造超过 200 个节点和 3 跳路径，断言只返回 2 跳、最多配置数量、graph path 摘要不超过 10 条。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/integration/test_unified_knowledge_graph_flow.py tests/knowledge_base/test_graph_retrieval_limits.py -q
```

Expected: tests fail until fixtures and all unified services are wired.

- [ ] **Step 3: 补齐集成 wiring 和运维文档**

运维文档必须包含：迁移前备份、模型迁移、Chunk 回填 dry-run/apply/verify、认知地图 dry-run/apply/verify、Outbox backlog 检查、Qdrant 重建、切换旧路由、失败排查和旧目录人工清理命令。`CLAUDE.md` 将“知识库权限”和“认知地图”说明更新为统一知识库图谱架构。

- [ ] **Step 4: 执行完整验证矩阵**

Backend targeted:

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base tests/tools/knowledge tests/api/test_knowledge_graph_routes.py tests/integration/test_unified_knowledge_graph_flow.py -q
```

Backend regression:

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 pytest tests -q
```

Formatting/static validation:

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 ruff check app/knowledge_base app/api/knowledge_graph_routes.py scripts/migrate_unified_knowledge_graph.py scripts/migrate_cognitive_maps_to_knowledge_bases.py tests/knowledge_base tests/tools/knowledge
cd backend && conda run -p /root/miniconda3/envs/backend_py311 ruff format --check app/knowledge_base app/api/knowledge_graph_routes.py scripts/migrate_unified_knowledge_graph.py scripts/migrate_cognitive_maps_to_knowledge_bases.py tests/knowledge_base tests/tools/knowledge
```

Frontend:

```bash
cd frontend && node --test src/api/*.test.mjs src/components/management/knowledge-base/*.test.mjs
cd frontend && npm run build
```

Expected: all commands exit 0. Any pre-existing unrelated failure must be recorded with the exact failing test and demonstrated unchanged from the base commit before proceeding.

- [ ] **Step 5: 检查迁移和索引不变量**

在测试/预发布数据库执行：

```bash
cd backend && conda run -p /root/miniconda3/envs/backend_py311 python scripts/migrate_unified_knowledge_graph.py --verify
cd backend && conda run -p /root/miniconda3/envs/backend_py311 python scripts/migrate_cognitive_maps_to_knowledge_bases.py --verify
```

Expected: exit 0; no missing Chunk, duplicate graph identity, orphan active relation, stale generation task or Qdrant orphan point.

- [ ] **Step 6: 提交**

```bash
git add backend/tests/integration/test_unified_knowledge_graph_flow.py backend/tests/knowledge_base/test_graph_retrieval_limits.py docs/knowledge-base-graph-operations.md CLAUDE.md
git commit -m "docs: 完善统一知识图谱发布门禁"
```

---

## 最终验收清单

- [ ] 每个知识库只拥有一个文档摄取入口、一个 Qdrant Collection 和一套图谱事实数据。
- [ ] 新文档只处理新增 Chunk，不触发其他文档重建。
- [ ] 原位替换复用未变化 Chunk，清理全部旧版本数据且没有回滚入口。
- [ ] 删除文档通过 Mention 引用保留仍被其他文档支持的实体和关系。
- [ ] Candidate 不进入默认 Agent 图检索；Confirmed/Published 无需整库重建即可生效。
- [ ] 普通召回和图召回通过 RRF 返回同一 Chunk contract。
- [ ] 跨知识库查询只在结果层融合，实体身份、权限和图遍历不跨库。
- [ ] PostgreSQL 可完整重建 Qdrant 的 chunk/entity/relation Point。
- [ ] Outbox 可幂等重试，旧 generation 任务无法回写。
- [ ] 知识库权限同时约束文档、图查询和图编辑。
- [ ] 现有认知地图数据、Schema、审核状态和 ops 使用方式完成迁移对账。
- [ ] 运行时不再读取独立 cognitive map JSON/PropertyGraphStore。
- [ ] 后端全量测试、Ruff、前端 Node 测试和 Vite build 全部通过，或对基线既有失败留有可复验证据。
