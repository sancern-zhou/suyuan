# 本机应用数据 PostgreSQL（会话历史 / 定时任务执行记录）

远端 `DATABASE_URL`（如火山引擎 weather_db）公网带宽有限（实测 ~30-70KB/s），会话消息与
任务执行记录含大 JSONB 负载，加载一次需数秒到数十秒。本目录在本机部署专用 PostgreSQL，
通过 `SESSION_DATABASE_URL` 承载以下低容量、高延迟敏感表：

- 会话与消息：`sessions`、`session_messages`、`conversation_catalog`
- 会话资源目录：`session_resources`、`session_resource_versions`
- 定时任务执行记录：`scheduled_task_executions`
- Draw.io 数据：`drawio_boards`、`drawio_board_versions`
- 社交账号与任务：`social_users`、`social_session_mappings`、`weixin_scan_tasks`
- 社交报告结果：`social_report_results`

其余表（气象数据、知识库、上传文件等）继续走 `DATABASE_URL`，代码按 URL 自动路由：
`SESSION_DATABASE_URL` 未设置时回退 `DATABASE_URL`，行为与旧版完全一致。

已知限制：知识问答（KNOWLEDGE_QA）的目录条目由 `knowledge_base/conversation_store.py`
经主库 session 写入，未路由到本机库，因此知识问答会话不出现在会话列表；本部署知识库为空，
暂不影响。若启用知识库，需一并规划该写入路径。

## 启动

```bash
cd deploy/postgres
cp .env.example .env   # 修改 LOCAL_PG_PASSWORD
docker compose -p suyuan-main -f docker-compose.local.yml up -d
```

不同项目分支用不同 Compose 项目名与端口（如 `-p suyuan-jiangsu-ops`、`LOCAL_PG_PORT=5434`）。
注意宿主机 5432 已被 skillhub-postgres 占用，本项目固定使用 5433。

## 后端接入

在对应项目的 `backend/.env` 中设置（web 与 worker 必须同值）：

```dotenv
SESSION_DATABASE_URL=postgresql+asyncpg://suyuan:<password>@127.0.0.1:5433/suyuan_app
```

首次启动前初始化 schema 并迁移数据：

```bash
cd backend
python -m app.db.init_session_db
```

## 数据迁移与回补

`backfill_session_tables.py` 负责从远端库把上述表搬到本机（凭据从 backend/.env 与
本目录 .env 读取，不写死在脚本里）：

```bash
cd deploy/postgres
python backfill_session_tables.py recent --days 7                 # 首次：最近 7 天
python backfill_session_tables.py delta --since 2026-09-21T08:51:58  # 切换前追平增量
python backfill_session_tables.py history --before 2026-09-14T00:00:00  # 后续按会话分批回补历史
```

`recent` 会清空目标表后导入，`delta`/`history` 只增不删。历史会话未回补前，UI 历史列表
只显示已迁移的会话；远端数据保持不变，可随时在带宽空闲时用 `history` 分批补齐。

## 共享知识库注意

`weather_db` 曾同时充当共享知识库中心（`SHARED_KNOWLEDGE_DATABASE_NAME=weather_db`）。
应用数据迁离远端后，若本项目的知识库数据也随 `sessions` 之外的主库迁移，其他分支的
`SHARED_KNOWLEDGE_DATABASE_NAME`（基于其自身 DATABASE_URL 推导）会指向旧库；跨机场景应
改用完整 `SHARED_KNOWLEDGE_DATABASE_URL` 指向新的中心库。

## 备份

数据迁入本机后为单盘存储，用 `backup.sh` 定时逻辑备份（crontab 示例见脚本头部注释）。
