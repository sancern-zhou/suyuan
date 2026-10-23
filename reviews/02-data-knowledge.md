# 数据层与知识库图谱评审

评审人：data-kb-reviewer（只读静态评审，未运行任何代码/测试；所有结论基于代码阅读，不确定处标注「待验证」）

## 一、总体评价

统一知识库图谱的整体设计质量较高：PG 事实源 + 事务性 Outbox + 可重建 Qdrant 投影的架构在代码中得到了忠实落地，`content_generation` 乐观并发、chunk_key 稳定复用、图谱任务租约、advisory lock 串行化等细节都有测试契约支撑。但存在两个必须立即处理的 P0：一是图谱管理 API（实体/关系增删改、合并、reindex、schema 更新）在真实依赖 `get_knowledge_db` 下从不提交事务，所有写操作在请求结束时被静默回滚，而测试通过自带 commit 的 dependency override 掩盖了该缺陷；二是知识库权限模型实际失效（can_search 恒真、can_upload 不校验私有库归属），任意登录用户可向他人私有库写入并检索其内容。此外「失败不恢复旧版本」铁律被 `replace_document` 的恢复逻辑（含测试固化）直接违反，恢复路径在「部分持久化后失败」场景会造成 PG/Outbox/Qdrant 三方失步。

## 二、数据架构现状图（文字描述）

```
上传/API/Agent 工具
        │
        ▼
KnowledgeBaseService (service.py)
  ├─ upload_document ──► queue_document（把任务写进 documents.extra_metadata，与文档同一事务提交）
  └─ KnowledgeIngestionService (ingestion_service.py)  ← 唯一的新增/替换/删除入口
        ├─ _load_and_mark_processing / _begin_replacement / _begin_delete   （行锁 + content_generation 乐观校验）
        ├─ KnowledgeChunkRepository.replace_document_chunks                 （chunk_key=content_hash:occurrence 复用/新增/删除）
        ├─ KnowledgeGraphRepository（upsert_chunk_extraction / remove_chunk_contributions，
        │     pg_advisory_xact_lock("knowledge-graph:{kb}") 串行化事实变更）
        ├─ ExtractionRunRepository（prompt/model 溯源）
        └─ KnowledgeIndexOutboxRepository（与事实同事务入队 upsert/delete；幂等键
              (record_type,record_id,operation,payload_version) 唯一约束）
                    │
                    ▼
        KnowledgeIndexOutboxWorker（仅 worker 角色启动；claim_batch skip_locked+租约；
              is_latest 跳过被取代事件）──► Qdrant（shared/local 双 scope 路由，
              typed_point_id=uuid5(record_type:record_id)）
                    ▲
        /graph/reindex、/graph/merge、实体/关系 CRUD（API 层补挂 outbox 事件）

检索：KnowledgeRetrievalService = Qdrant chunk 向量（hybrid） + Qdrant entity/relation 向量
      （仅 TRUSTED_REVIEW_STATUSES={"confirmed","published"}）→ PG 复核命中（vector_status=indexed）
      → Mention 反查 chunk → RRF 融合。

文档处理队列：DocumentProcessingQueue（tasks.py，行锁 claim + JSON lease + 心跳续租，
      仅 worker/all 角色启动；web/worker 通过 DB 行锁安全并发）。
图谱构建：KnowledgeGraphBuildTask（DB 租约 + started_at owner_token + 心跳），
      web 与 worker 都会启动恢复循环并可在本进程执行构建。
```

关键类：`KnowledgeIngestionService`、`KnowledgeChunkRepository`、`KnowledgeGraphRepository`、`KnowledgeIndexOutbox(Repository/Worker)`、`GraphBuildService`、`KnowledgeRetrievalService`、`KnowledgeBasePermissions`、`DocumentProcessingQueue`。

## 三、发现清单

### P0（数据损坏 / 一致性与安全）

