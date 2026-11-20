# 嵌入与重排部署（bge-m3 独立服务 / 内网 AI 网关）

两种形态二选一，靠 `backend/.env` 切换，代码同一条路径
（`RemoteEmbeddingModel` / `RemoteReranker`）：

| 形态 | 适用 | 关键配置 |
|---|---|---|
| native（自建 bge-m3） | 有本机 GPU/CPU 余量、无网关配额 | `EMBEDDING_SERVICE_URL=http://127.0.0.1:8020`、`FORMAT=native` |
| openai（内网网关） | 复用网关 Qwen3-Embedding-8B / Qwen3-Reranker-8B，进程零显存 | `FORMAT=openai` + `MODEL` + `jcmp-token` |

> 切换嵌入模型会改变向量维度（bge-m3=1024，Qwen3-Embedding-8B=4096）。已有非空
> 集合无法就地升级：`vector_store` 会在读写前比对 `dense_size` 并抛错
> `Collection ... stores 1024-dim dense vectors but the active embedding model
> produces 4096-dim ... Re-index this knowledge base`。空集合会自动删除重建。
> 因此切到网关模型前，必须先对每个已有知识库重新入库（或用
> `backend/scripts/migrate_qdrant_collections.py` 迁移），否则检索直接失败。

## 网关模式（Qwen3-Embedding-8B + Qwen3-Reranker-8B）

```dotenv
EMBEDDING_SERVICE_URL=http://<gateway>/api/v1
EMBEDDING_SERVICE_FORMAT=openai
EMBEDDING_SERVICE_MODEL=Qwen3-Embedding-8B
EMBEDDING_SERVICE_API_KEY=sk_zmp_...
EMBEDDING_SERVICE_API_KEY_HEADER=jcmp-token
EMBEDDING_SERVICE_API_KEY_PREFIX=
EMBEDDING_SERVICE_BATCH_SIZE=32
EMBEDDING_SERVICE_TIMEOUT_SECONDS=60

KNOWLEDGE_RERANK_BACKEND=remote
KNOWLEDGE_RERANK_API_URL=http://<gateway>/api/v1/rerank
KNOWLEDGE_RERANK_MODEL=Qwen3-Reranker-8B
KNOWLEDGE_RERANK_API_KEY=sk_zmp_...
KNOWLEDGE_RERANK_API_KEY_HEADER=jcmp-token
KNOWLEDGE_RERANK_API_KEY_PREFIX=
KNOWLEDGE_RERANK_TIMEOUT_SECONDS=8
```

要点：

- `FORMAT=openai` 时客户端自动补 `/embeddings`，body 为 `{model, input}`；
  native 时补 `/embed`，body 为 `{texts, normalize}`。
- 认证头规则：`API_KEY_HEADER` 留空默认 `Authorization` 并加 `Bearer ` 前缀；
  配置自定义头（如 `jcmp-token`）时默认裸值，`API_KEY_PREFIX` 留空即可。
  网关只认 `jcmp-token`，用 `Authorization: Bearer` 会 401。
- 网关不保证返回向量已归一化，客户端在 `FORMAT=openai` 下统一做 L2 归一化。
- 重排请求 `{model, query, documents, top_n}`，返回 `results[].{index, relevance_score}`。
- 该模式下 **不要** 启动 `app.services.embedding_server`（也不再需要 bge-m3 权重），
  web worker 内存不再被模型封顶。
- 网关模型的 key 与 LLM 的 `LLM_EXTRA_HEADERS` 是两套凭据，不要复用。

## native 模式（自建 bge-m3 独立服务）

### 许昌部署：LLM 并发调优 + 嵌入服务外置

两层优化配套实施。第一层放开 LLM 并发闸门（解除对话排队），第二层把 bge-m3
权重收敛为全机一份（解除 worker 数的内存封顶）。代码层改动已入库本分支：

- `backend/app/services/embedding_server.py`：独立嵌入服务（新）
- `backend/app/knowledge_base/remote_embedding.py`：远程嵌入客户端（新）
- `backend/app/knowledge_base/vector_store.py`、`document_processor.py`：配置
  `EMBEDDING_SERVICE_URL` 后不再本地加载权重（改）
- `backend/.env.example`：新增配置项说明（改）

### 内存账（为什么这么做）

| 项 | 改造前 | 改造后 |
|---|---|---|
| 每 web worker 常驻 | 业务 + bge-m3 ≈ 1G | 仅业务 |
| bge-m3 副本数 | 3 份（3 worker）+ worker 进程按需 | 1 份（独立服务 ≈ 1.2G） |
| 6.5G 机器 worker 上限 | 3（4 个即 OOM） | 5~6（按内存余量） |
| LLM 并发闸门 | 2/worker → 全机约 6 路在飞 | 8/worker → 全机 24 路起步 |

