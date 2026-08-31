# Suyuan 本地 Nginx部署

该入口使用生产构建提供 Vue SPA，并将公司认证请求转发到公司网关、将 Suyuan HTTP 与 WebSocket 请求直接转发到本机后端。

## 前置条件

- 后端监听 `127.0.0.1:8000` 或 `0.0.0.0:8000`。
- Docker 与 Docker Compose 可用。
- 正式启动前已经生成 `frontend/dist`。

## 构建与配置检查

```bash
cd /home/xckj/suyuan/frontend
npm run test:auth
npm run test:event-tasks
PROJECT=default npm run build:standalone

grep -R "resources?presentation_type=document" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/office-documents" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/visualizations" /home/xckj/suyuan/frontend/dist/assets

cd /home/xckj/suyuan
docker compose -f deploy/nginx/docker-compose.yml config
```

## 备用端口演练

演练使用 5175，不影响当前 5174 的 Vite 服务：

```bash
cd /home/xckj/suyuan
SUYUAN_NGINX_PORT=5175 \
SUYUAN_NGINX_CONTAINER_NAME=suyuan-nginx-rehearsal \
docker compose -p suyuan-nginx-rehearsal -f deploy/nginx/docker-compose.yml up -d

curl -fsS http://127.0.0.1:5175/login
curl -fsS http://127.0.0.1:5175/api/suyuan/health

SUYUAN_NGINX_PORT=5175 \
SUYUAN_NGINX_CONTAINER_NAME=suyuan-nginx-rehearsal \
docker compose -p suyuan-nginx-rehearsal -f deploy/nginx/docker-compose.yml down
```

## 正式切换到 5174

先停止当前 Vite 进程，确认 5174 已释放，再启动 Nginx：

```bash
cd /home/xckj/suyuan
ss -ltnp | grep ':5174'
docker compose -p suyuan-nginx -f deploy/nginx/docker-compose.yml up -d
docker compose -p suyuan-nginx -f deploy/nginx/docker-compose.yml ps
```

如生产环境地址不同，可在命令前覆盖：

```bash
AUTH_UPSTREAM=http://company-gateway:8025 \
BUSINESS_UPSTREAM=http://127.0.0.1:8000 \
docker compose -p suyuan-nginx -f deploy/nginx/docker-compose.yml up -d
```

## 升级

```bash
cd /home/xckj/suyuan/frontend
PROJECT=default npm run build:standalone
grep -R "resources?presentation_type=document" dist/assets
! grep -R "/office-documents" dist/assets
! grep -R "/visualizations" dist/assets
docker exec suyuan-nginx nginx -s reload
```

## Android 社交 App 路由

当某个分支需要给 Android App 提供对话、会话和广播收件箱能力时，Nginx 模板必须把下面两条前缀原样转发到后端：

```nginx
location ^~ /api/social/app/voice/realtime {
    proxy_pass ${BUSINESS_UPSTREAM};
}

location ^~ /api/social/app/ {
    proxy_pass ${BUSINESS_UPSTREAM};
}
```

注意 `proxy_pass` 不要再追加 `/api` 或其他路径，否则 App 接口会被改写成错误地址。

许昌等其他分支部署时，只需要替换对应工作树、端口、容器名和后端环境文件，保持这两条路由规则不变。改完后重建或重启对应 Nginx 容器，再用下面三条接口核对：

```bash
POST /api/social/app/auth/login
POST /api/social/app/chat/stream
GET  /api/social/app/push/status
```

## 项目选择

后端与前端必须使用来自 `projects/<id>/project.yaml` 的同一项目标识。构建前先校验后端读取结果：

```bash
export PROJECT=default
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 python -c \
  "from app.project_config.loader import load_project_context; print(load_project_context('$PROJECT').model_dump_json())"

cd /home/xckj/suyuan/frontend
npm run build:standalone
```

每次部署记录 `PROJECT`、Git commit SHA、项目清单校验和及构建产物版本。客户发布标签用于标识部署快照，例如 `jiyuan/v2026.07.1`，不创建永久客户分支。

## 项目端口与构建产物

每个部署目录（工作树）只维护一套正式前端产物 `frontend/dist`。下表为本机当前部署的风清气智与江苏运维两个项目的固定布局，其他项目部署时按实际环境单独规划：

| 项目 | 容器 | 端口 | 后端 | 后端环境文件 | 部署目录（工作树/分支） | 构建命令 |
| --- | --- | ---: | ---: | --- | --- | --- |
| 风清气智 | `suyuan-nginx` | 5174 | 8000 | `backend/.env` | `/home/xckj/suyuan-main`（main） | `PROJECT=default npm run build:standalone` |
| 江苏运维 | `suyuan-nginx-jiangsu` | 5175 | 8001 | `backend/.env.jiangsu-ops` | `/home/xckj/suyuan`（project/jiangsu-ops） | `PROJECT=jiangsu-ops npm run build:standalone` |

两个 Nginx 容器禁止挂载同一个 `frontend/dist`；发布后必须检查首页标题与容器挂载。不创建 `dist-*` 目录。

### 固定后端数据目录

