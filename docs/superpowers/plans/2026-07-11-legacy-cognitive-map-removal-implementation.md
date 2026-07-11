# Legacy Cognitive Map Permanent Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently remove the legacy standalone cognitive-map implementation and data while preserving the per-knowledge-base graph extraction, incremental build, review, query, Agent, and G6 visualization capabilities.

**Architecture:** First move the extraction contracts and providers still used by the knowledge-base graph into `app.knowledge_base.graph_extraction`, with neutral knowledge-graph names and focused contract tests. Switch all active runtime imports and prove extraction still works before deleting the legacy backend, data, migration, frontend helpers, and compatibility wording. The PostgreSQL knowledge-graph facts, Qdrant collections, knowledge-base documents, graph APIs, outbox/build services, and G6 workspace remain untouched.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy, pytest, Vue 3, AntV G6 5, Node test runner, Vite

---

## File Structure

### New extraction package

- `backend/app/knowledge_base/graph_extraction/__init__.py`: exports the extraction contracts used by the knowledge-base graph.
- `backend/app/knowledge_base/graph_extraction/models.py`: graph schema, source document/chunk, candidate entity/relation, evidence, diagnostics, and extraction result models.
- `backend/app/knowledge_base/graph_extraction/llm_factory.py`: constructs the configured LlamaIndex-compatible LLM.
- `backend/app/knowledge_base/graph_extraction/provider_factory.py`: selects parser and graph extraction providers.
- `backend/app/knowledge_base/graph_extraction/providers/base.py`: parser and extractor protocols only; the old view-retriever protocol is intentionally omitted.
- `backend/app/knowledge_base/graph_extraction/providers/{text_parser,pdf_parser,docx_parser,markitdown_parser,local_extractor,llamaindex_extractor}.py`: shared parsing and extraction implementations with imports redirected to the new package.
- `backend/tests/knowledge_base/test_graph_extraction_contracts.py`: protects the new public imports and proves the legacy query/view types are absent.

### Active runtime changes

- `backend/app/knowledge_base/graph_extractor.py`: consumes `GraphExtractionSchema` and `GraphDocumentChunk` from the new package.
- `backend/app/knowledge_base/ingestion_service.py`: consumes `GraphExtractionSchema` when constructing per-knowledge-base graph jobs.
- `backend/tests/knowledge_base/test_graph_extractor_adapter.py`: verifies chunk adaptation through the new contracts.
- `backend/tests/knowledge_base/test_ingestion_service.py`: verifies automatic graph extraction remains part of incremental ingestion.

### Frontend rename and cleanup

- `frontend/src/components/management/KnowledgeGraphChat.vue`: renamed retained graph-editing conversation component.
- `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`: imports and renders `KnowledgeGraphChat`.
- `frontend/src/components/management/knowledge-graph-chat-contract.test.mjs`: renamed retained component contract test.
- Remove `frontend/src/components/management/cognitiveMapGraphLinks.js`, `frontend/src/components/management/cognitiveMapHierarchy.js`, `frontend/src/utils/cognitiveMapRefresh.js`, and their legacy-only tests after proving they have no runtime consumers.

### Permanent removals

- Remove `backend/app/agent/cognition/` after all active imports have moved.
- Remove `backend/scripts/migrate_cognitive_maps_to_knowledge_bases.py` and `backend/tests/knowledge_base/test_cognitive_map_migration.py`.
- Remove `backend/backend_data_registry/cognitive_maps/` without backup.
- Remove stale `cognitive_map_routes` and cognition Python bytecode caches.
- Update `backend/app/agent/prompts/graph_prompt.py`, `backend/app/agent/context/context_builder.py`, and `backend/app/agent/prompts/tool_registry.py` so active graph wording names the knowledge-base graph and no longer mentions the removed JSON directory or REST compatibility path.

## Task 1: Establish the new graph-extraction contract

**Files:**
- Create: `backend/tests/knowledge_base/test_graph_extraction_contracts.py`
- Create: `backend/app/knowledge_base/graph_extraction/__init__.py`
- Create: `backend/app/knowledge_base/graph_extraction/models.py`
- Create: `backend/app/knowledge_base/graph_extraction/providers/__init__.py`
- Create: `backend/app/knowledge_base/graph_extraction/providers/base.py`

