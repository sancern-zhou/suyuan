# Scenario-Driven Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scene-driven knowledge-graph workflow where users describe one business scene per knowledge base, upload representative documents, confirm an automatically discovered business model, add natural-language rules and confirmed facts, and use the resulting graph for evidence-backed Agent retrieval.

**Architecture:** Keep PostgreSQL as the sole fact source and Qdrant as a rebuildable `chunk/entity/relation` index. Add versioned scene profiles, business rules, user facts, schema suggestions, and extraction runs around the existing graph entities/relations/Mentions. Compile user-facing business language into the existing strict `GraphExtractionSchema`, then upgrade extraction and retrieval without introducing Neo4j or a second graph fact store.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, Pydantic, PostgreSQL JSONB, Qdrant, LlamaIndex-compatible project LLM adapter, Vue 3, Pinia, pytest, Playwright/Vite build.

---

## Delivery boundaries and sequence

This is one ordered program with three releasable checkpoints:

1. **Scene discovery and confirmation:** Tasks 1-6. Users can create a scene profile from representative documents and compile a confirmed internal Schema.
2. **Rules and trusted facts:** Tasks 7-9. Users can add natural-language rules and directly asserted `confirmed` facts.
3. **Extraction and retrieval quality:** Tasks 10-14. The graph uses scene constraints, exact evidence, extraction provenance, entity linking, and graph-aware retrieval.

Do not start a later checkpoint until the previous checkpoint's focused test suite passes. Run all backend commands from `/home/xckj/suyuan/backend` with:

```bash
conda run -p /root/miniconda3/envs/backend_py311 <command>
```

Do not include or alter the unrelated dirty worktree files shown by `git status`. Every commit below must stage only the listed task files.

## File and responsibility map

### Backend files to create

- `backend/app/knowledge_base/scene_models.py`: SQLAlchemy persistence models for scene profiles, suggestions, rules, user facts, and extraction runs.
- `backend/app/knowledge_base/scene_schemas.py`: Pydantic API and service contracts; no database operations.
- `backend/app/knowledge_base/scene_repository.py`: transactional CRUD and version queries for scene resources.
- `backend/app/knowledge_base/scene_discovery.py`: representative-document sampling and LLM scene discovery.
- `backend/app/knowledge_base/schema_compiler.py`: deterministic conversion from confirmed business language to `GraphExtractionSchema`.
- `backend/app/knowledge_base/business_rule_service.py`: rule parsing, confirmation, versioning, and active-rule assembly.
- `backend/app/knowledge_base/user_fact_service.py`: natural-language fact parsing, ambiguity handling, entity linking, and confirmed fact persistence.
- `backend/app/knowledge_base/extraction_run_repository.py`: raw model-response provenance and validation diagnostics.
- `backend/app/knowledge_base/entity_linker.py`: exact, alias, and vector-assisted entity-link decisions.
- `backend/app/knowledge_base/graph_retrieval.py`: entity/relation seeds, graph traversal, Mention-to-Chunk mapping, and RRF fusion.
- `backend/app/api/knowledge_scene_routes.py`: scene discovery, confirmation, rule, fact, and suggestion endpoints.
- `backend/app/alembic/versions/add_scenario_driven_knowledge_graph.py`: idempotent PostgreSQL migration.

### Backend files to modify

- `backend/app/knowledge_base/models.py`: add scene-state/version columns to `KnowledgeBase`.
- `backend/app/knowledge_base/graph_extraction/models.py`: enrich Schema metadata and evidence contracts.
- `backend/app/knowledge_base/graph_schemas.py`: expose rule/fact/extraction response types where graph APIs need them.
- `backend/app/knowledge_base/graph_extraction/llm_factory.py`: build prompts entirely from the active scene Schema and capture raw responses.
- `backend/app/knowledge_base/graph_extraction/providers/llamaindex_extractor.py`: preserve evidence spans and confidence.
- `backend/app/knowledge_base/graph_extractor.py`: pass scene context and map linked entities/relations.
- `backend/app/knowledge_base/ingestion_service.py`: enforce scene readiness, run extraction provenance, evidence validation, and entity linking.
- `backend/app/knowledge_base/graph_repository.py`: persist source type, Schema version, and confirmed user facts.
- `backend/app/knowledge_base/retrieval_service.py`: fuse ordinary RAG and graph-derived Chunk results.
- `backend/app/api/knowledge_graph_routes.py`: gate graph build by scene state and expose provenance fields.
- `backend/app/core/routing.py`: register the scene router.

### Frontend files to create

- `frontend/src/components/management/knowledge-base/KnowledgeSceneSetup.vue`: scene goal and representative-document readiness wizard.
- `frontend/src/components/management/knowledge-base/KnowledgeSceneDraft.vue`: business-object/business-logic confirmation UI.
- `frontend/src/components/management/knowledge-base/KnowledgeBusinessRules.vue`: list, parse preview, confirm, archive rules.
- `frontend/src/components/management/knowledge-base/KnowledgeUserFacts.vue`: natural-language fact entry and ambiguity resolution.

### Frontend files to modify

- `frontend/src/api/knowledgeBase.js`: scene, rule, fact, and suggestion API functions.
- `frontend/src/stores/knowledgeBaseStore.js`: scene state and async actions.
- `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`: render setup/confirmation before graph workbench.
- `frontend/src/components/management/knowledge-base/KnowledgeGraphDetailPanel.vue`: show source kind, exact evidence, and version provenance.
- `frontend/src/components/management/KnowledgeBasePanel.vue`: pass document counts and refresh events.

---

### Task 1: Persist scene state and versioned resources

**Files:**
- Create: `backend/app/knowledge_base/scene_models.py`
- Modify: `backend/app/knowledge_base/models.py`
- Modify: `backend/app/knowledge_base/graph_models.py`
- Test: `backend/tests/knowledge_base/test_scene_models.py`

- [ ] **Step 1: Write the failing model-contract test**

```python
from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base.scene_models import (
    KnowledgeBusinessRule,
    KnowledgeGraphExtractionRun,
    KnowledgeSceneProfile,
    KnowledgeSchemaSuggestion,
    KnowledgeUserFact,
)


def test_scene_tables_and_kb_state_contract():
    assert KnowledgeBase.__table__.c.scene_status.default.arg == "awaiting_documents"
    assert KnowledgeBase.__table__.c.scene_profile_version.default.arg == 0
    assert KnowledgeBase.__table__.c.schema_version.default.arg == 0
    assert KnowledgeSceneProfile.__tablename__ == "knowledge_scene_profiles"
    assert KnowledgeBusinessRule.__tablename__ == "knowledge_business_rules"
    assert KnowledgeUserFact.__tablename__ == "knowledge_user_facts"
    assert KnowledgeSchemaSuggestion.__tablename__ == "knowledge_schema_suggestions"
    assert KnowledgeGraphExtractionRun.__tablename__ == "knowledge_graph_extraction_runs"
    assert KnowledgeUserFact.__table__.c.review_status.default.arg == "draft"
    assert KnowledgeGraphRelation.__table__.c.source_type.default.arg == "document_fact"
    assert KnowledgeGraphRelation.__table__.c.schema_version.default.arg == 0
```

