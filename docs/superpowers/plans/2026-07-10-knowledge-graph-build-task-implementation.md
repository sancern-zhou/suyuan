# 知识库级图谱构建任务实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为单个知识库增加可排队、可观测、可重试的图谱构建任务，扫描已有 Chunk 并复用现有 Graph Repository 和 Outbox 完成图谱补建。

**Architecture:** 新增持久化的 `KnowledgeGraphBuildTask` 与任务服务；API 只负责权限校验、创建/查询/取消任务，后台 worker 扫描 pending Chunk 并逐 Chunk 调用现有 `KnowledgeGraphExtractor`。构建写入仍走 `KnowledgeGraphRepository` 和事务 Outbox，文档摄取的增量路径保持不变；前端图谱工作台轮询任务状态并提供构建、重试、reset、取消操作。

**Tech Stack:** FastAPI、SQLAlchemy async、PostgreSQL、现有应用后台任务生命周期、Qdrant Outbox、Vue 3/Pinia、Node test runner。

---

### Task 1: 建立构建任务事实模型和迁移

**Files:**
- Create: `backend/app/knowledge_base/graph_build_models.py`
- Modify: `backend/app/db/database.py`（确保模型导入）
- Modify: `backend/app/alembic/versions/create_unified_knowledge_graph.py`
- Test: `backend/tests/knowledge_base/test_graph_build_models.py`

- [ ] **Step 1: Write the failing model test**

  测试 `KnowledgeGraphBuildTask` 的字段、状态默认值、`kb_id` 外键和同一知识库 active 任务唯一约束；测试 SQLite metadata 能创建表。

- [ ] **Step 2: Run the focused test and verify it fails**

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_build_models.py -q`

  Expected: FAIL because the task model and table do not exist.

- [ ] **Step 3: Implement the model and migration**

  定义 `id`、`kb_id`、`status`、`mode`、`created_by`、`total_chunks`、`processed_chunks`、`failed_chunks`、`remaining_chunks`、`failed_chunk_ids`、`last_error`、`cancel_requested`、`lease_until`、时间戳字段；PostgreSQL migration 使用 `CREATE TABLE IF NOT EXISTS`、索引和 partial unique index，约束 `queued/running` 每 KB 至多一条。

- [ ] **Step 4: Run the test and migration syntax checks**

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_build_models.py -q` and `conda run -p /root/miniconda3/envs/backend_py311 python -m py_compile backend/app/knowledge_base/graph_build_models.py backend/app/alembic/versions/create_unified_knowledge_graph.py`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add backend/app/knowledge_base/graph_build_models.py backend/app/db/database.py backend/app/alembic/versions/create_unified_knowledge_graph.py backend/tests/knowledge_base/test_graph_build_models.py
  git commit -m "feat: 增加图谱构建任务模型"
  ```

### Task 2: 实现构建服务、锁和后台执行器

**Files:**
- Create: `backend/app/knowledge_base/graph_build_service.py`
- Modify: `backend/app/knowledge_base/tasks.py` 或现有生命周期任务注册模块
- Test: `backend/tests/knowledge_base/test_graph_build_service.py`

- [ ] **Step 1: Write failing service tests**

  使用 fake extractor、fake graph repository 和 SQLite session，覆盖：pending 只选 `graph_status != completed`；同 KB active 任务返回冲突；单 Chunk 失败不阻塞其他 Chunk；成功/失败/剩余计数正确；retry 只重置失败 Chunk；cancel 在 Chunk 边界停止；reset 保留 Document/Chunk 但清理 Graph Mention、实体、关系和 Outbox。

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_build_service.py -q`

  Expected: FAIL because no build service exists.