- [P0] **图谱管理 API 全部写操作不提交事务，静默回滚** — backend/app/db/knowledge_database.py:41-47、backend/app/api/knowledge_graph_routes.py:550-554、567-594、597-612、675-705、708-731、734-749、792-821、849-876 — `get_knowledge_db` 只在异常时 rollback，从不 commit（对比主库依赖 `get_db` 在 database.py:263 有 `await session.commit()`）；knowledge_graph_routes.py 全文件 0 处 commit（grep 证实），实体/关系 create/patch/delete、merge、reindex 的 outbox 入队、`update_graph_schema` 全部依赖请求 session，请求结束即回滚 → 图谱管理页所有编辑、审核状态流转（payload 同步事件）、向量重建入队实际都不落库，且接口响应读的是同 session 未提交数据，前端看起来“成功”→ 修改建议：给 `get_knowledge_db` 补与 `get_db` 一致的“yield 后 commit”语义，或各写端点显式 `await db.commit()`；同时修正 tests/api/test_knowledge_graph_routes.py:97-104 中自带 commit 的 override（正是它掩盖了该缺陷）。
- [P0] **知识库权限模型实际失效：任意用户可写/可读他人私有库** — backend/app/knowledge_base/permissions.py:122-135（can_search 恒真）、:156-182（filter_accessible_ids 只做 scope 过滤，不过滤私有归属）、:138-154（can_upload 对本地库无条件 True）→ backend/app/api/knowledge_base_routes.py:269-385 → backend/app/knowledge_base/service.py:368 — 登录用户 A 可向用户 B 的私有知识库上传文档（私有库写入无 owner 校验）；`/search` 与 knowledge_qa 检索链路（service.py:660-671）会把 B 的私有库内容返回给 A；`can_manage_documents` 对公共本地库放行所有认证用户（permissions.py:117-119），任意用户可删除/替换公共库任意文档 → 修改建议：can_upload/can_manage_documents 对 private 增加 owner/admin 判断；filter_accessible_ids 至少过滤 `kb_type=private and owner_id != user_id`；若“全员可读”确属临时策略，应在 CLAUDE.md/代码注释中声明风险与到期计划。
- [P0] **「失败不恢复旧版本」铁律被 replace_document 违反，且部分持久化后恢复会造成三方失步** — backend/app/knowledge_base/ingestion_service.py:154-174（异常即 `_restore_replacement`）、:184-207（把 content_generation 从 +1 回拨、恢复旧 file_path/filename）— 与 CLAUDE.md「原位替换……失败不恢复旧版本」直接冲突；测试 backend/tests/knowledge_base/test_document_replace_delete.py:160-180 还把该行为固化为契约。更严重的是：若失败发生在 `_persist_chunks_and_outbox` 提交之后（如 `_finalize_document` 抛 StaleContentGeneration/DB 抖动），新 chunk 已落库（content_generation=旧+1）、旧 chunk 已删除、outbox upsert/delete（payload_version=旧+1）已入队，此时回拨 content_generation → PG 文档行与新 chunk 世代错位；后续再次替换会以相同 payload_version 重新入队，被幂等键（index_outbox.py:122-137 `_find_identity` 不区分状态）吞掉 → Qdrant 永久缺少新内容向量 → 修改建议：按铁律移除恢复逻辑，失败置 FAILED 并保留新世代（前端展示失败原因+重试）；或至少在恢复时同步清理/重放 outbox 并禁止版本回拨。

### P1（可靠性 / 性能）