数据库中的会话资源 locator 会持久化文件路径。每个部署使用的后端环境文件都必须显式配置绝对路径形式的 `DATA_REGISTRY_DIR`，同一项目的 web 与 worker 必须使用完全相同的值。不得使用 `backend_data_registry` 这类相对值，否则从另一 Git worktree 启动时会解析到新的空目录，历史资源会因路径安全校验返回 `resource_path_forbidden`。

本机固定配置如下；其他部署替换为各自的绝对路径：

```dotenv
# backend/.env（风清气智）
DATA_REGISTRY_DIR=/home/xckj/suyuan/backend/backend_data_registry

# backend/.env.jiangsu-ops（江苏运维）
DATA_REGISTRY_DIR=/home/xckj/suyuan/backend/backend_data_registry_jiangsu_ops
```

启动或切换工作树前先校验配置：

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/envs/backend_py311/bin/python \
  -m app.utils.deployment_preflight --env-file .env
```

`start.sh`、`restart_server.sh` 与 `python -m app.worker` 都会自动执行该校验；校验失败时禁止绕过这些入口直接启动服务。迁移数据目录时，必须同时迁移文件并事务性更新数据库 locator，不能只修改环境变量。

## 双项目同时部署（本机布局）

同一工作树同一时刻只有一套 `frontend/dist`，因此双项目同时在线使用两个部署目录：

- `/home/xckj/suyuan-main`：main 分支工作树，构建 `PROJECT=default`，由它启动 `suyuan-nginx`（5174 → 8000）。首次创建：`git worktree add /home/xckj/suyuan-main main`，并复用主树依赖：`ln -s /home/xckj/suyuan/frontend/node_modules /home/xckj/suyuan-main/frontend/node_modules`。
- `/home/xckj/suyuan`：project/jiangsu-ops 工作树，构建 `PROJECT=jiangsu-ops`，由它启动 `suyuan-nginx-jiangsu`（5175 → 8001）。

两个后端进程统一从 `/home/xckj/suyuan/backend` 启动（共享数据目录 `backend_data_registry`，不随工作树拆分）。web 进程只提供 HTTP API，fetchers、定时任务等后台服务由配套的 worker 进程提供，web 与 worker 必须成对启动（worker 缺失时 `/api/suyuan/fetchers/*`、`/api/suyuan/scheduled-tasks` 等接口返回 503）：

```bash
# 风清气智 8000（backend/.env，默认项目）+ worker（内部端口 8011）
cd /home/xckj/suyuan/backend && bash restart_server.sh
nohup setsid /root/miniconda3/envs/backend_py311/bin/python -m app.worker \
  > /tmp/backend-worker.log 2>&1 &
echo $! > /tmp/suyuan_worker.pid

# 江苏运维 8001（backend/.env.jiangsu-ops）+ worker（内部端口 8012）
cd /home/xckj/suyuan/backend
export DATABASE_SCHEMA_INIT_ON_STARTUP=false
nohup setsid /root/miniconda3/envs/backend_py311/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8001 --workers 1 --env-file .env.jiangsu-ops --no-proxy-headers \
  > /tmp/backend-jiangsu.log 2>&1 &
echo $! > /tmp/suyuan_backend_jiangsu.pid
nohup setsid /root/miniconda3/envs/backend_py311/bin/python -m app.worker \
  --env-file .env.jiangsu-ops > /tmp/backend-worker-jiangsu.log 2>&1 &
echo $! > /tmp/suyuan_worker_jiangsu.pid
```

校验 worker：`ss -tlnp | grep -E ':(8011|8012)'`，并确认 `curl http://127.0.0.1:5175/api/suyuan/fetchers/status` 返回 200。

前端发布（容器挂载的 dist 取决于 Compose 文件所在工作树，必须一一对应）：

```bash
# 风清气智：在 main 工作树中构建并重建 suyuan-nginx
cd /home/xckj/suyuan-main/frontend && PROJECT=default npm run build:standalone
cd /home/xckj/suyuan-main && docker compose -p suyuan-nginx \
  -f deploy/nginx/docker-compose.yml up -d --force-recreate

# 江苏运维：在 jiangsu 工作树中构建并重建 suyuan-nginx-jiangsu
cd /home/xckj/suyuan/frontend && PROJECT=jiangsu-ops npm run build:standalone
cd /home/xckj/suyuan && docker compose -p suyuan-nginx-jiangsu \
  -f deploy/nginx/docker-compose.jiangsu-ops.yml up -d --force-recreate
```

发布后校验：

```bash
curl -fsS http://127.0.0.1:5174/ | grep -F '<title>风清气智</title>'
curl -fsS http://127.0.0.1:5174/api/suyuan/health
curl -fsS http://127.0.0.1:5175/ | grep -F '<title>江苏省运维审核管理服务平台</title>'
curl -fsS http://127.0.0.1:5175/api/suyuan/health
docker inspect suyuan-nginx suyuan-nginx-jiangsu \
  --format '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}'
```

## 回滚

先停止 Nginx释放 5174，再临时恢复 Vite：

```bash
cd /home/xckj/suyuan
docker compose -p suyuan-nginx -f deploy/nginx/docker-compose.yml down
cd frontend
nohup npm run dev -- --host 0.0.0.0 --port 5174 >> vite.log 2>&1 &
```

回滚后检查登录页、验证码和后端健康接口。访问日志不得输出请求体、密码或 Authorization。