- [ ] **Step 1: Write the failing public-contract test**

```python
from app.knowledge_base.graph_extraction import (
    GraphDocumentChunk,
    GraphExtractionResult,
    GraphExtractionSchema,
    GraphSourceFile,
)
from app.knowledge_base.graph_extraction.providers.base import (
    DocumentParserProvider,
    GraphExtractorProvider,
)


def test_graph_extraction_exports_neutral_knowledge_graph_contracts():
    schema = GraphExtractionSchema(
        allowed_entity_types=["Device"],
        allowed_relation_types=["measures"],
    )
    chunk = GraphDocumentChunk(
        chunk_id="chunk-1",
        knowledge_base_id="kb-1",
        source_file_id="doc-1",
        chunk_index=0,
        text="设备监测噪声。",
        location="page:1",
    )

    assert schema.allowed_entity_types == ["Device"]
    assert chunk.knowledge_base_id == "kb-1"
    assert GraphSourceFile is not None
    assert GraphExtractionResult is not None
    assert DocumentParserProvider is not None
    assert GraphExtractorProvider is not None


def test_legacy_query_and_view_are_not_part_of_new_contract():
    import app.knowledge_base.graph_extraction as extraction

    assert not hasattr(extraction, "CognitiveMapQuery")
    assert not hasattr(extraction, "CognitiveMapView")
```

- [ ] **Step 2: Run the test and verify the package is missing**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_extraction_contracts.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.knowledge_base.graph_extraction'`.

- [ ] **Step 3: Add neutral extraction models**

Move the reusable definitions from `app.agent.cognition.models` into `graph_extraction/models.py` and make these deliberate renames throughout the copied model definitions:

```python
class GraphSourceFile(BaseModel):
    file_id: str
    knowledge_base_id: str
    filename: str
    content_type: str
    storage_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GraphDocumentChunk(BaseModel):
    chunk_id: str
    knowledge_base_id: str
    source_file_id: str
    chunk_index: int
    text: str
    location: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphExtractionSchema(BaseModel):
    allowed_entity_types: list[str]
    allowed_relation_types: list[str]
    allowed_relation_triplets: list[tuple[str, str, str]] = Field(default_factory=list)
    required_evidence: bool = False
    build_requirement: str = ""
    domain_aliases: dict[str, list[str]] = Field(default_factory=dict)
    normalization_rules: dict[str, Any] = Field(default_factory=dict)
```

Keep the existing default air-quality schema contents, but change its return annotation and constructor to `GraphExtractionSchema`. Rename `map_id` to `knowledge_base_id` in evidence, candidate entity/relation, and extraction-result models. Rename `ExtractionResult` to `GraphExtractionResult`; retain `CandidateEntity`, `CandidateRelation`, `Evidence`, `ExtractionDiagnostic`, and the lightweight payload helpers because providers use them. Do not copy `CognitiveMapQuery` or `CognitiveMapView`.

- [ ] **Step 4: Add focused provider protocols and exports**

```python
# graph_extraction/providers/base.py
from typing import Protocol

from app.knowledge_base.graph_extraction.models import (
    GraphDocumentChunk,
    GraphExtractionResult,
    GraphExtractionSchema,
    GraphSourceFile,
)


class DocumentParserProvider(Protocol):
    async def parse(self, source_file: GraphSourceFile) -> list[GraphDocumentChunk]: ...


class GraphExtractorProvider(Protocol):
    async def extract(
        self,
        chunks: list[GraphDocumentChunk],
        schema: GraphExtractionSchema,
        **kwargs,
    ) -> GraphExtractionResult: ...
```

Export the four renamed models from `graph_extraction/__init__.py`. Do not recreate `GraphRetrieverProvider`, because it only served the removed standalone view.

- [ ] **Step 5: Run the contract test**

Run the Task 1 pytest command again.

Expected: `2 passed`.

- [ ] **Step 6: Commit the contract boundary**

```bash
git add backend/app/knowledge_base/graph_extraction backend/tests/knowledge_base/test_graph_extraction_contracts.py
git commit -m "refactor: establish knowledge graph extraction contracts"
```

## Task 2: Move the shared factories and providers

