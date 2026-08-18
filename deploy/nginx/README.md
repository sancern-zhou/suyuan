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

每个部署目录只维护一套正式前端产物 `frontend/dist`。端口和后端固定如下：

| 项目 | 容器 | 端口 | 后端 | 静态目录 | 构建命令 |
| --- | --- | ---: | ---: | --- | --- |
| 风清气智 | `suyuan-nginx` | 5174 | 8000 | `frontend/dist` | `PROJECT=default npm run build:standalone` |
| 江苏运维 | `suyuan-nginx-jiangsu` | 5175 | 8001 | `frontend/dist` | `PROJECT=jiangsu-ops npm run build:standalone` |

### 固定后端数据目录

数据库中的会话资源 locator 会持久化文件路径。每个部署使用的后端环境文件都必须显式配置绝对路径形式的 `DATA_REGISTRY_DIR`，同一项目的 web 与 worker 必须使用完全相同的值。不得使用 `backend_data_registry` 这类相对值，否则从另一 Git worktree 启动时会解析到新的空目录，历史资源会因路径安全校验返回 `resource_path_forbidden`。

启动或切换工作树前先校验配置：

```bash
cd backend
/root/miniconda3/envs/backend_py311/bin/python \
  -m app.utils.deployment_preflight --env-file .env
```

`start.sh`、`restart_server.sh` 与 `python -m app.worker` 都会自动执行该校验；校验失败时禁止绕过这些入口直接启动服务。迁移数据目录时，必须同时迁移文件并事务性更新数据库 locator，不能只修改环境变量。

发布时必须在对应项目的部署目录中构建，再检查首页标题和容器挂载。需要同时部署多个项目时，使用独立工作树或部署目录；每个目录仍只使用自己的 `frontend/dist`，不创建 `dist-*`：

```bash
cd /home/xckj/suyuan/frontend
PROJECT=jiangsu-ops npm run build:standalone

curl -fsS http://127.0.0.1:5175/ | grep -F '<title>江苏省运维审核管理服务平台</title>'
docker inspect suyuan-nginx-jiangsu \
  --format '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}'
```

江苏构建完成后，使用专用 Compose 文件重建该容器：

```bash
cd /home/xckj/suyuan
docker compose -p suyuan-nginx-jiangsu \
  -f deploy/nginx/docker-compose.jiangsu-ops.yml up -d --force-recreate
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
