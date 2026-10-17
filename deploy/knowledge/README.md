# 知识库任务与数据维护

知识库管理、文档处理、图谱、索引 Outbox 与检索统一使用 `KNOWLEDGE_DATABASE_URL`；未配置时回退 `DATABASE_URL`。中央共享知识库仍由 `SHARED_KNOWLEDGE_DATABASE_URL` / `SHARED_KNOWLEDGE_DATABASE_NAME` 单独路由。

## 文档任务

上传接口在保存 Document 的同一个事务内发布任务，参数存储于 Document 的 `extra_metadata._processing_task`。worker 持续从数据库领取，不依赖 web 进程内存，无需新增数据库表或迁移。

- worker 默认并发 3；使用 PostgreSQL 行锁与 `SKIP LOCKED` 领取。
- 租约默认 300 秒，每三分之一个租期续约。租约过期后其他 worker 可以重新领取；旧持有者不能更新新任务状态。
- 失败最多尝试 3 次，切分策略、大小、重叠量及模型模式在重试和重启后保留。
- 正常停止 worker 会把未完成任务释放为 queued；进程异常退出后通过租约恢复。
- 手动重试失败文档也发布持久任务，不在 HTTP 请求内重新执行长时间处理。

web 与 worker 必须使用相同的知识库数据库配置，并能访问上传暂存文件所在目录。部署或重启仍遵守根目录 AGENTS.md 的 web/worker 配对要求。

## 检索

普通检索与图谱检索共用 `KnowledgeRetrievalService`。阈值、元数据过滤、dense/hybrid 选择和重排策略由统一入口传递；图谱增加扩展与融合。普通和图谱路径均排除缺失或尚未索引的 canonical Chunk。

尚未迁移的旧向量仅在原文档存在、已完成且该文档没有 canonical Chunk 时保留读取兼容。文档完成迁移后，旧投影不再绕过事实校验。

知识问答不再执行 HyDE 自动关键词生成；保留首轮证据预取、Agent 按需换词补查和独立网页摘要补充。

## 备份与旧迁移工具

`backend/app/knowledge_base/export_knowledge_base.py` 和 `import_knowledge_base.py` 仅为旧格式迁移工具，默认拒绝执行。确需迁移旧数据时必须显式传 `--legacy-format`；Python 调用需传 `legacy_format=True`。导出拒绝存在 canonical Chunk 的知识库，导入在写入前拒绝 typed vectors，避免创建缺少事实表的投影。

当前知识库的完整备份应覆盖：

1. `KNOWLEDGE_DATABASE_URL` 指向数据库的 PostgreSQL 备份，例如使用 `pg_dump` / `pg_restore`。这里包含 Chunk、图谱、来源引用、场景、规则、抽取记录及 Outbox 等事实。
2. PostgreSQL Large Object 原文件（数据库备份必须包含）及数据库外的本地/对象存储原文件。
3. 对应 shared/local Qdrant collection 的一致性快照或经过验证的重建方案。

应在静止写入窗口或已有的一致性备份流程内执行，恢复后验证文档、事实、来源和索引一致性。旧脚本的 JSON/Qdrant 导出不构成完整备份。本次代码清理不会自动执行备份、恢复或数据迁移。