**Files:**
- Create: `backend/app/knowledge_base/graph_extraction/llm_factory.py`
- Create: `backend/app/knowledge_base/graph_extraction/provider_factory.py`
- Create: `backend/app/knowledge_base/graph_extraction/providers/text_parser.py`
- Create: `backend/app/knowledge_base/graph_extraction/providers/pdf_parser.py`
- Create: `backend/app/knowledge_base/graph_extraction/providers/docx_parser.py`
- Create: `backend/app/knowledge_base/graph_extraction/providers/markitdown_parser.py`
- Create: `backend/app/knowledge_base/graph_extraction/providers/local_extractor.py`
- Create: `backend/app/knowledge_base/graph_extraction/providers/llamaindex_extractor.py`
- Modify: `backend/tests/knowledge_base/test_graph_extraction_contracts.py`

- [ ] **Step 1: Add failing provider-factory tests**

```python
from app.knowledge_base.graph_extraction.provider_factory import (
    create_extractor_provider,
    create_parser_provider,
)


def test_graph_extraction_factory_builds_local_provider():
    provider = create_extractor_provider("local")
    assert provider.provider_name == "local-rule-based"


def test_graph_extraction_factory_builds_text_parser():
    parser = create_parser_provider("text")
    assert parser.__class__.__name__ == "TextParserProvider"
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_extraction_contracts.py -q
```

Expected: import failure for `app.knowledge_base.graph_extraction.provider_factory`.

- [ ] **Step 3: Copy the active implementations and redirect internal imports**

Copy the implementation bodies from the matching files in `backend/app/agent/cognition/`. Replace every old package import with the new package and replace model names/fields consistently:

```python
from app.knowledge_base.graph_extraction.models import (
    CandidateEntity,
    CandidateRelation,
    Evidence,
    ExtractionDiagnostic,
    GraphDocumentChunk,
    GraphExtractionResult,
    GraphExtractionSchema,
    GraphSourceFile,
)
```

Within provider constructors and result assembly, use `knowledge_base_id=...`, read `chunk.knowledge_base_id`, and return `GraphExtractionResult`. Preserve existing provider names, parsing behavior, extraction prompts, stable IDs, evidence behavior, LLM configuration, and factory selection. The new `provider_factory.py` must import only from `app.knowledge_base.graph_extraction.providers`.

- [ ] **Step 4: Run contract and provider tests**

Run the Task 2 pytest command again.

Expected: `4 passed`.

- [ ] **Step 5: Compile the entire new package to catch stale imports**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 python -m compileall -q backend/app/knowledge_base/graph_extraction
```

Expected: exit status `0` and no traceback.

- [ ] **Step 6: Commit the moved providers**

```bash
git add backend/app/knowledge_base/graph_extraction backend/tests/knowledge_base/test_graph_extraction_contracts.py
git commit -m "refactor: move graph extraction providers into knowledge base"
```

## Task 3: Switch the knowledge-base graph runtime

**Files:**
- Modify: `backend/app/knowledge_base/graph_extractor.py`
- Modify: `backend/app/knowledge_base/ingestion_service.py`
- Modify: `backend/tests/knowledge_base/test_graph_extractor_adapter.py`
- Modify: `backend/tests/knowledge_base/test_ingestion_service.py`

- [ ] **Step 1: Update adapter tests to construct the new models**

Replace old cognition imports with:

```python
from app.knowledge_base.graph_extraction.models import (
    CandidateEntity,
    ExtractionDiagnostic,
    GraphExtractionResult,
    GraphExtractionSchema,
)
```

Make fake providers return `GraphExtractionResult(knowledge_base_id="kb-1", ...)`, pass `GraphExtractionSchema` into `extract_chunk`, and assert the provider receives a chunk whose `knowledge_base_id == "kb-1"`.

- [ ] **Step 2: Run the adapter and ingestion tests to verify runtime still uses old imports**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_extractor_adapter.py backend/tests/knowledge_base/test_ingestion_service.py -q
```

Expected: at least one failure caused by the adapter returning/expecting old `map_id` contracts or importing `app.agent.cognition`.

- [ ] **Step 3: Redirect the active runtime**

In `graph_extractor.py`, use:

