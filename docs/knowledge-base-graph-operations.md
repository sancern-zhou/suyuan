# 知识库图谱迁移与运维

知识库文档、Chunk、实体、关系、Mention、审核状态和索引 Outbox 以 PostgreSQL 为唯一事实源。每个知识库只有一个 Qdrant Collection，其中使用 `record_type=chunk/entity/relation` 区分可重建索引。

## 发布前备份

1. 备份 PostgreSQL：`pg_dump --format=custom --file=suyuan-before-knowledge-graph.dump "$DATABASE_URL"`。
2. 对 Qdrant 创建 collection snapshot，并记录每个 `kb_*` collection 的 point 数。
3. 只读备份 `backend/backend_data_registry/cognitive_maps`；迁移程序不会删除该目录。
4. 在维护窗口停止 worker，避免迁移期间继续消费旧任务。

## 数据库模型迁移

在 backend 目录和 backend_py311 环境执行：

```bash
conda run -p /root/miniconda3/envs/backend_py311 python -m app.alembic.versions.create_unified_knowledge_graph
conda run -p /root/miniconda3/envs/backend_py311 python -m app.alembic.versions.add_scenario_driven_knowledge_graph
```

确认 `knowledge_chunks`、图谱事实/Mention 表和 `knowledge_index_outbox` 存在，再启动应用。迁移没有 destructive downgrade；回退使用发布前数据库备份。

场景驱动版本发布时按以下顺序执行迁移和聚焦测试：

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 python -m app.alembic.versions.add_scenario_driven_knowledge_graph
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/knowledge_base tests/api/test_knowledge_scene_routes.py tests/api/test_knowledge_graph_routes.py -q
```

存量知识库迁移后进入 `awaiting_confirmation`，需要上传或选用至少一份代表性文档并确认系统发现的业务对象和业务逻辑，之后才能重新构建图谱。存量图谱事实保留原审核状态，场景、Schema 和规则版本均为 `0`；不会被自动提升为新场景下的事实。回滚不执行破坏性 downgrade，必须恢复发布前 PostgreSQL 备份，并按需从 snapshot 重建 Qdrant 派生索引。

## 离线质量评估

金标 JSONL 每行代表一个 Chunk，至少包含 `chunk_id`，并可包含 `gold_entities`、`gold_relations`、`predicted_entities`、`predicted_relations`、`evidence_valid` 和 `entity_link_valid`。实体采用 `[类型, 名称]`，关系采用 `[主体名称, 关系类型, 客体名称]`。

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 python scripts/evaluate_scene_graph.py \
  --kb-id <kb_id> --gold-jsonl <gold.jsonl> --output-json <metrics.json>
```

报告包含实体与关系的精确率、召回率和 F1，以及类型准确率、实体链接准确率、证据支持率、重复实体率、Schema 违反率和孤立实体率。指标偏低不会让脚本非零退出；数据格式错误或执行失败才会返回错误码。

## Chunk 回填

```bash
python scripts/migrate_unified_knowledge_graph.py --dry-run
python scripts/migrate_unified_knowledge_graph.py --apply --kb-id <kb_id>
python scripts/migrate_unified_knowledge_graph.py --verify --kb-id <kb_id>
```

先检查每库 `qdrant_points`、`postgres_chunks`、`missing_documents` 和 `unrecovered_metadata`。只有 dry-run 对账合理后执行 apply。脚本可重复执行。

## 认知地图迁移

```bash
python scripts/migrate_cognitive_maps_to_knowledge_bases.py --source-root backend_data_registry/cognitive_maps --dry-run
python scripts/migrate_cognitive_maps_to_knowledge_bases.py --source-root backend_data_registry/cognitive_maps --apply
python scripts/migrate_cognitive_maps_to_knowledge_bases.py --source-root backend_data_registry/cognitive_maps --verify
```

需要合并到已有知识库时增加 `--map-to-kb map_id=kb_id`。迁移保留 Schema、审核状态和可恢复 Evidence/Mention；启用的旧 ops binding 只转换为默认知识库，不迁移 binding 机制。

## Outbox 与 Qdrant 重建

检查积压：

```sql
SELECT status, count(*), max(attempts) FROM knowledge_index_outbox GROUP BY status;
SELECT id, record_type, record_id, attempts, last_error
FROM knowledge_index_outbox WHERE status = 'pending' ORDER BY created_at LIMIT 100;
```

重建图索引可调用 `POST /api/knowledge-base/{kb_id}/graph/reindex`。全量重建时先清空目标 collection 的派生 point，再从 PostgreSQL Chunk、实体和关系生成 upsert Outbox；不要从旧 JSON 反向覆盖事实表。

## 切换与故障排查

- web 角色只提供 API；worker/all 角色消费 Outbox。
- 确认 `/api/knowledge-base/{kb_id}/graph/*` 可用，旧 cognitive-map router 不再注册。
- Qdrant 失败：检查 `last_error`、网络和 collection vector 配置；修复后等待指数退避重试。
- 文档 `partial`：普通 Chunk 已可用，修复抽取服务后调用 `graph/retry-failed`。
- 替换失败：不会恢复旧版本；再次替换当前文档或重试。
- stale generation：检查是否有旧 worker；旧任务必须被 Outbox 版本检查丢弃。

## 旧目录人工清理

迁移 verify、业务抽查和备份均完成后，先停止服务，再人工归档；应用不会自动执行清理：

```bash
tar -C backend/backend_data_registry -czf cognitive_maps-archive.tgz cognitive_maps
# 经变更审批和恢复演练后再人工删除原目录
```

不要在迁移、发布脚本或应用启动逻辑中自动删除旧目录。