- [ ] **Step 3: Implement the service**

  提供 `create_task(kb_id, mode, batch_size, user_id)`、`get_status(kb_id/task_id)`、`run(task_id)`、`retry(task_id/kb_id)`、`cancel(task_id)` 和 `reset_graph(kb_id)`。`run` 用 `select(...).with_for_update()` 获取任务租约，按批次查询 Chunk；抽取阶段受 `max_graph_concurrency` 限制，事实写入阶段复用 `_persist_graph_extraction` 的 generation 校验、Graph Repository 和 Outbox。每个 Chunk 独立提交，任务状态通过短事务更新。

- [ ] **Step 4: 接入后台 worker 生命周期并验证恢复**

  将 queued 任务提交到现有后台机制；增加 lease 超时恢复和启动扫描。测试 worker 崩溃后任务可恢复为 queued，重复启动不会创建第二个 active 任务。

- [ ] **Step 5: Run service tests and commit**

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base/test_graph_build_service.py backend/tests/knowledge_base/test_index_outbox.py -q`

  Expected: PASS.

  ```bash
  git add backend/app/knowledge_base/graph_build_service.py backend/app/knowledge_base/tasks.py backend/tests/knowledge_base/test_graph_build_service.py
  git commit -m "feat: 增加知识库图谱构建执行器"
  ```

### Task 3: 增加图谱构建 API 和权限隔离

**Files:**
- Modify: `backend/app/api/knowledge_graph_routes.py`
- Modify: `backend/app/core/routing.py`（仅在需要新增 router 时）
- Modify: `backend/app/knowledge_base/graph_schemas.py`
- Test: `backend/tests/api/test_knowledge_graph_build_routes.py`

- [ ] **Step 1: Write failing API tests**

  覆盖 `POST /api/knowledge-base/{kb_id}/graph/build` 返回 202、重复 active 返回 409、GET 返回计数和错误、retry/cancel/reset 调用服务、viewer 只能 GET、非 owner/admin 的写请求返回 403、跨 KB 的 task_id 不可访问。

- [ ] **Step 2: Run the API tests and verify they fail**

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/api/test_knowledge_graph_build_routes.py -q`

  Expected: FAIL because build schemas and routes do not exist.

- [ ] **Step 3: Implement schemas and routes**

  增加 `GraphBuildRequest`、`GraphBuildResponse`、`GraphBuildStatusResponse`；实现 `/build`、`/build/status`、`/build/retry`、`/build/cancel`、`/build/reset`，写操作统一调用 `_manageable_kb`，读状态调用 `_readable_kb`，路由不直接执行抽取。