- [P1] **图谱种子与 review 状态变更绕过 Outbox，PG/Qdrant 失步** — backend/app/tools/xuchang/station_catalog/graph_seed.py:380-396（`set_review_status` 置 confirmed 后不入队任何 outbox 事件）、backend/app/knowledge_base/graph_repository.py:262-282（`set_review_status` 本身无索引事件）— `sync_station_knowledge_graph` 先 `reset_graph`（清空实体/关系向量）再写入 confirmed 事实，但从不 enqueue upsert → 该 KB 的 entity/relation 向量索引为空，图检索只剩 chunk 命中回退路径（retrieval_service.py:186-193）。API 层有补偿（knowledge_graph_routes.py:238-267），但任何非 API 调用点（种子、未来脚本）都会失步 → 修改建议：把“状态变更/事实写入 → 索引事件”下沉到 repository 层（或提供 `index_after_review()` 统一入口）。
- [P1] **delete_knowledge_base 先删 Qdrant 后删 PG，且失败被吞 → 永久孤儿集合；chunk 向量无重建入口** — backend/app/knowledge_base/service.py:319-324（不检查 delete_collection 返回值）+ backend/app/knowledge_base/vector_store.py:439-445（异常仅记日志返回 False）— Qdrant 删除失败时 KB 行仍被删除，集合永久泄漏；反向（集合已删、PG 删除失败）时 KB 无集合，而 chunk 向量没有任何全量重建路径：`/graph/reindex` 只覆盖 entity/relation（knowledge_graph_routes.py:849-876），chunk 侧 `vector_status` 停留 "indexed"，重摄入不会为复用 chunk 重新入队（ingestion_service.py:330-333）→ 违反「Qdrant 只保存可重建的派生索引」→ 修改建议：先删 PG（事务内）再异步删集合 + 失败重试/对账任务；提供 chunk 向量全量重建（按 PG chunks 重新入队 outbox upsert）。
- [P1] **图谱构建任务失败无终态，确定性错误会无限重试** — backend/app/knowledge_base/graph_build_service.py:163-266（`run()` 无 try/except，异常既不 `_mark_task_failed` 也不 finish）、:122-130（`_mark_task_failed` 已定义但 run 未调用）— `run()` 抛异常时任务停留 running，web 与 worker 的恢复循环（knowledge_graph_routes.py:91-107，30s 周期）不断把它重新入队并再次启动 → schema/DB 类确定性错误形成 30s+租约周期的无限循环 → 修改建议：run 外层捕获异常调 `_mark_task_failed`；为构建任务增加 attempts 上限。
- [P1] **Outbox 无死信与保留策略；租约过期双消费者重复执行** — backend/app/knowledge_base/index_outbox.py:178-210（claim 仅靠 300s 租约，处理超过租约即被二次 claim）、:224-248（mark_completed/mark_retry 无状态 CAS，晚到的 retry 可把 completed 翻回 pending）、无 attempts 上限/死信态、completed 行永不清理（表无限膨胀，且 `is_latest`/`next_payload_version` 依赖全表 max）→ 数据本身靠幂等兜底无害，但毒消息反复占用、表膨胀拖慢每 KB 事实写入（next_payload_version 全表 max 查询）→ 修改建议：attempts 上限 + failed(dead) 状态；completed 行按策略归档（保留每记录 max(payload_version) 语义）；mark_* 增加状态前置条件。
- [P1] **web 进程内联执行图谱构建与重试，可能阻塞请求进程** — backend/app/api/knowledge_graph_routes.py:82-88（create/retry/recover 直接 `asyncio.create_task` 在 web 进程跑 LLM 抽取）、:824-846（`retry-failed` 在请求内同步逐文档全量重摄入）— 与 worker 双端竞争靠租约保护没错，但 web 承担重 LLM/解析负载，uvicorn 多 worker 时被重复放大；retry-failed 大 KB 会拖垮请求 → 修改建议：构建一律入队由 worker 消费（或至少 retry-failed 走队列）。

### P2（建议）

