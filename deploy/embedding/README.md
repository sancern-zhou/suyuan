# 许昌部署：LLM 并发调优 + 嵌入服务外置

两层优化配套实施。第一层放开 LLM 并发闸门（解除对话排队），第二层把 bge-m3
权重收敛为全机一份（解除 worker 数的内存封顶）。代码层改动已入库本分支：

- `backend/app/services/embedding_server.py`：独立嵌入服务（新）
- `backend/app/knowledge_base/remote_embedding.py`：远程嵌入客户端（新）
- `backend/app/knowledge_base/vector_store.py`、`document_processor.py`：配置
  `EMBEDDING_SERVICE_URL` 后不再本地加载权重（改）
- `backend/.env.example`：新增配置项说明（改）

## 内存账（为什么这么做）

| 项 | 改造前 | 改造后 |
|---|---|---|
| 每 web worker 常驻 | 业务 + bge-m3 ≈ 1G | 仅业务 |
| bge-m3 副本数 | 3 份（3 worker）+ worker 进程按需 | 1 份（独立服务 ≈ 1.2G） |
| 6.5G 机器 worker 上限 | 3（4 个即 OOM） | 5~6（按内存余量） |
| LLM 并发闸门 | 2/worker → 全机约 6 路在飞 | 8/worker → 全机 24 路起步 |

前置确认：上游 DeepSeek 中转 RPM=100（按账号计，3 worker 共享）。
`LLM_GLOBAL_MAX_CONCURRENCY=8` 时请求速率 ≈ `3×8 ÷ 平均单次时长 × 60`，
平均 20~30 秒单次时长约 48~72 次/分钟，留有余量；日志出现 429 再回调。

## 第一步：更新代码

```bash
cd <xuchang工作树>
git fetch origin && git checkout xuchang && git pull origin xuchang
```

## 第二步：修改 backend/.env

```bash
cd <xuchang工作树>/backend

# 第一层：LLM 并发池上限（原默认 2，未显式配置过则直接追加）
grep -q '^LLM_GLOBAL_MAX_CONCURRENCY=' .env && \
  sed -i 's/^LLM_GLOBAL_MAX_CONCURRENCY=.*/LLM_GLOBAL_MAX_CONCURRENCY=8/' .env || \
  echo 'LLM_GLOBAL_MAX_CONCURRENCY=8' >> .env

# 第二层：指向独立嵌入服务（留空即回退旧的本地加载行为）
echo 'EMBEDDING_SERVICE_URL=http://127.0.0.1:8020' >> .env
```

## 第三步：启动嵌入服务（先于 web/worker）

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

## 第四步：成对重启 web 与 worker

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

## 第五步：验证清单

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

### 并发调收敛（上线后观察一两天）

- 排队仍在：`grep llm_pool_concurrency_acquired /tmp/suyuan-web.log` 中
  `wait_ms` 持续偏大 → 调大 `LLM_GLOBAL_MAX_CONCURRENCY`（步进 +4）；
- 上游顶不住：`grep llm_rate_limit_detected /tmp/suyuan-web.log` 频繁 → 调小。

## 第六步（可选）：扩 worker

内存确认有 1.5G 以上余量后，把 uvicorn `--workers` 提到 5~6 并重启 web。
连带检查：PostgreSQL `max_connections` ≥ worker 数 × 50（每 worker 连接池
20+30 溢出）+ 嵌入服务/worker 进程/运维余量。

## 回滚

```bash
# 删掉 EMBEDDING_SERVICE_URL 行 → 重启 web 与 worker：恢复每进程本地加载模型
kill $(cat /tmp/suyuan-embedding.pid)    # 停嵌入服务
LLM_GLOBAL_MAX_CONCURRENCY 改回 2 → 重启 web：恢复原并发闸门
```