```python
from app.knowledge_base.graph_extraction.models import (
    GraphDocumentChunk,
    GraphExtractionSchema,
)

# lazy defaults inside __init__
from app.knowledge_base.graph_extraction.llm_factory import create_llamaindex_llm
from app.knowledge_base.graph_extraction.provider_factory import create_extractor_provider
```

Construct `GraphDocumentChunk(knowledge_base_id=kb_id, ...)`, rename the local variable from `cognition_chunk` to `graph_chunk`, and annotate `schema: GraphExtractionSchema`. In `ingestion_service.py`, import and construct `GraphExtractionSchema` without changing the persisted knowledge-base graph schema/config behavior.

- [ ] **Step 4: Prove the active runtime has no cognition import**

Run:

```bash
rg -n "app\.agent\.cognition" backend/app/knowledge_base backend/tests/knowledge_base/test_graph_extractor_adapter.py backend/tests/knowledge_base/test_ingestion_service.py
```

Expected: no output and exit status `1`.

- [ ] **Step 5: Run extraction and incremental-ingestion tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_extraction_contracts.py backend/tests/knowledge_base/test_graph_extractor_adapter.py backend/tests/knowledge_base/test_ingestion_service.py backend/tests/knowledge_base/test_document_replace_delete.py -q
```

Expected: all tests pass; this is the gate that must pass before deleting `app.agent.cognition`.

- [ ] **Step 6: Commit the runtime cutover**

```bash
git add backend/app/knowledge_base/graph_extractor.py backend/app/knowledge_base/ingestion_service.py backend/tests/knowledge_base/test_graph_extractor_adapter.py backend/tests/knowledge_base/test_ingestion_service.py
git commit -m "refactor: switch knowledge graph runtime to extraction package"
```

## Task 4: Rename the retained graph chat component

**Files:**
- Rename: `frontend/src/components/management/CognitiveMapGraphChat.vue` → `frontend/src/components/management/KnowledgeGraphChat.vue`
- Rename: `frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs` → `frontend/src/components/management/knowledge-graph-chat-contract.test.mjs`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`
- Modify: `frontend/src/components/management/knowledge-graph-chat-contract.test.mjs`

- [ ] **Step 1: Change the contract test to require the new component name**

Change its source path to:

```javascript
const componentPath = new URL('./KnowledgeGraphChat.vue', import.meta.url)
```

Retain the assertions covering knowledge-base ID propagation, selected entity/relation context, `/api/agent/analyze`, and the `graph-updated` event. Add assertions that `KnowledgeGraphTab.vue` contains `KnowledgeGraphChat` and does not contain `CognitiveMapGraphChat`.

- [ ] **Step 2: Run the renamed contract test and verify failure**

Run:

```bash
cd frontend && node --test src/components/management/knowledge-graph-chat-contract.test.mjs
```

Expected: failure because `KnowledgeGraphChat.vue` does not exist.

- [ ] **Step 3: Rename the component and update the tab import/template**

The resulting tab wiring must be:

```vue
<KnowledgeGraphChat
  :knowledge-base-id="kbId"
  :entities="store.graphEntities"
  :relations="store.graphRelations"
  @graph-updated="reload"
/>

<script setup>
import KnowledgeGraphChat from '../KnowledgeGraphChat.vue'
</script>
```

Preserve all existing graph-chat behavior; this task changes identity and terminology only.

- [ ] **Step 4: Run graph-chat and tab tests**

Run:

```bash
cd frontend && node --test src/components/management/knowledge-graph-chat-contract.test.mjs src/components/management/knowledge-base/knowledge-graph-tab-contract.test.mjs src/components/management/knowledge-base/knowledge-graph-tab-visualization.test.mjs
```

Expected: all tests pass.

- [ ] **Step 5: Commit the rename**

```bash
git add frontend/src/components/management/KnowledgeGraphChat.vue frontend/src/components/management/knowledge-graph-chat-contract.test.mjs frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue
git add -u frontend/src/components/management/CognitiveMapGraphChat.vue frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs
git commit -m "refactor: rename knowledge graph chat component"
```

## Task 5: Remove unused legacy frontend helpers