- [ ] **Step 2: Run the test and verify the missing-model failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_scene_models.py -q
```

Expected: collection fails because `app.knowledge_base.scene_models` does not exist.

- [ ] **Step 3: Add focused SQLAlchemy models**

Implement UUID string primary keys and JSON columns following the existing graph model style. Use these required columns:

```python
class KnowledgeSceneProfile(Base):
    __tablename__ = "knowledge_scene_profiles"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    scene_goal = Column(Text, nullable=False)
    desired_questions = Column(JSON, nullable=False, default=list)
    business_objects = Column(JSON, nullable=False, default=list)
    business_logic = Column(JSON, nullable=False, default=list)
    ignored_content = Column(JSON, nullable=False, default=list)
    source_document_ids = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="draft")
    discovery_diagnostics = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime)


class KnowledgeBusinessRule(Base):
    __tablename__ = "knowledge_business_rules"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    structured_rule = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="draft")
    version = Column(Integer, nullable=False)
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime)


class KnowledgeUserFact(Base):
    __tablename__ = "knowledge_user_facts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    structured_fact = Column(JSON, nullable=False)
    entity_link_decisions = Column(JSON, nullable=False, default=list)
    review_status = Column(String(24), nullable=False, default="draft")
    source_type = Column(String(24), nullable=False, default="user_asserted")
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class KnowledgeSchemaSuggestion(Base):
    __tablename__ = "knowledge_schema_suggestions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion_type = Column(String(32), nullable=False)
    payload = Column(JSON, nullable=False)
    evidence = Column(JSON, nullable=False, default=list)
    status = Column(String(24), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class KnowledgeGraphExtractionRun(Base):
    __tablename__ = "knowledge_graph_extraction_runs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String(36), ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    content_generation = Column(Integer, nullable=False)
    scene_profile_version = Column(Integer, nullable=False)
    schema_version = Column(Integer, nullable=False)
    prompt_version = Column(String(40), nullable=False)
    model_name = Column(String(160), nullable=False)
    model_params = Column(JSON, nullable=False, default=dict)
    raw_response = Column(JSON, nullable=False, default=dict)
    parsed_response = Column(JSON, nullable=False, default=dict)
    validation_errors = Column(JSON, nullable=False, default=list)
    token_usage = Column(JSON, nullable=False, default=dict)
    latency_ms = Column(Integer)
    status = Column(String(24), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
```

Add to `KnowledgeBase`:

```python
scene_status = Column(String(32), nullable=False, default="awaiting_documents")
scene_profile_version = Column(Integer, nullable=False, default=0, server_default="0")
schema_version = Column(Integer, nullable=False, default=0, server_default="0")
rule_version = Column(Integer, nullable=False, default=0, server_default="0")
```

Add to `KnowledgeGraphEntity` and `KnowledgeGraphRelation`:

```python
source_type = Column(String(24), nullable=False, default="document_fact")
scene_profile_version = Column(Integer, nullable=False, default=0, server_default="0")
schema_version = Column(Integer, nullable=False, default=0, server_default="0")
rule_version = Column(Integer, nullable=False, default=0, server_default="0")
```

Add a uniqueness constraint for `(kb_id, version)` on scene profiles, plus indexes on `(kb_id, status)` for all workflow tables. Business-rule versions are knowledge-base-wide activation revisions: draft rules use version `0`, and confirmation assigns the next `KnowledgeBase.rule_version`, so add a partial PostgreSQL unique index on `(kb_id, version)` where `status='confirmed'`.

- [ ] **Step 4: Run the focused model test**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit the model contract**

```bash
git add backend/app/knowledge_base/models.py backend/app/knowledge_base/graph_models.py backend/app/knowledge_base/scene_models.py backend/tests/knowledge_base/test_scene_models.py
git commit -m "feat: add scene-driven graph persistence models"
```

---

### Task 2: Add an idempotent PostgreSQL migration

**Files:**
- Create: `backend/app/alembic/versions/add_scenario_driven_knowledge_graph.py`
- Test: `backend/tests/knowledge_base/test_scene_migration.py`

- [ ] **Step 1: Write a migration declaration test**

```python
from app.alembic.versions import add_scenario_driven_knowledge_graph as migration


def test_migration_declares_all_scene_tables_and_columns():
    sql = "\n".join(migration.KNOWLEDGE_BASE_ALTERS)
    assert "scene_status" in sql
    assert "scene_profile_version" in sql
    assert "schema_version" in sql
    assert "rule_version" in sql
    graph_sql = "\n".join(migration.GRAPH_FACT_ALTERS)
    assert "source_type" in graph_sql
    assert "scene_profile_version" in graph_sql
    assert {table.name for table in migration.SCENE_TABLES} == {
        "knowledge_scene_profiles",
        "knowledge_business_rules",
        "knowledge_user_facts",
        "knowledge_schema_suggestions",
        "knowledge_graph_extraction_runs",
    }
```

- [ ] **Step 2: Verify the test fails because the migration is absent**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_scene_migration.py -q
```

Expected: import error for the missing migration module.

- [ ] **Step 3: Implement the migration**

Follow `create_unified_knowledge_graph.py`: require PostgreSQL, use `ADD COLUMN IF NOT EXISTS`, create model tables with `checkfirst=True`, and create the unique/index definitions explicitly. Export:

```python
KNOWLEDGE_BASE_ALTERS = [
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS scene_status VARCHAR(32) NOT NULL DEFAULT 'awaiting_documents'",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS scene_profile_version INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS schema_version INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS rule_version INTEGER NOT NULL DEFAULT 0",
]

GRAPH_FACT_ALTERS = [
    *[
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS source_type VARCHAR(24) NOT NULL DEFAULT 'document_fact'"
        for table in ("knowledge_graph_entities", "knowledge_graph_relations")
    ],
    *[
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} INTEGER NOT NULL DEFAULT 0"
        for table in ("knowledge_graph_entities", "knowledge_graph_relations")
        for column in ("scene_profile_version", "schema_version", "rule_version")
    ],
]

SCENE_TABLES = [
    KnowledgeSceneProfile.__table__,
    KnowledgeBusinessRule.__table__,
    KnowledgeUserFact.__table__,
    KnowledgeSchemaSuggestion.__table__,
    KnowledgeGraphExtractionRun.__table__,
]
```

Backfill existing knowledge bases as follows:

```sql
UPDATE knowledge_bases kb
SET scene_status = CASE
    WHEN EXISTS (SELECT 1 FROM documents d WHERE d.knowledge_base_id = kb.id)
      THEN 'awaiting_confirmation'
    ELSE 'awaiting_documents'
END
WHERE scene_profile_version = 0;
```

- [ ] **Step 4: Run migration tests and the existing unified-model tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_scene_migration.py \
  tests/knowledge_base/test_unified_graph_models.py -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/alembic/versions/add_scenario_driven_knowledge_graph.py backend/tests/knowledge_base/test_scene_migration.py
git commit -m "feat: migrate scene-driven graph resources"
```

---

### Task 3: Define business-facing contracts and deterministic Schema compilation

**Files:**
- Create: `backend/app/knowledge_base/scene_schemas.py`
- Create: `backend/app/knowledge_base/schema_compiler.py`
- Modify: `backend/app/knowledge_base/graph_extraction/models.py`
- Test: `backend/tests/knowledge_base/test_schema_compiler.py`

- [ ] **Step 1: Write compiler tests for valid, duplicate, and conflicting logic**

```python
import pytest

from app.knowledge_base.scene_schemas import BusinessLogic, BusinessObject, SceneDraft
from app.knowledge_base.schema_compiler import SceneSchemaCompiler, SchemaCompilationError


def test_compile_business_language_to_strict_schema():
    draft = SceneDraft(
        scene_goal="分析企业噪声投诉与整改闭环",
        desired_questions=["哪些噪声源导致投诉？"],
        business_objects=[
            BusinessObject(key="enterprise", name="企业", description="被监管企业", aliases=[]),
            BusinessObject(key="noise_source", name="噪声源", description="产生噪声的设备或工艺", aliases=["声源"]),
        ],
        business_logic=[
            BusinessLogic(
                key="enterprise_has_noise_source",
                statement="企业拥有噪声源",
                source_key="enterprise",
                relation_key="has_noise_source",
                target_key="noise_source",
                policy="allowed",
            )
        ],
        ignored_content=["页眉页脚"],
        source_document_ids=["doc-1"],
    )
    schema = SceneSchemaCompiler().compile(draft)
    assert schema.allowed_entity_types == ["enterprise", "noise_source"]
    assert schema.allowed_relation_triplets == [
        ("enterprise", "has_noise_source", "noise_source")
    ]
    assert schema.domain_aliases == {"噪声源": ["声源"]}
    assert schema.build_requirement == draft.scene_goal


def test_compile_rejects_logic_with_unknown_endpoint():
    draft = SceneDraft.model_validate({
        "scene_goal": "噪声场景",
        "business_objects": [{"key": "enterprise", "name": "企业"}],
        "business_logic": [{
            "key": "bad",
            "statement": "企业拥有未知对象",
            "source_key": "enterprise",
            "relation_key": "has_unknown",
            "target_key": "missing",
            "policy": "allowed",
        }],
        "source_document_ids": ["doc-1"],
    })
    with pytest.raises(SchemaCompilationError, match="missing"):
        SceneSchemaCompiler().compile(draft)
```

- [ ] **Step 2: Run the test and verify missing-contract failures**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_schema_compiler.py -q
```

Expected: import failure for `scene_schemas` or `schema_compiler`.

- [ ] **Step 3: Implement the contracts**

Define constrained Pydantic models:

```python
class BusinessObject(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    aliases: list[str] = Field(default_factory=list)


class BusinessLogic(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,119}$")
    statement: str = Field(min_length=1, max_length=1000)
    source_key: str
    relation_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,119}$")
    target_key: str
    policy: Literal["required", "allowed", "forbidden"] = "allowed"


class SceneDraft(BaseModel):
    scene_goal: str = Field(min_length=5, max_length=2000)
    desired_questions: list[str] = Field(default_factory=list)
    business_objects: list[BusinessObject]
    business_logic: list[BusinessLogic]
    ignored_content: list[str] = Field(default_factory=list)
    source_document_ids: list[str] = Field(min_length=1)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
```

Extend `GraphExtractionSchema` with backward-compatible defaults:

```python
entity_type_descriptions: dict[str, str] = Field(default_factory=dict)
relation_type_descriptions: dict[str, str] = Field(default_factory=dict)
required_relation_triplets: list[tuple[str, str, str]] = Field(default_factory=list)
forbidden_relation_triplets: list[tuple[str, str, str]] = Field(default_factory=list)
ignored_content: list[str] = Field(default_factory=list)
scene_profile_version: int = 0
schema_version: int = 0
```

- [ ] **Step 4: Implement deterministic compilation**

`SceneSchemaCompiler.compile()` must validate unique keys, validate endpoints, exclude forbidden triplets from allowed triplets, map required policies separately, and return types in user-confirmed order. It must never invoke an LLM.

```python
return GraphExtractionSchema(
    allowed_entity_types=[item.key for item in draft.business_objects],
    allowed_relation_types=list(dict.fromkeys(item.relation_key for item in active_logic)),
    allowed_relation_triplets=[triplet(item) for item in active_logic],
    required_relation_triplets=[triplet(item) for item in active_logic if item.policy == "required"],
    forbidden_relation_triplets=[triplet(item) for item in forbidden_logic],
    required_evidence=True,
    build_requirement=draft.scene_goal,
    domain_aliases={item.name: item.aliases for item in draft.business_objects if item.aliases},
    entity_type_descriptions={item.key: item.description for item in draft.business_objects},
    relation_type_descriptions={item.relation_key: item.statement for item in active_logic},
    ignored_content=draft.ignored_content,
)
```

- [ ] **Step 5: Run compiler and existing extraction-contract tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_schema_compiler.py \
  tests/knowledge_base/test_graph_extraction_contracts.py -q
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/knowledge_base/scene_schemas.py backend/app/knowledge_base/schema_compiler.py backend/app/knowledge_base/graph_extraction/models.py backend/tests/knowledge_base/test_schema_compiler.py
git commit -m "feat: compile business scenes into graph schemas"
```

---

### Task 4: Implement scene repository and representative-document gate

**Files:**
- Create: `backend/app/knowledge_base/scene_repository.py`
- Test: `backend/tests/knowledge_base/test_scene_repository.py`

- [ ] **Step 1: Write repository integration tests**

```python
import pytest

from app.knowledge_base.scene_repository import RepresentativeDocumentRequired, SceneRepository


@pytest.mark.asyncio
async def test_begin_discovery_requires_completed_representative_document(db_session, kb_factory):
    kb = await kb_factory(scene_status="awaiting_documents")
    repo = SceneRepository(db_session)
    with pytest.raises(RepresentativeDocumentRequired):
        await repo.begin_discovery(kb.id, created_by="u1")


@pytest.mark.asyncio
async def test_confirm_profile_atomically_updates_versions(db_session, kb_factory, document_factory):
    kb = await kb_factory(scene_status="awaiting_documents")
    await document_factory(kb.id, status="completed")
    repo = SceneRepository(db_session)
    profile = await repo.create_draft(kb.id, scene_draft_payload(), created_by="u1")
    confirmed = await repo.confirm_profile(profile.id, compiled_schema_payload())
    await db_session.refresh(kb)
    assert confirmed.status == "confirmed"
    assert kb.scene_status == "ready"
    assert kb.scene_profile_version == 1
    assert kb.schema_version == 1
    assert kb.graph_schema["scene_profile_version"] == 1
```

- [ ] **Step 2: Run and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_scene_repository.py -q
```

Expected: import failure for `SceneRepository`.

- [ ] **Step 3: Implement transactional repository methods**

Provide exactly these public async methods: `require_representative_documents(kb_id) -> list[Document]`, `begin_discovery(kb_id, created_by) -> KnowledgeBase`, `create_draft(kb_id, draft, created_by) -> KnowledgeSceneProfile`, `get_current_profile(kb_id) -> KnowledgeSceneProfile | None`, `confirm_profile(profile_id, schema) -> KnowledgeSceneProfile`, and `list_suggestions(kb_id, status="pending") -> list[KnowledgeSchemaSuggestion]`.

`require_representative_documents()` accepts only documents whose ingestion status is `completed` or `partial` and whose Chunk count is greater than zero. `confirm_profile()` must lock both the profile and knowledge base, archive the old confirmed profile, increment versions, write the compiled Schema, set `scene_status="ready"`, and commit as one transaction.

- [ ] **Step 4: Run repository tests**

Run Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/knowledge_base/scene_repository.py backend/tests/knowledge_base/test_scene_repository.py
git commit -m "feat: manage versioned knowledge scene profiles"
```

---

### Task 5: Discover a scene from representative documents

**Files:**
- Create: `backend/app/knowledge_base/scene_discovery.py`
- Test: `backend/tests/knowledge_base/test_scene_discovery.py`

- [ ] **Step 1: Write deterministic sampling and structured-output tests**

```python
import pytest

from app.knowledge_base.scene_discovery import SceneDiscoveryService


@pytest.mark.asyncio
async def test_discovery_uses_goal_questions_and_representative_chunks():
    llm = FakeJsonLLM({
        "business_objects": [
            {"key": "enterprise", "name": "企业", "description": "被监管企业", "aliases": []},
            {"key": "noise_source", "name": "噪声源", "description": "产生噪声的对象", "aliases": ["声源"]},
        ],
        "business_logic": [{
            "key": "enterprise_has_noise_source",
            "statement": "企业拥有噪声源",
            "source_key": "enterprise",
            "relation_key": "has_noise_source",
            "target_key": "noise_source",
            "policy": "allowed",
        }],
        "ignored_content": ["页眉页脚"],
        "diagnostics": {"coverage": "sufficient", "uncertainties": []},
    })
    service = SceneDiscoveryService(llm=llm, chunk_repository=FakeChunks())
    draft = await service.discover(
        kb_id="kb1",
        scene_goal="分析企业噪声投诉与整改闭环",
        desired_questions=["企业有哪些主要噪声源？"],
        documents=[representative_document("doc1")],
    )
    assert draft.source_document_ids == ["doc1"]
    assert draft.business_objects[1].aliases == ["声源"]
    assert "企业有哪些主要噪声源" in llm.last_prompt
    assert "代表性文档" in llm.last_prompt
```

- [ ] **Step 2: Run and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_scene_discovery.py -q
```

Expected: missing service import.

- [ ] **Step 3: Implement bounded representative sampling**

Sample per document:

- title/filename;
- first Chunk;
- up to two section-leading Chunks;
- up to three evenly spaced Chunks;
- no more than 12,000 characters per document and 36,000 total.

Deduplicate by Chunk ID and preserve document/section labels. The sampling function must be pure and unit-testable:

Expose the pure function `select_representative_chunks(chunks, max_chunks=6, max_chars=12_000) -> list[KnowledgeChunk]`. Implement selection by ordered unique Chunk IDs, stop before adding a Chunk that would exceed `max_chars`, and always include the first non-empty Chunk when one exists.

- [ ] **Step 4: Implement the discovery prompt and parser**

Use one project LLM JSON call. The prompt must state:

```text
你是业务知识建模助手。用户不需要理解知识图谱 Schema。
根据场景目标、希望回答的问题和代表性文档，识别：
1. 对 Agent 推理有稳定意义的业务对象；
2. 用户能够理解和确认的业务逻辑；
3. 同义词和缩写；
4. 应忽略的版式或背景信息；
5. 样本文档覆盖不足或存在歧义的部分。
不要把具体实例误当成对象类型，不要生成技术化英文关系给用户展示。
```

Validate with `SceneDraft`; reject empty object or logic collections with a domain error that includes `diagnostics` rather than silently creating a permissive Schema.

- [ ] **Step 5: Run discovery tests**

Run Step 2. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/knowledge_base/scene_discovery.py backend/tests/knowledge_base/test_scene_discovery.py
git commit -m "feat: discover business scenes from representative documents"
```

---

### Task 6: Expose scene discovery/confirmation APIs and the setup UI

**Files:**
- Create: `backend/app/api/knowledge_scene_routes.py`
- Modify: `backend/app/core/routing.py`
- Test: `backend/tests/api/test_knowledge_scene_routes.py`
- Modify: `frontend/src/api/knowledgeBase.js`
- Modify: `frontend/src/stores/knowledgeBaseStore.js`
- Create: `frontend/src/components/management/knowledge-base/KnowledgeSceneSetup.vue`
- Create: `frontend/src/components/management/knowledge-base/KnowledgeSceneDraft.vue`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`

- [ ] **Step 1: Write API tests for the complete state transition**

```python
def test_scene_discovery_requires_document(scene_api):
    response = scene_api.post("/api/knowledge-base/kb1/scene/discover", json={
        "scene_goal": "分析企业噪声投诉与整改闭环",
        "desired_questions": [],
    })
    assert response.status_code == 409
    assert response.json()["detail"] == "representative_document_required"


def test_confirm_scene_compiles_schema_and_sets_ready(scene_api, completed_document):
    draft = scene_api.post("/api/knowledge-base/kb1/scene/discover", json={
        "scene_goal": "分析企业噪声投诉与整改闭环",
        "desired_questions": ["哪些噪声源导致投诉？"],
    }).json()
    response = scene_api.post(
        f"/api/knowledge-base/kb1/scene/profiles/{draft['id']}/confirm",
        json={"business_objects": draft["business_objects"], "business_logic": draft["business_logic"], "ignored_content": []},
    )
    assert response.status_code == 200
    assert response.json()["scene_status"] == "ready"
    assert response.json()["schema_version"] == 1
```

- [ ] **Step 2: Run the API test and verify missing routes**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/api/test_knowledge_scene_routes.py -q
```

Expected: 404 or missing router import.

- [ ] **Step 3: Implement and register the API**

Add routes:

```text
GET  /api/knowledge-base/{kb_id}/scene
POST /api/knowledge-base/{kb_id}/scene/discover
GET  /api/knowledge-base/{kb_id}/scene/profiles/current
POST /api/knowledge-base/{kb_id}/scene/profiles/{profile_id}/confirm
GET  /api/knowledge-base/{kb_id}/scene/suggestions
POST /api/knowledge-base/{kb_id}/scene/suggestions/{suggestion_id}/accept
POST /api/knowledge-base/{kb_id}/scene/suggestions/{suggestion_id}/reject
```

Reuse `_readable_kb` and `_manageable_kb` permission semantics. Return 409 codes `representative_document_required`, `scene_discovery_in_progress`, and `stale_scene_profile` where applicable.

- [ ] **Step 4: Gate graph builds until the scene is ready**

In `create_graph_build()` add:

```python
if kb.scene_status != "ready":
    raise HTTPException(status_code=409, detail="scene_confirmation_required")
```

Update existing route fixtures to create `scene_status="ready"`, and add a regression assertion for the 409 response.

- [ ] **Step 5: Run API and graph-build tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/api/test_knowledge_scene_routes.py \
  tests/api/test_knowledge_graph_routes.py \
  tests/knowledge_base/test_graph_build_service.py -q
```

Expected: all tests PASS.

- [ ] **Step 6: Add frontend API/store functions**

Add functions with the existing `request()` helper:

```javascript
export const getKnowledgeScene = kbId => request(`${BASE_URL}/${kbId}/scene`)
export const discoverKnowledgeScene = (kbId, payload) => request(`${BASE_URL}/${kbId}/scene/discover`, { method: 'POST', body: JSON.stringify(payload) })
export const confirmKnowledgeScene = (kbId, profileId, payload) => request(`${BASE_URL}/${kbId}/scene/profiles/${profileId}/confirm`, { method: 'POST', body: JSON.stringify(payload) })
export const listKnowledgeSceneSuggestions = kbId => request(`${BASE_URL}/${kbId}/scene/suggestions`)
```

Store state must distinguish `awaiting_documents`, `discovering`, `awaiting_confirmation`, and `ready`; do not infer readiness from entity count.

- [ ] **Step 7: Build the scene wizard**

`KnowledgeSceneSetup.vue` shows scene goal, optional desired questions, current document count, and a disabled discovery action until at least one processed document exists. `KnowledgeSceneDraft.vue` shows editable business-object cards and natural-language business-logic rows with `required/allowed/forbidden` selectors. It must not expose JSON Schema.

`KnowledgeGraphTab.vue` renders:

```vue
<KnowledgeSceneSetup v-if="scene.status === 'awaiting_documents' || !scene.profile" />
<KnowledgeSceneDraft v-else-if="scene.status === 'awaiting_confirmation'" />
<template v-else-if="scene.status === 'ready'">
  <!-- existing graph workbench -->
</template>
```

- [ ] **Step 8: Run frontend build**

```bash
cd /home/xckj/suyuan/frontend && npm run build
```

Expected: Vite build exits 0 without unresolved imports.

- [ ] **Step 9: Commit checkpoint 1**

```bash
git add backend/app/api/knowledge_scene_routes.py backend/app/core/routing.py backend/app/api/knowledge_graph_routes.py backend/tests/api/test_knowledge_scene_routes.py backend/tests/api/test_knowledge_graph_routes.py frontend/src/api/knowledgeBase.js frontend/src/stores/knowledgeBaseStore.js frontend/src/components/management/knowledge-base/KnowledgeSceneSetup.vue frontend/src/components/management/knowledge-base/KnowledgeSceneDraft.vue frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue
git commit -m "feat: add scene discovery and business confirmation workflow"
```

---

### Task 7: Parse, confirm, version, and archive natural-language business rules

**Files:**
- Create: `backend/app/knowledge_base/business_rule_service.py`
- Modify: `backend/app/api/knowledge_scene_routes.py`
- Test: `backend/tests/knowledge_base/test_business_rule_service.py`
- Test: `backend/tests/api/test_knowledge_business_rule_routes.py`
- Modify: `frontend/src/api/knowledgeBase.js`
- Create: `frontend/src/components/management/knowledge-base/KnowledgeBusinessRules.vue`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`

- [ ] **Step 1: Write rule parsing and version tests**

```python
@pytest.mark.asyncio
async def test_rule_is_draft_until_user_confirms(db_session, ready_kb):
    service = BusinessRuleService(db_session, llm=FakeRuleLLM())
    rule = await service.parse_rule(
        ready_kb.id,
        "工业企业厂界噪声结果应按功能区类别和昼夜时段使用对应限值评价。",
        created_by="u1",
    )
    assert rule.status == "draft"
    assert rule.structured_rule["kind"] == "conditional_constraint"
    await service.confirm_rule(rule.id, expected_version=1)
    await db_session.refresh(ready_kb)
    assert ready_kb.rule_version == 1


@pytest.mark.asyncio
async def test_archived_rule_is_not_in_active_extraction_context(db_session, ready_kb):
    service = BusinessRuleService(db_session, llm=FakeRuleLLM())
    rule = await create_confirmed_rule(service, ready_kb.id)
    await service.archive_rule(rule.id)
    assert await service.active_rule_context(ready_kb.id) == []
```

- [ ] **Step 2: Run and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_business_rule_service.py -q
```

Expected: missing service import.

- [ ] **Step 3: Implement structured rule parsing**

Use this validated shape:

```python
class StructuredBusinessRule(BaseModel):
    kind: Literal["relationship_constraint", "conditional_constraint", "normalization", "exclusion"]
    summary: str
    applies_to: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    required_logic: list[str] = Field(default_factory=list)
    forbidden_logic: list[str] = Field(default_factory=list)
```

The LLM prompt must use the active scene profile and explicitly say “只解释规则，不从规则臆造具体企业、站点、设备或事件事实”. `confirm_rule()` increments the knowledge base rule version under a row lock. `active_rule_context()` returns confirmed rules ordered by version.

- [ ] **Step 4: Add rule routes and API tests**

Add:

```text
GET    /api/knowledge-base/{kb_id}/scene/rules
POST   /api/knowledge-base/{kb_id}/scene/rules/parse
POST   /api/knowledge-base/{kb_id}/scene/rules/{rule_id}/confirm
DELETE /api/knowledge-base/{kb_id}/scene/rules/{rule_id}
```

Test that parse returns `draft`, confirm returns `confirmed`, and archive excludes it from the default list.

- [ ] **Step 5: Run backend rule tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_business_rule_service.py \
  tests/api/test_knowledge_business_rule_routes.py -q
```

Expected: PASS.

- [ ] **Step 6: Add the rules UI**

The component flow is: enter one natural-language rule → preview system interpretation → confirm or cancel. Display status and version. Do not provide a raw JSON editor. Archive requires a confirmation dialog and explains that archived rules stop affecting later extraction.

- [ ] **Step 7: Build frontend and commit**

```bash
cd /home/xckj/suyuan/frontend && npm run build
git add backend/app/knowledge_base/business_rule_service.py backend/app/api/knowledge_scene_routes.py backend/tests/knowledge_base/test_business_rule_service.py backend/tests/api/test_knowledge_business_rule_routes.py frontend/src/api/knowledgeBase.js frontend/src/components/management/knowledge-base/KnowledgeBusinessRules.vue frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue
git commit -m "feat: add confirmed natural-language business rules"
```

---

### Task 8: Implement reusable entity linking

**Files:**
- Create: `backend/app/knowledge_base/entity_linker.py`
- Modify: `backend/app/knowledge_base/graph_repository.py`
- Test: `backend/tests/knowledge_base/test_entity_linker.py`

- [ ] **Step 1: Write linking-decision tests**

```python
@pytest.mark.asyncio
async def test_alias_match_links_without_llm(entity_linker, entity_factory):
    entity = await entity_factory(entity_type="pollutant", name="PM2.5", aliases=["PM25", "细颗粒物"])
    decision = await entity_linker.link(kb_id="kb1", entity_type="pollutant", name="PM25")
    assert decision.action == "link"
    assert decision.entity_id == entity.id
    assert decision.reason == "confirmed_alias"


@pytest.mark.asyncio
async def test_multiple_close_candidates_require_user_resolution(entity_linker, entity_factory):
    await entity_factory(entity_type="station", name="南站", aliases=[])
    await entity_factory(entity_type="enterprise", name="南站公司", aliases=[])
    decision = await entity_linker.link(kb_id="kb1", entity_type="unknown", name="南站")
    assert decision.action == "ambiguous"
    assert len(decision.candidates) >= 2
```

- [ ] **Step 2: Run and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_entity_linker.py -q
```

Expected: missing linker import.

- [ ] **Step 3: Implement the decision pipeline**

Define:

```python
class EntityLinkDecision(BaseModel):
    action: Literal["link", "create", "ambiguous"]
    entity_id: str | None = None
    canonical_name: str
    reason: str
    confidence: float = Field(ge=0, le=1)
    candidates: list[EntityLinkCandidate] = Field(default_factory=list)
```

Order decisions:

1. exact normalized name and type;
2. confirmed aliases and scene `domain_aliases`;
3. Qdrant entity-vector candidates limited to the same compatible type;
4. LLM comparison only when the top candidates are close;
5. `ambiguous` if confidence is below 0.90 or the top-two difference is below 0.08.

Never automatically merge different entity types. Expose a repository method that links an extracted local ID to an existing canonical entity without overwriting user-locked fields.

- [ ] **Step 4: Run linker and graph-repository tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_entity_linker.py \
  tests/knowledge_base/test_graph_repository.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/knowledge_base/entity_linker.py backend/app/knowledge_base/graph_repository.py backend/tests/knowledge_base/test_entity_linker.py
git commit -m "feat: link graph entities with aliases and ambiguity handling"
```

---

### Task 9: Parse and persist user-asserted confirmed facts

**Files:**
- Create: `backend/app/knowledge_base/user_fact_service.py`
- Modify: `backend/app/api/knowledge_scene_routes.py`
- Test: `backend/tests/knowledge_base/test_user_fact_service.py`
- Test: `backend/tests/api/test_knowledge_user_fact_routes.py`
- Modify: `frontend/src/api/knowledgeBase.js`
- Create: `frontend/src/components/management/knowledge-base/KnowledgeUserFacts.vue`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`

- [ ] **Step 1: Write trusted-fact and ambiguity tests**

```python
@pytest.mark.asyncio
async def test_confirmed_user_fact_creates_confirmed_relation(db_session, ready_kb):
    service = UserFactService(db_session, parser=FakeFactParser(), linker=ExactLinker())
    preview = await service.parse_fact(ready_kb.id, "企业A的主要噪声源是1号空压机", created_by="u1")
    fact = await service.confirm_fact(preview.id, resolutions={})
    relation = await db_session.get(KnowledgeGraphRelation, fact.structured_fact["relation_id"])
    assert relation.review_status == "confirmed"
    assert relation.source_type == "user_asserted"


@pytest.mark.asyncio
async def test_ambiguous_fact_cannot_confirm_without_resolution(db_session, ready_kb):
    service = UserFactService(db_session, parser=FakeFactParser(), linker=AmbiguousLinker())
    preview = await service.parse_fact(ready_kb.id, "南站发生设备故障", created_by="u1")
    with pytest.raises(FactResolutionRequired):
        await service.confirm_fact(preview.id, resolutions={})
```

- [ ] **Step 2: Run and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_user_fact_service.py -q
```

Expected: missing service import.

- [ ] **Step 3: Implement parse-preview-confirm**

Parse against the active scene Schema into:

```python
class UserFactDraft(BaseModel):
    subject: UserFactEntity
    relation_type: str
    object: UserFactEntity
    statement: str
```

Validate the relation triplet against the confirmed Schema. Store the preview before confirmation. On confirmation, require explicit resolutions for all ambiguous entities, write/attach canonical entities, persist the relation through `KnowledgeGraphRepository`, set `review_status="confirmed"`, `source_type="user_asserted"`, and use the original user statement as evidence. Enqueue entity/relation Qdrant Outbox upserts in the same transaction.

- [ ] **Step 4: Add endpoints and route tests**

```text
GET  /api/knowledge-base/{kb_id}/scene/facts
POST /api/knowledge-base/{kb_id}/scene/facts/parse
POST /api/knowledge-base/{kb_id}/scene/facts/{fact_id}/confirm
```

Return HTTP 409 with `entity_resolution_required` and candidate records if confirmation lacks a required resolution.

- [ ] **Step 5: Run backend tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_user_fact_service.py \
  tests/api/test_knowledge_user_fact_routes.py \
  tests/knowledge_base/test_index_outbox.py -q
```

Expected: PASS.

- [ ] **Step 6: Add fact-entry UI**

The UI must show the parsed `主体—关系—客体` before confirmation. For ambiguous entities, show existing candidates plus “创建新实体”. The final button text is “确认并加入可信图谱”, and the resulting fact is labelled “用户确认事实”.

- [ ] **Step 7: Build and commit checkpoint 2**

```bash
cd /home/xckj/suyuan/frontend && npm run build
git add backend/app/knowledge_base/user_fact_service.py backend/app/api/knowledge_scene_routes.py backend/tests/knowledge_base/test_user_fact_service.py backend/tests/api/test_knowledge_user_fact_routes.py frontend/src/api/knowledgeBase.js frontend/src/components/management/knowledge-base/KnowledgeUserFacts.vue frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue
git commit -m "feat: add user-confirmed business facts"
```

---

### Task 10: Make the extraction prompt entirely scene-driven

**Files:**
- Modify: `backend/app/knowledge_base/graph_extraction/llm_factory.py`
- Test: `backend/tests/knowledge_base/test_graph_prompt_builder.py`

- [ ] **Step 1: Write prompt regression tests**

```python
def test_prompt_uses_scene_schema_without_air_quality_hardcoding():
    adapter = ProjectLLMAdapter(llm_service=FakeLLMService())
    adapter.set_cognitive_schema(noise_scene_schema())
    prompt = adapter._build_structured_kg_prompt("企业A存在空压机噪声", 10)
    assert "enterprise：被监管企业" in prompt
    assert "enterprise --has_noise_source--> noise_source" in prompt
    assert "工业企业厂界噪声" in prompt
    assert "Station, Pollutant, Metric" not in prompt


def test_prompt_contains_confirmed_rules_and_ignored_content():
    adapter = ProjectLLMAdapter(llm_service=FakeLLMService())
    adapter.set_cognitive_schema(noise_scene_schema())
    adapter.set_business_rules([{"summary": "监测结果必须关联昼夜时段"}])
    prompt = adapter._build_structured_kg_prompt("正文", 10)
    assert "监测结果必须关联昼夜时段" in prompt
    assert "不要抽取：页眉页脚" in prompt
```

- [ ] **Step 2: Run and verify the current hard-coded prompt fails the test**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_prompt_builder.py -q
```

Expected: assertion failure because air-quality types are still hard-coded.

- [ ] **Step 3: Replace hard-coded type lists with dynamic sections**

The builder must render:

```text
场景目标
实体类型（key、中文说明、别名）
关系类型（key、业务说明）
允许/必须/禁止的三元组方向
已确认业务规则
应忽略内容
输出 JSON 契约
当前文本
```

Keep the JSON shape stable for LlamaIndex structured validation. Add `PROMPT_VERSION = "scene-kg-v1"`. Do not allow caller-provided full prompts.

- [ ] **Step 4: Run prompt and provider tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_graph_prompt_builder.py \
  tests/knowledge_base/test_graph_extractor_adapter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/knowledge_base/graph_extraction/llm_factory.py backend/tests/knowledge_base/test_graph_prompt_builder.py
git commit -m "feat: drive graph extraction prompts from confirmed scenes"
```

---

### Task 11: Capture extraction runs and exact evidence

**Files:**
- Create: `backend/app/knowledge_base/extraction_run_repository.py`
- Modify: `backend/app/knowledge_base/graph_extraction/models.py`
- Modify: `backend/app/knowledge_base/graph_extraction/llm_factory.py`
- Modify: `backend/app/knowledge_base/graph_extraction/providers/llamaindex_extractor.py`
- Modify: `backend/app/knowledge_base/graph_schemas.py`
- Test: `backend/tests/knowledge_base/test_extraction_runs_and_evidence.py`

- [ ] **Step 1: Write evidence validation and provenance tests**

```python
def test_exact_evidence_must_match_chunk_text():
    evidence = ExtractedEvidence(quote="采样管路泄漏", start_char=0, end_char=7)
    assert evidence.validate_against("采样管路泄漏导致流量不足") is None
    with pytest.raises(EvidenceMismatch):
        evidence.validate_against("文本中没有该证据")


@pytest.mark.asyncio
async def test_failed_validation_still_persists_raw_extraction_run(db_session):
    repo = ExtractionRunRepository(db_session)
    run = await repo.record_completed(
        context=run_context(),
        raw_response={"triplets": [{"bad": "payload"}]},
        parsed_response={},
        validation_errors=["triplets.0.subject is required"],
        status="failed",
    )
    assert run.raw_response["triplets"]
    assert run.prompt_version == "scene-kg-v1"
```

- [ ] **Step 2: Run and verify failures**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_extraction_runs_and_evidence.py -q
```

Expected: missing evidence/run contracts.

- [ ] **Step 3: Extend the structured LLM output**

Each entity and relation must return:

```json
{
  "evidence": {
    "quote": "原文中的连续文本",
    "start_char": 10,
    "end_char": 24
  },
  "confidence": 0.93
}
```

Validate `chunk_text[start_char:end_char] == quote`. If offsets are absent but the quote occurs exactly once, derive offsets. If it occurs multiple times or not at all, mark validation failed; do not silently attach the whole Chunk as exact evidence.

- [ ] **Step 4: Implement extraction-run persistence**

Provide three public methods: `start(context) -> str`, `complete(run_id, raw_response, parsed_response, token_usage, latency_ms) -> None`, and `fail(run_id, raw_response, validation_errors, latency_ms) -> None`. `start` inserts status `running`; `complete` updates only a running row to `completed`; `fail` updates only a running row to `failed`. Both terminal methods reject a second terminal transition.

Capture the project LLM model name/parameters and adapter `last_structured_payload`. Never log raw document text in ordinary application logs; raw response belongs in the protected PostgreSQL record.

- [ ] **Step 5: Run evidence and adapter tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_extraction_runs_and_evidence.py \
  tests/knowledge_base/test_graph_extractor_adapter.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/knowledge_base/extraction_run_repository.py backend/app/knowledge_base/graph_extraction/models.py backend/app/knowledge_base/graph_extraction/llm_factory.py backend/app/knowledge_base/graph_extraction/providers/llamaindex_extractor.py backend/app/knowledge_base/graph_schemas.py backend/tests/knowledge_base/test_extraction_runs_and_evidence.py
git commit -m "feat: record graph extraction provenance and exact evidence"
```

---

### Task 12: Integrate scene context, two-stage extraction, linking, and suggestions

**Files:**
- Modify: `backend/app/knowledge_base/graph_extractor.py`
- Modify: `backend/app/knowledge_base/ingestion_service.py`
- Modify: `backend/app/knowledge_base/graph_repository.py`
- Test: `backend/tests/knowledge_base/test_scene_constrained_ingestion.py`
- Test: `backend/tests/integration/test_scene_driven_graph_flow.py`

- [ ] **Step 1: Write an end-to-end constrained-ingestion test**

```python
@pytest.mark.asyncio
async def test_scene_constrained_ingestion_persists_candidate_with_exact_evidence(scene_db):
    kb, document, chunk = await ready_noise_scene(scene_db)
    extractor = FakeTwoStageExtractor(
        entities=[entity("e1", "enterprise", "企业A", quote="企业A")],
        relations=[relation("e1", "has_noise_source", "e2", quote="企业A拥有1号空压机")],
    )
    result = await ingestion_service(scene_db, extractor=extractor).ingest_document(document.id)
    relation = await scene_db.scalar(select(KnowledgeGraphRelation))
    mention = await scene_db.scalar(select(KnowledgeGraphRelationMention))
    assert result.status == "completed"
    assert relation.review_status == "candidate"
    assert relation.source_type == "document_fact"
    assert mention.evidence_text == "企业A拥有1号空压机"
    assert relation.schema_version == kb.schema_version
```

- [ ] **Step 2: Write a suggestion test for out-of-Schema concepts**

```python
@pytest.mark.asyncio
async def test_valid_out_of_schema_concept_becomes_suggestion_not_fact(scene_db):
    extractor = FakeTwoStageExtractor(unknown_entities=[entity("e9", "regulator", "生态环境局", quote="生态环境局")])
    await ingestion_service(scene_db, extractor=extractor).ingest_document("doc1")
    suggestion = await scene_db.scalar(select(KnowledgeSchemaSuggestion))
    assert suggestion.suggestion_type == "entity_type"
    assert suggestion.status == "pending"
    assert await scene_db.scalar(select(func.count()).select_from(KnowledgeGraphEntity)) == 0
```

- [ ] **Step 3: Run and verify failures**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_scene_constrained_ingestion.py \
  tests/integration/test_scene_driven_graph_flow.py -q
```

Expected: missing source/version/evidence behavior.

- [ ] **Step 4: Implement two-stage extraction**

`KnowledgeGraphExtractor.extract_chunk()` must perform:

```python
entity_result = await provider.extract_entities(context)
relation_result = await provider.extract_relations(context, entities=entity_result.entities)
validated = validator.validate(entity_result, relation_result, schema, active_rules)
```

Relation endpoints must refer to entity `local_id`; do not resolve relation endpoints by display-name guessing. Include document title, section path, previous Chunk summary, current Chunk, and next Chunk summary. Neighbor text is for disambiguation only; evidence offsets must always reference the current Chunk.

- [ ] **Step 5: Integrate extraction-run lifecycle, evidence checks, and entity linker**

For each Chunk:

1. start extraction run;
2. extract entities;
3. extract relations;
4. validate exact evidence and Schema/rules;
5. link entities;
6. persist candidate document facts and Mentions;
7. write Outbox records;
8. complete or fail the run.

Ambiguous automatic entities remain candidate records with `needs_review`; they must not be silently merged. Out-of-Schema output becomes a suggestion with evidence and is excluded from facts.

- [ ] **Step 6: Preserve incremental-generation protections**

Keep the existing `content_generation` checks before persistence and add `schema_version` checks. A run started under an old Schema may be stored for diagnostics but cannot mutate current graph facts.

- [ ] **Step 7: Run ingestion, replacement, and build regression suites**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_scene_constrained_ingestion.py \
  tests/integration/test_scene_driven_graph_flow.py \
  tests/knowledge_base/test_ingestion_service.py \
  tests/knowledge_base/test_document_replace_delete.py \
  tests/knowledge_base/test_graph_build_service.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/knowledge_base/graph_extractor.py backend/app/knowledge_base/ingestion_service.py backend/app/knowledge_base/graph_repository.py backend/tests/knowledge_base/test_scene_constrained_ingestion.py backend/tests/integration/test_scene_driven_graph_flow.py
git commit -m "feat: build graphs with scene constraints and entity linking"
```

---

### Task 13: Add graph-aware retrieval and provenance-aware Agent results

**Files:**
- Create: `backend/app/knowledge_base/graph_retrieval.py`
- Modify: `backend/app/knowledge_base/retrieval_service.py`
- Modify: `backend/app/tools/knowledge/knowledge_graph_query/tool.py`
- Test: `backend/tests/knowledge_base/test_graph_retrieval.py`
- Test: `backend/tests/tools/knowledge/test_knowledge_graph_query_tool.py`

- [ ] **Step 1: Write RRF and trusted-source tests**

```python
def test_rrf_fuses_chunk_and_graph_rankings():
    result = reciprocal_rank_fusion(
        {"chunk": ["c1", "c2"], "graph": ["c2", "c3"]},
        weights={"chunk": 1.0, "graph": 1.0},
        k=60,
    )
    assert result[0].chunk_id == "c2"
    assert set(result[0].sources) == {"chunk", "graph"}


@pytest.mark.asyncio
async def test_agent_graph_retrieval_excludes_candidate_document_facts(graph_retrieval):
    result = await graph_retrieval.search("企业A的主要噪声源", ["kb1"])
    assert all(item.review_status in {"confirmed", "published"} for item in result.facts)
    assert {item.source_type for item in result.facts} <= {"document_fact", "user_asserted"}
```

- [ ] **Step 2: Run and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_retrieval.py -q
```

Expected: missing graph retrieval module.

- [ ] **Step 3: Implement graph retrieval without a new graph database**

Use:

1. Qdrant `record_type=entity` and `record_type=relation` searches for seeds;
2. PostgreSQL `KnowledgeGraphRepository.traverse()` at depth 1-2;
3. confirmed/published Mention records to recover supporting Chunk IDs;
4. weighted RRF to fuse ordinary Chunk results and graph-derived Chunk results;
5. existing reranker for final ordering.

Return separate typed collections:

```python
class GraphRetrievalResult(BaseModel):
    facts: list[RetrievedGraphFact]
    rules: list[RetrievedBusinessRule]
    chunks: list[RetrievedChunk]
    paths: list[RetrievedGraphPath]
```

Every fact carries `source_type`, `review_status`, evidence reference, and versions. Rules are never labelled as observed facts. Inferred paths are returned as paths, not persisted facts.

- [ ] **Step 4: Update the Agent tool output contract**

Return concise JSON sections `facts`, `business_rules`, `graph_paths`, and `evidence_chunks`. Update the tool description to explain the distinction between `document_fact`, `user_asserted`, `business_rule`, and `inferred`.

- [ ] **Step 5: Run retrieval and Agent tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base/test_graph_retrieval.py \
  tests/tools/knowledge/test_knowledge_graph_query_tool.py \
  tests/test_agent_knowledge_graph_context.py \
  tests/test_graph_mode_prompt_and_context.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/knowledge_base/graph_retrieval.py backend/app/knowledge_base/retrieval_service.py backend/app/tools/knowledge/knowledge_graph_query/tool.py backend/tests/knowledge_base/test_graph_retrieval.py backend/tests/tools/knowledge/test_knowledge_graph_query_tool.py
git commit -m "feat: fuse trusted graph facts into knowledge retrieval"
```

---

### Task 14: Complete provenance UI, quality evaluation, and release verification

**Files:**
- Modify: `backend/app/api/knowledge_graph_routes.py`
- Create: `backend/tests/knowledge_base/test_graph_quality_metrics.py`
- Create: `backend/scripts/evaluate_scene_graph.py`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphDetailPanel.vue`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphStatus.vue`
- Create: `frontend/src/components/management/knowledge-base/KnowledgeSceneSuggestions.vue`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`
- Modify: `docs/knowledge-base-graph-operations.md`

- [ ] **Step 1: Write quality-metric tests**

```python
def test_graph_quality_metrics_from_gold_records():
    metrics = calculate_graph_metrics(
        predicted_entities={("enterprise", "企业A"), ("noise_source", "空压机")},
        gold_entities={("enterprise", "企业A"), ("noise_source", "空压机"), ("complaint", "投诉1")},
        predicted_relations={("企业A", "has_noise_source", "空压机")},
        gold_relations={("企业A", "has_noise_source", "空压机")},
        evidence_valid=[True],
    )
    assert metrics.entity_precision == 1.0
    assert metrics.entity_recall == pytest.approx(2 / 3)
    assert metrics.relation_f1 == 1.0
    assert metrics.evidence_support_rate == 1.0
```

- [ ] **Step 2: Run and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base/test_graph_quality_metrics.py -q
```

Expected: missing evaluation function.

- [ ] **Step 3: Implement offline evaluation**

`evaluate_scene_graph.py` accepts:

```text
--kb-id
--gold-jsonl
--output-json
```

The JSONL contract contains `chunk_id`, gold entities, gold relations, aliases, and evidence spans. Report entity/relationship precision, recall and F1; type accuracy; entity-link accuracy; evidence support rate; duplicate-entity rate; Schema violation rate; and isolated-entity rate. Exit non-zero only for malformed data or execution failures, not for a low metric score.

- [ ] **Step 4: Add provenance and suggestion presentation**

Graph detail shows:

- source badge: 文档事实 / 用户确认事实;
- review status;
- exact quote and document location;
- scene, Schema, rule, Prompt, and model versions;
- extraction confidence and validation messages.

`KnowledgeSceneSuggestions.vue` shows the suggested object/logic in business language, its supporting documents/Chunks, and accept/reject actions. Accepting a suggestion creates a new draft profile; it must not mutate the confirmed Schema immediately.

- [ ] **Step 5: Document deployment and rollback**

Update operations documentation with exact order:

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 python -m app.alembic.versions.add_scenario_driven_knowledge_graph
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base tests/api/test_knowledge_scene_routes.py tests/api/test_knowledge_graph_routes.py -q
```

Document that existing knowledge bases enter `awaiting_confirmation`, existing graph facts retain their current review state and version 0, and rollback uses the pre-release PostgreSQL backup rather than a destructive downgrade.

- [ ] **Step 6: Run focused backend verification**

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/knowledge_base \
  tests/api/test_knowledge_scene_routes.py \
  tests/api/test_knowledge_business_rule_routes.py \
  tests/api/test_knowledge_user_fact_routes.py \
  tests/api/test_knowledge_graph_routes.py \
  tests/integration/test_scene_driven_graph_flow.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 7: Run lint and frontend production build**

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 ruff check app/knowledge_base app/api/knowledge_scene_routes.py tests/knowledge_base tests/api/test_knowledge_scene_routes.py
cd /home/xckj/suyuan/frontend
npm run build
```

Expected: Ruff exits 0 and Vite build exits 0.

- [ ] **Step 8: Run the existing unified-flow regression**

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/integration/test_unified_knowledge_graph_flow.py \
  tests/knowledge_base/test_document_replace_delete.py \
  tests/knowledge_base/test_graph_build_sqlite_integration.py -q
```

Expected: PASS; replacement/deletion still removes stale Mentions and Outbox records correctly.

- [ ] **Step 9: Commit checkpoint 3**

```bash
git add backend/app/api/knowledge_graph_routes.py backend/tests/knowledge_base/test_graph_quality_metrics.py backend/scripts/evaluate_scene_graph.py frontend/src/components/management/knowledge-base/KnowledgeGraphDetailPanel.vue frontend/src/components/management/knowledge-base/KnowledgeGraphStatus.vue frontend/src/components/management/knowledge-base/KnowledgeSceneSuggestions.vue frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue docs/knowledge-base-graph-operations.md
git commit -m "feat: complete scene graph quality and provenance workflow"
```

---

## Manual acceptance scenarios

After Task 14, test these three knowledge bases independently. Each represents one scene and must produce a different confirmed Schema:

1. **Industrial noise complaints:** upload a complaint/monitoring document; confirm enterprise, noise source, complaint, monitoring result, and rectification logic; add a functional-zone evaluation rule; add one user-confirmed enterprise/noise-source fact.
2. **Policy and technical specifications:** upload a regulation; confirm policy, clause, regulated object, pollutant/indicator, limit, applicable region, and effective-time logic; verify that section headings and publishing bodies are not indiscriminately promoted to core entities.
3. **Monitoring station equipment faults:** upload a maintenance work order; confirm station, device, alarm, symptom, metric, root cause, and action logic; verify that aliases link to existing devices and ambiguous station names request resolution.

For every scenario verify:

- discovery cannot start without a representative document;
- users never need to edit Schema JSON;
- confirmed business language produces a versioned strict Schema;
- document extraction creates candidate facts with exact evidence;
- natural-language user facts become confirmed only after preview confirmation;
- active business rules change later extraction validation;
- schema suggestions require explicit acceptance;
- Agent retrieval distinguishes facts, rules, paths, and evidence;
- modifying the scene or rules explains whether historical re-extraction is required.

## Completion criteria

The program is complete only when all three checkpoints are delivered, all commands in Task 14 pass, and the three manual scenarios have recorded acceptance results. Do not claim success based only on successful database migration, graph-build completion status, or a populated graph canvas.