- [P2] **query_entities/traverse 全表加载后内存过滤** — backend/app/knowledge_base/graph_repository.py:362-391（加载 KB 全部实体再 Python 过滤 name/alias）、:393-463（BFS 前加载全部实体+关系）— 大图谱下每次查询/检索内存与延迟线性放大 → 改 SQL 侧 name/alias 检索 + 分层邻接查询。
- [P2] **大事务 + N+1：删除文档与 reset_graph** — backend/app/knowledge_base/ingestion_service.py:678-739（大文档单事务内逐 chunk delete+outbox enqueue，每次 enqueue 还有一次 identity SELECT）、backend/app/knowledge_base/graph_build_service.py:376-411（每记录 2-3 次 max(version) 查询，KB 图谱锁内）→ 建议批量 identity 查询/批量 insert，必要时分批提交。
- [P2] **孤儿文件/大对象无回收** — backend/app/knowledge_base/file_storage.py:135-146（lo_unlink 失败仅日志）、backend/app/knowledge_base/service.py:189-215（先建 Qdrant 集合后提交 PG，提交失败泄漏集合）、backend/app/api/knowledge_base_routes.py:329-337（进程崩溃残留 staging 文件）→ 增加对账/清理任务。
- [P2] **init_session_db 无 schema 锁、迁移脚本非原子** — backend/app/db/init_session_db.py:46-53（create_all 无 advisory lock，与 init_db 的 database.py:61-65 不一致；仅手动入口，风险低）、backend/app/db/migrate_sessions_to_db.py:69-115（get→create 非原子；create 成功但历史写入失败后重跑会被 skip，消息静默丢失）、:88-97（裸 except 吞日期解析错误）→ 补锁 + 按 (session_id,message) 幂等 upsert。
- [P2] **sync_bridge 每次调用新建 engine（NullPool）** — backend/app/db/sync_bridge.py:31-37 — 高频定时任务写路径每条 SQL 付建连成本 → 按 thread 复用 engine。
- [P2] **get_stats / search N+1** — backend/app/knowledge_base/service.py:990-996（每 KB 加载全部文档数状态）、:667-671（逐 KB 查询）→ 聚合 SQL。
- [P2] **复用 chunk 的 Qdrant payload.chunk_index 可过期** — backend/app/knowledge_base/chunk_repository.py:152-158（`_has_same_index_text` 不比较 chunk_index）+ ingestion_service.py:330-333（indexed 复用块不再入队）→ 插入/删除导致整体位移时，向量里的 chunk_index 与 PG 不一致（影响依赖 payload 的展示/排序，待验证消费方）。
- [P2] **update_graph_schema 直接覆盖且不递增 schema_version** — backend/app/api/knowledge_graph_routes.py:417-432 — 绕过 scene 编译路径的版本递增（scene_repository 负责），导致存量事实的 schema_version 溯源失真（待验证：scene 流程是否为唯一合法入口，若是应禁止该 PUT 直接改结构）。
- [P2] **导入工具直写 Qdrant+PG，绕过 IngestionService/Outbox** — backend/app/knowledge_base/import_knowledge_base.py:432-495 — CLI 运维工具（含 `--legacy-format`），新库导入尚可，但破坏「文档进入必须过 KnowledgeIngestionService」的字面约束 → 文档化为 ops-only 例外，或改为写 PG 后经 outbox 建索引。
- [P2] **模型默认值不一致与弱哈希** — backend/app/knowledge_base/models.py:97-98（chunk_size=256/overlap=64）vs backend/app/knowledge_base/service.py:339-341（1200/100）；service.py:1135-1141（file_hash 用 MD5）→ 统一默认值；file_hash 若仅用于展示/去重可保留但注明非安全用途。
- [P2] **连接池总量可能超过 PG max_connections** — backend/app/db/database.py:35-36、knowledge_database.py:21-22、session_database.py:29-30、weather_database.py:23-24 — 单进程 20+30/10+20，xuchang 3 web worker + worker 共 4-5 进程，理论上限数百连接 > 默认 100（待验证部署 env 是否调低池或调高 max_connections）。

## 四、规范符合性核查表（CLAUDE.md 铁律）

| # | 铁律 | 结论 | 证据 |
|---|------|------|------|
| 1 | 每个知识库拥有自己的图谱，图谱是 KB 的结构化索引 | 符合 | knowledge_base/models.py:110（每 KB 唯一 qdrant_collection）；graph_repository 全部按 kb_id 过滤；graph_models.py:82-176 |
| 2 | PG 保存 Chunk/实体/关系/Mention/审核状态/Outbox，是唯一事实源 | 符合（实现层面） | graph_models.py 全部事实表在 PG；检索前 PG 复核（retrieval_service.py:123-153） |
| 3 | Qdrant 只保存可重建的派生索引 | 部分违反 | entity/relation 有 `/graph/reindex` 重建（knowledge_graph_routes.py:849-876）；**chunk 向量无重建入口**（见 P1#6）；reset_graph 对无 outbox 历史的存量点不产生删除事件（graph_build_service.py:376-407） |
| 4 | 文档新增/替换/删除必须经 KnowledgeIngestionService，不得直写 Qdrant/独立图谱 JSON | 基本符合 | 全库仅 ingestion_service.py:221 删除 Document（grep 证实）；API delete/replace 均转 ingestion（service.py:488-566）。例外：CLI 导入直写（P2）、graph_seed 绕过 outbox 同步（P1#4） |
| 5 | 原位替换递增 content_generation、复用未变化 Chunk | 符合 | ingestion_service.py:637（+1）；chunk_repository.py:83-114（chunk_key 复用） |
| 6 | 失败不恢复旧版本 | **违反** | ingestion_service.py:165-172 + test_document_replace_delete.py:160-180 固化恢复行为（见 P0#3） |
| 7 | 默认图检索只使用 confirmed/published | 符合 | graph_schemas.py:46 `TRUSTED_REVIEW_STATUSES={"confirmed","published"}`；query 默认 statuses（graph_schemas.py:85）；向量种子检索带 review_statuses 过滤（retrieval_service.py:160-166）。注：`/graph/snapshot` 默认含 candidate（routes:467），定位为管理页接口，待验证前端用途 |
| 8 | Agent 图谱工具接收 knowledge_base_ids，不读 backend_data_registry/cognitive_maps | 符合 | tools/knowledge/knowledge_graph_query/tool.py:37-45、knowledge_graph_build/tool.py:30-34；运行时强制注入会话已选 KB（agent/runtime/tool_coordinator.py:38-42，test_agent_knowledge_graph_context.py:19-27）；legacy 断言 test_legacy_cognitive_map_runtime_removed.py:4-22；grep 未发现图谱工具读 cognitive_maps |
| 9 | can_search/can_manage 同时约束文档、图查询、图编辑 | **机制覆盖、实际失效** | 图查询/编辑/文档入口都挂了检查（knowledge_graph_routes.py:133-149、knowledge_base_routes.py 各端点、knowledge_scene_routes.py:37-48）✓；但 can_search 恒真、can_upload 无 owner 校验、can_manage_documents 公共库全放行（permissions.py:85-154）→ 约束力接近零（见 P0#2）；Agent 工具链路无独立校验，仅靠 coordinator 注入缓解（待验证会话选择环节是否过滤） |