**Files:**
- Delete: `frontend/src/components/management/cognitiveMapGraphLinks.js`
- Delete: `frontend/src/components/management/cognitiveMapHierarchy.js`
- Delete: `frontend/src/utils/cognitiveMapRefresh.js`
- Delete: `frontend/src/utils/__tests__/cognitiveMapRefresh.test.mjs`
- Modify: `frontend/src/components/management/knowledge-base/legacy-cognitive-map-removed.test.mjs`

- [ ] **Step 1: Extend the legacy-removal contract**

Add assertions equivalent to:

```javascript
for (const relativePath of [
  '../CognitiveMapGraphChat.vue',
  '../cognitiveMapGraphLinks.js',
  '../cognitiveMapHierarchy.js',
  '../../../utils/cognitiveMapRefresh.js',
]) {
  assert.equal(existsSync(new URL(relativePath, import.meta.url)), false)
}
```

- [ ] **Step 2: Run the removal test and verify it fails**

Run:

```bash
cd frontend && node --test src/components/management/knowledge-base/legacy-cognitive-map-removed.test.mjs
```

Expected: failure because the three helper modules still exist.

- [ ] **Step 3: Verify there are no runtime consumers**

Run:

```bash
rg -n "cognitiveMapGraphLinks|cognitiveMapHierarchy|cognitiveMapRefresh" frontend/src --glob '!**/*.test.mjs'
```

Expected: no output and exit status `1`. If a runtime import appears, migrate that consumer to the current `knowledgeGraphData.js`/store behavior before deletion and add it to this task's commit.

- [ ] **Step 4: Delete the helpers and their legacy-only test**

Delete the four listed files. Do not delete `knowledgeGraphData.js`, `knowledgeGraphSnapshot.js`, the G6 canvas, detail panel, toolbar, review panel, or their tests.

- [ ] **Step 5: Run all knowledge-graph frontend tests**

Run:

```bash
cd frontend && node --test \
  src/api/knowledgeBaseGraph.test.mjs \
  src/components/management/knowledge-graph-chat-contract.test.mjs \
  src/components/management/knowledge-base/knowledge-graph-canvas-contract.test.mjs \
  src/components/management/knowledge-base/knowledge-graph-detail-contract.test.mjs \
  src/components/management/knowledge-base/knowledge-graph-tab-contract.test.mjs \
  src/components/management/knowledge-base/knowledge-graph-tab-visualization.test.mjs \
  src/components/management/knowledge-base/knowledgeGraphData.test.mjs \
  src/components/management/knowledge-base/legacy-cognitive-map-removed.test.mjs \
  src/stores/knowledgeGraphSnapshot.test.mjs
```

Expected: all tests pass.

- [ ] **Step 6: Commit frontend cleanup**

```bash
git add frontend/src/components/management/knowledge-base/legacy-cognitive-map-removed.test.mjs
git add -u frontend/src/components/management/cognitiveMapGraphLinks.js frontend/src/components/management/cognitiveMapHierarchy.js frontend/src/utils/cognitiveMapRefresh.js frontend/src/utils/__tests__/cognitiveMapRefresh.test.mjs
git commit -m "refactor: remove legacy cognitive map frontend helpers"
```

## Task 6: Update active Agent terminology

**Files:**
- Modify: `backend/app/agent/context/context_builder.py`
- Modify: `backend/app/agent/prompts/graph_prompt.py`
- Modify: `backend/app/agent/prompts/tool_registry.py`
- Create: `backend/tests/agent/test_knowledge_graph_prompt_contract.py`

- [ ] **Step 1: Add a failing terminology contract test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "app" / "agent"


def test_active_graph_prompts_do_not_reference_legacy_cognitive_map_runtime():
    sources = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "context/context_builder.py",
            "prompts/graph_prompt.py",
            "prompts/tool_registry.py",
        )
    )
    assert "cognitive_maps" not in sources
    assert "认知地图面板" not in sources
    assert "认知地图 REST API" not in sources
    assert "认知地图图谱编辑" not in sources
```

- [ ] **Step 2: Run the contract and verify failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/agent/test_knowledge_graph_prompt_contract.py -q
```

Expected: failure listing the legacy directory/panel/API wording.

- [ ] **Step 3: Replace only runtime-specific terminology**

Use these exact replacements in `context_builder.py`:

