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
npm run build:standalone

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
npm run build:standalone
cd ..
docker compose -p suyuan-nginx -f deploy/nginx/docker-compose.yml restart nginx
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