- [ ] **Step 4: Run API and existing graph route tests**

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/api/test_knowledge_graph_build_routes.py backend/tests/api/test_knowledge_graph_routes.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add backend/app/api/knowledge_graph_routes.py backend/app/knowledge_base/graph_schemas.py backend/tests/api/test_knowledge_graph_build_routes.py
  git commit -m "feat: 增加图谱构建任务接口"
  ```

### Task 4: 接入前端图谱工作台

**Files:**
- Modify: `frontend/src/api/knowledgeBase.js`
- Modify: `frontend/src/stores/knowledgeBaseStore.js`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphStatus.vue`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`
- Test: `frontend/src/api/knowledgeGraphBuild.test.mjs`
- Test: `frontend/src/components/management/knowledge-base/knowledge-graph-build-tab-contract.test.mjs`

- [ ] **Step 1: Write failing frontend contract tests**

  断言 API 客户端暴露 `startGraphBuild`、`getGraphBuildStatus`、`retryGraphBuild`、`cancelGraphBuild`、`resetGraphBuild`；图谱 Tab 包含 pending/failed/processed 计数、构建/重试/reset/cancel 操作和轮询状态。

- [ ] **Step 2: Run tests and verify they fail**

  Run: `node --test frontend/src/api/knowledgeGraphBuild.test.mjs frontend/src/components/management/knowledge-base/knowledge-graph-build-tab-contract.test.mjs`

  Expected: FAIL because build API methods and controls do not exist.

- [ ] **Step 3: Implement API, Store and controls**

  API 复用现有 `request` 和 KB URL；Store 增加 `graphBuildStatus`、`loadGraphBuildStatus`、`startGraphBuild`、`retryGraphBuild`、`cancelGraphBuild`、`resetGraphBuild`；组件在 queued/running 时按退避间隔轮询，unmounted 时清理 timer，错误写入现有 error state。

- [ ] **Step 4: Run frontend tests and production build**

  Run: `node --test frontend/src/api/*.test.mjs frontend/src/components/management/knowledge-base/*.test.mjs && npm run build` from `frontend`.

  Expected: 新增构建测试和现有图谱测试通过；构建成功。已存在的 Session API limit 基线断言失败单独记录，不修改本任务范围。

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/src/api/knowledgeBase.js frontend/src/stores/knowledgeBaseStore.js frontend/src/components/management/knowledge-base/KnowledgeGraphStatus.vue frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue frontend/src/api/knowledgeGraphBuild.test.mjs frontend/src/components/management/knowledge-base/knowledge-graph-build-tab-contract.test.mjs
  git commit -m "feat: 增加图谱构建工作台操作"
  ```

### Task 5: 修正 Agent graph 模式的构建语义和发布门禁

**Files:**
- Modify: `backend/app/tools/knowledge/knowledge_graph_query/tool.py`
- Create: `backend/app/tools/knowledge/knowledge_graph_build/tool.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent/runtime/tool_coordinator.py`
- Modify: `backend/app/agent/prompts/graph_prompt.py`
- Test: `backend/tests/tools/knowledge/test_knowledge_graph_build_tool.py`
- Test: `backend/tests/test_graph_mode_prompt_and_context.py`

- [ ] **Step 1: Write failing Agent tests**

  断言 `knowledge_graph_build` 要求单个 `knowledge_base_id`，缺少 ID 时返回选择知识库错误；有效调用提交任务并返回 task_id；runtime 注入的选定 KB 覆盖模型输入；graph prompt 将“构建”导向 build 工具，将“查询”导向 query 工具。

- [ ] **Step 2: Run tests and verify they fail**

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/tools/knowledge/test_knowledge_graph_build_tool.py backend/tests/test_graph_mode_prompt_and_context.py -q`

  Expected: FAIL because the build tool and prompt routing do not exist.

- [ ] **Step 3: Implement the controlled build tool**

  工具只负责调用任务服务/API 内部入口，不直接执行 LLM 抽取；限制单 KB、校验 `mode` 和 `batch_size`，返回 queued 状态、任务 ID 和进度查询提示。`ToolCoordinator` 对 graph build/query 都注入当前选定 KB；没有选择时 build 工具明确失败，不自动选择全部知识库。

- [ ] **Step 4: Run Agent tests and full graph matrix**

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/tools/knowledge/test_knowledge_graph_build_tool.py backend/tests/test_graph_mode_prompt_and_context.py backend/tests/knowledge_base backend/tests/api/test_knowledge_graph_routes.py -q`

  Expected: PASS except documented unrelated baseline failures outside this matrix.

- [ ] **Step 5: Commit and final verification**

  ```bash
  git add backend/app/tools/knowledge/knowledge_graph_build backend/app/tools/__init__.py backend/app/agent/runtime/tool_coordinator.py backend/app/agent/prompts/graph_prompt.py backend/tests/tools/knowledge/test_knowledge_graph_build_tool.py backend/tests/test_graph_mode_prompt_and_context.py
  git commit -m "feat: 让 Agent 支持受控图谱构建"
  ```

  Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/knowledge_base backend/tests/api/test_knowledge_graph_build_routes.py backend/tests/tools/knowledge/test_knowledge_graph_build_tool.py -q`; from `frontend`, run `node --test src/api/knowledgeGraphBuild.test.mjs src/components/management/knowledge-base/knowledge-graph-build-tab-contract.test.mjs && npm run build`.