```python
"## 知识库图谱编辑上下文\n"
"- 当前请求来自知识库图谱详情面板的对话编辑入口。\n"
"- 用户可能用“这个节点”“这条关系”“刚才那个实体”等表达指代，优先结合用户消息中的“当前知识库图谱上下文”。\n"
"- 修改图谱时使用知识库图谱工具和 API，所有操作限定在当前 knowledge_base_id。"
```

Rename the matching comment in `tool_registry.py` to `知识库图谱编辑模式工具`. Remove rule 7 about the old `cognitive_maps` JSON directory from `graph_prompt.py` and renumber later rules if necessary. Do not alter the generic domain discussion in `ops_prompt.py`, which does not address the removed runtime.

- [ ] **Step 4: Run the terminology contract**

Run the Task 6 pytest command again.

Expected: `1 passed`.

- [ ] **Step 5: Commit wording cleanup**

```bash
git add backend/app/agent/context/context_builder.py backend/app/agent/prompts/graph_prompt.py backend/app/agent/prompts/tool_registry.py backend/tests/agent/test_knowledge_graph_prompt_contract.py
git commit -m "refactor: align agent context with knowledge base graphs"
```

## Task 7: Permanently delete the legacy backend and data

**Files:**
- Delete: `backend/app/agent/cognition/`
- Delete: `backend/scripts/migrate_cognitive_maps_to_knowledge_bases.py`
- Delete: `backend/tests/knowledge_base/test_cognitive_map_migration.py`
- Delete: `backend/backend_data_registry/cognitive_maps/`
- Delete: stale cognition and `cognitive_map_routes` `__pycache__` entries
- Create: `backend/tests/knowledge_base/test_legacy_cognitive_map_removed.py`

- [ ] **Step 1: Add a failing filesystem-removal test**

```python
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_legacy_cognitive_map_implementation_and_data_are_absent():
    removed = (
        BACKEND_ROOT / "app/agent/cognition",
        BACKEND_ROOT / "scripts/migrate_cognitive_maps_to_knowledge_bases.py",
        BACKEND_ROOT / "backend_data_registry/cognitive_maps",
    )
    assert all(not path.exists() for path in removed)
```

- [ ] **Step 2: Run the removal test and verify failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_legacy_cognitive_map_removed.py -q
```

Expected: failure because the implementation and data directories still exist.

- [ ] **Step 3: Run the mandatory pre-deletion gate**

Run:

```bash
rg -n "app\.agent\.cognition" backend/app --glob '!agent/cognition/**'
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_extraction_contracts.py backend/tests/knowledge_base/test_graph_extractor_adapter.py backend/tests/knowledge_base/test_ingestion_service.py -q
```

Expected: `rg` has no output; every test passes. Stop deletion and repair the cutover if either condition fails.

- [ ] **Step 4: Permanently delete the explicitly authorized legacy assets**

Delete the entire tracked `backend/app/agent/cognition/` tree, migration script, and migration test. Permanently delete `backend/backend_data_registry/cognitive_maps/` including `agent_bindings.json`, every `cm_*` directory, source files, maps, schemas, extractions, property graph stores, evaluations, and build runs. No archive or backup is created.

Remove stale bytecode using narrowly scoped paths:

```bash
find backend/app/agent -type d -name __pycache__ -path '*cognition*' -prune -exec rm -rf {} +
find backend/app/api -type f -path '*/__pycache__/cognitive_map_routes*.pyc' -delete
```

- [ ] **Step 5: Run the removal test and import-negative check**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_legacy_cognitive_map_removed.py -q
conda run -p /root/miniconda3/envs/backend_py311 python -c "import importlib.util; assert importlib.util.find_spec('app.agent.cognition') is None"
```

Expected: test passes and the Python command exits `0`.

- [ ] **Step 6: Commit code and tracked-data deletion**

```bash
git add backend/tests/knowledge_base/test_legacy_cognitive_map_removed.py
git add -u backend/app/agent/cognition backend/scripts/migrate_cognitive_maps_to_knowledge_bases.py backend/tests/knowledge_base/test_cognitive_map_migration.py backend/backend_data_registry/cognitive_maps
git commit -m "refactor: permanently remove legacy cognitive maps"
```

## Task 8: Verify the retained graph system and repository hygiene

