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
```

确认 `knowledge_chunks`、图谱事实/Mention 表和 `knowledge_index_outbox` 存在，再启动应用。迁移没有 destructive downgrade；回退使用发布前数据库备份。

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