## 五、亮点

1. **事务性 Outbox 设计完整**：入队与事实同事务（ingestion_service.py:284-346）、幂等键唯一约束（graph_models.py:259-272）、`pg_advisory_xact_lock` 保护 per-record 版本分配（index_outbox.py:79-105）、`is_latest` 丢弃被取代事件（:212-222）、claim 用 `skip_locked`+租约，web/worker 并发消费无竞争。
2. **读路径防孤儿向量**：检索把 Qdrant 命中回 PG 校验 `vector_status=indexed` 并保留 legacy 白名单（retrieval_service.py:123-153），删除/替换未同步的向量不会泄漏给用户。
3. **稳定分块身份**：`chunk_key=content_hash:occurrence` 让替换只动变化块，Mention/向量天然复用，且有 test_chunk_repository.py、test_document_replace_delete.py 的行为契约。
4. **图谱构建的并发正确性**：任务租约 + started_at owner_token 条件 UPDATE + 心跳续租 + 恢复循环（graph_build_service.py:93-172, 307-353），`_persist_graph_extraction` 在事务内再做文档/Chunk 世代与租约双重校验（ingestion_service.py:348-435）。
5. **抽取溯源**：ExtractionRun 记录 prompt/model/延迟/原始响应，Mention 反查可给出 `stale` 标记（knowledge_graph_routes.py:196-222）。
6. **schema 初始化有序**：init_db 用 `pg_advisory_xact_lock` 串行化多进程建表（database.py:61-65, 327-337），启动默认只验连接、建表 opt-in（lifecycle/database.py:34-43，test_lifecycle_database_initialization.py 契约）。
7. **文档处理队列可恢复**：行锁 claim + JSON lease + 心跳 + attempts 上限 + 启动兜底收养（tasks.py:75-121, 153-163），web/worker 双端安全。
8. **session_resources 仓储事务规范**：显式 `db.begin()` + 版本行 `with_for_update`（session_resources_repository.py:92-130）。

## 六、修复优先级路线建议

1. **立即（P0）**：修 `get_knowledge_db` 提交语义并同步修正 test_knowledge_graph_routes.py 的 override；给 can_upload/can_manage_documents/filter_accessible_ids 补私有库 owner 判断；决策「失败恢复旧版本」去留——按铁律移除 `_restore_replacement`，并为「persist 之后失败」补一条回归测试。
2. **本周（P1）**：索引事件下沉 repository（覆盖 graph_seed/set_review_status）；`delete_knowledge_base` 改为先 PG 后异步清 Qdrant 并检查返回值；补 chunk 向量全量重建入口（reindex 扩展到 chunk 或专用 rebuild）；GraphBuildService.run 捕获异常落 failed + attempts 上限；outbox 增加 dead 状态与 completed 归档。
3. **规划（P2）**：graph_repository 查询下推 SQL；删除/reset 大事务分批；孤儿 LO/集合/staging 对账任务；连接池与 PG max_connections 容量核算；`update_graph_schema` 收敛到 scene 版本化流程；统一 chunk_size 默认值。

以上行号以当前工作树为准；P0-1/P0-2 建议由 backend-core-reviewer 在接口层复核交叉确认。