**Files:**
- Modify only if a failing verification exposes a missed legacy reference; keep fixes within the deletion design boundary.

- [ ] **Step 1: Scan runtime and tests for forbidden legacy identifiers**

Run:

```bash
rg -n "app\.agent\.cognition|backend_data_registry/cognitive_maps|CognitiveMapPanel|CognitiveMapGraphChat|cognitiveMapGraphLinks|cognitiveMapHierarchy|cognitiveMapRefresh|cognitive_map_routes" backend/app backend/scripts backend/tests frontend/src
```

Expected: no output. Generic business prose containing “认知地图” is allowed only outside the removed runtime references specified by the design.

- [ ] **Step 2: Verify protected graph assets still exist**

Run:

```bash
test -f backend/app/knowledge_base/graph_repository.py
test -f backend/app/knowledge_base/graph_build_service.py
test -f backend/app/knowledge_base/index_outbox.py
test -f frontend/src/components/management/knowledge-base/KnowledgeGraphCanvas.vue
test -f frontend/src/components/management/knowledge-base/KnowledgeGraphDetailPanel.vue
test -f frontend/src/components/management/KnowledgeGraphChat.vue
```

Expected: all commands exit `0`.

- [ ] **Step 3: Run the complete retained backend graph suite**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/knowledge_base/test_graph_extraction_contracts.py \
  backend/tests/knowledge_base/test_graph_extractor_adapter.py \
  backend/tests/knowledge_base/test_ingestion_service.py \
  backend/tests/knowledge_base/test_document_replace_delete.py \
  backend/tests/knowledge_base/test_graph_build_models.py \
  backend/tests/knowledge_base/test_graph_build_service.py \
  backend/tests/knowledge_base/test_graph_build_sqlite_integration.py \
  backend/tests/knowledge_base/test_graph_repository.py \
  backend/tests/knowledge_base/test_graph_retrieval.py \
  backend/tests/knowledge_base/test_graph_retrieval_limits.py \
  backend/tests/knowledge_base/test_graph_revision.py \
  backend/tests/knowledge_base/test_graph_snapshot.py \
  backend/tests/knowledge_base/test_index_outbox.py \
  backend/tests/knowledge_base/test_knowledge_qa_graph_compat.py \
  backend/tests/knowledge_base/test_unified_graph_models.py \
  backend/tests/knowledge_base/test_legacy_cognitive_map_removed.py \
  backend/tests/agent/test_knowledge_graph_prompt_contract.py -q
```

Expected: all selected tests pass with no import, schema, or extraction errors.

- [ ] **Step 4: Run frontend graph tests and production build**

Run:

```bash
cd frontend && node --test \
  src/api/knowledgeBaseGraph.test.mjs \
  src/components/management/knowledge-graph-chat-contract.test.mjs \
  src/components/management/knowledge-base/knowledge-graph-canvas-contract.test.mjs \
  src/components/management/knowledge-base/knowledge-graph-detail-contract.test.mjs \
  src/components/management/knowledge-base/knowledge-graph-tab-contract.test.mjs \
  src/components/management/knowledge-base/knowledge-graph-tab-visualization.test.mjs \
  src/components/management/knowledge-base/knowledgeGraphData.test.mjs \
  src/components/management/knowledge-base/legacy-cognitive-map-removed.test.mjs \
  src/stores/knowledgeGraphSnapshot.test.mjs
npm run build
```

Expected: all Node tests pass; Vite finishes with `built in ...` and exit status `0`.

- [ ] **Step 5: Inspect the final diff for deletion boundaries**

Run:

```bash
git status --short
git diff --stat HEAD~7..HEAD
git diff --name-status HEAD~7..HEAD
```

Expected: changes are limited to the new extraction package, runtime import cutover, graph-chat rename, legacy prompt wording, explicit legacy deletions, tests, and this plan. No PostgreSQL graph models/migrations, Qdrant code/data, knowledge-base documents, G6 components, or unrelated dirty user files are deleted.

- [ ] **Step 6: Commit any verification-only corrections**

If verification required a scoped correction, stage only those exact files and commit:

```bash
git commit -m "test: verify legacy cognitive map removal"
```

If no corrections were needed, do not create an empty commit.