前置确认：上游 DeepSeek 中转 RPM=100（按账号计，3 worker 共享）。
`LLM_GLOBAL_MAX_CONCURRENCY=8` 时请求速率 ≈ `3×8 ÷ 平均单次时长 × 60`，
平均 20~30 秒单次时长约 48~72 次/分钟，留有余量；日志出现 429 再回调。

### 第一步：更新代码

```bash
cd <xuchang工作树>
git fetch origin && git checkout xuchang && git pull origin xuchang
```

### 第二步：修改 backend/.env

```bash
cd <xuchang工作树>/backend

# 第一层：LLM 并发池上限（原默认 2，未显式配置过则直接追加）
grep -q '^LLM_GLOBAL_MAX_CONCURRENCY=' .env && \
  sed -i 's/^LLM_GLOBAL_MAX_CONCURRENCY=.*/LLM_GLOBAL_MAX_CONCURRENCY=8/' .env || \
  echo 'LLM_GLOBAL_MAX_CONCURRENCY=8' >> .env

# 第二层：指向独立嵌入服务（留空即回退旧的本地加载行为）
echo 'EMBEDDING_SERVICE_URL=http://127.0.0.1:8020' >> .env
```

### 第三步：启动嵌入服务（先于 web/worker）

按 AGENTS.md 规范用 setsid + nohup 脱离会话：

```bash
cd <xuchang工作树>/backend
BACKEND_PYTHON=/path/to/conda/envs/backend_py311/bin/python

nohup setsid "$BACKEND_PYTHON" -m app.services.embedding_server \
  > /tmp/suyuan-embedding.log 2>&1 < /dev/null &
echo $! > /tmp/suyuan-embedding.pid
```

启动即加载模型（加载失败进程会直接退出）。确认：

```bash
ss -ltnp | grep 8020                      # 端口在听
curl -s http://127.0.0.1:8020/health      # {"status":"ok","model_loaded":true,"dim":1024}
tail -5 /tmp/suyuan-embedding.log         # bge_m3_model_loaded
```

### 第四步：成对重启 web 与 worker

参照 AGENTS.md（web 3 个 uvicorn worker + 单实例 app.worker）：

```bash
# 停旧进程（用 PID 文件，不要只关终端）
kill $(cat /tmp/suyuan-web.pid) $(cat /tmp/suyuan-worker.pid) 2>/dev/null
sleep 3

cd <xuchang工作树>/backend
nohup setsid "$BACKEND_PYTHON" -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8000 --workers 3 --env-file .env --no-proxy-headers \
  > /tmp/suyuan-web.log 2>&1 < /dev/null &
echo $! > /tmp/suyuan-web.pid

nohup setsid "$BACKEND_PYTHON" -m app.worker --env-file .env \
  > /tmp/suyuan-worker.log 2>&1 < /dev/null &
echo $! > /tmp/suyuan-worker.pid
```

（端口按许昌实际部署端口替换；启动命令以服务器现有 PID 文件/运维脚本为准。）

### 第五步：验证清单

```bash
# 1. 两个 web worker 端口与 worker 内部端口都在监听
ss -ltnp

# 2. 每个 web worker 都走了远程嵌入（应出现 3 次，每 worker 一次）
grep -c embedding_using_remote_service /tmp/suyuan-web.log

# 3. 并发池新上限已生效（应看到 limit=8）
grep llm_pool_concurrency_configured /tmp/suyuan-web.log

# 4. 内存变化：web 进程 RSS 各降约 1G，嵌入服务常驻约 1.2G
free -h
ps -o pid,rss,cmd -C python | sort -k2 -n | tail -8

# 5. 业务冒烟：前端发起一次知识问答，确认回答正常、
#    /tmp/suyuan-embedding.log 有请求日志
```

#### 并发调收敛（上线后观察一两天）

- 排队仍在：`grep llm_pool_concurrency_acquired /tmp/suyuan-web.log` 中
  `wait_ms` 持续偏大 → 调大 `LLM_GLOBAL_MAX_CONCURRENCY`（步进 +4）；
- 上游顶不住：`grep llm_rate_limit_detected /tmp/suyuan-web.log` 频繁 → 调小。

### 第六步（可选）：扩 worker

内存确认有 1.5G 以上余量后，把 uvicorn `--workers` 提到 5~6 并重启 web。
连带检查：PostgreSQL `max_connections` ≥ worker 数 × 50（每 worker 连接池
20+30 溢出）+ 嵌入服务/worker 进程/运维余量。

### 回滚

```bash
# 删掉 EMBEDDING_SERVICE_URL 行 → 重启 web 与 worker：恢复每进程本地加载模型
kill $(cat /tmp/suyuan-embedding.pid)    # 停嵌入服务
LLM_GLOBAL_MAX_CONCURRENCY 改回 2 → 重启 web：恢复原并发闸门
```
