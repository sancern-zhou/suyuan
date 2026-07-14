# Suyuan 本地 Nginx生产入口设计

## 目标

使用 Docker Nginx替换当前公网入口后的 Vite 开发服务器，在不改变公网地址 `http://219.135.180.51:56041` 和本机入口端口 `5174` 的前提下，由 Suyuan 自己承担前端静态资源、公司认证代理、业务 API 和 WebSocket 转发，不再依赖公司网关新增 `/api/suyuan/**` 路由。

## 部署结构

Nginx容器使用 host network，监听宿主机 `5174`，设置 `restart: unless-stopped`。前端生产构建目录只读挂载到 `/usr/share/nginx/html`，版本化 Nginx配置只读挂载到容器配置目录。

```text
公网 219.135.180.51:56041
  → 宿主机 10.10.10.192:5174
  → Docker Nginx
      ├── /api/auth/**       → 10.10.204.80:8025/api/auth/**
      ├── /api/suyuan/ws/**  → 127.0.0.1:8000/ws/**
      ├── /api/suyuan/**     → 127.0.0.1:8000/api/**
      └── 其他路径            → Vue dist/index.html
```

## 路由规则

### 公司认证

- `/api/auth/**` 保持原始 URI 转发到公司网关 `10.10.204.80:8025`。
- 保留前端发送的 `Authorization`、`SysCode: JCXT`、`Sign` 和 `encryptType`。
- 登录、验证码、当前用户和退出均使用该入口。

### Suyuan HTTP业务

- `/api/suyuan/{path}` 转发为后端 `/api/{path}`。
- 保留 `Authorization` 和业务 `SysCode: SUYUAN`。
- 删除客户端传入的 `X-User-Id` 和 `X-Is-Admin`。
- 后端只看到来自本机回环地址的 Nginx连接，符合现有可信网关配置。

### Suyuan WebSocket

- `/api/suyuan/ws/{path}` 转发为后端 `/ws/{path}`。
- 使用 HTTP/1.1 并转发 `Upgrade`、`Connection`。
- WebSocket路由优先于普通 `/api/suyuan/**` 路由。

### Vue SPA

- 静态文件存在时直接返回。
- `/login` 等前端路由回退到 `/index.html`。
- 带哈希的 `assets` 文件使用长期缓存；`index.html` 禁止长期缓存，避免发布后仍加载旧资源。

## 仓库文件

- `deploy/nginx/suyuan.conf`：生产反向代理和静态资源配置。
- `deploy/nginx/docker-compose.yml`：Nginx容器定义、host network、只读挂载及重启策略。
- `deploy/nginx/README.md`：构建、启动、验证、升级和回滚命令。

## 发布流程

1. 执行前端测试和 `npm run build`。
2. 使用 `nginx -t` 在临时容器中验证配置。
3. 停止占用 `5174` 的 Vite进程。
4. 启动 Suyuan Nginx容器。
5. 验证登录页、验证码、认证接口、业务接口和 WebSocket升级。
6. 若失败，停止容器并恢复原 Vite进程作为临时回滚。

## 安全与日志

- 不在 Nginx配置中记录或写入账号、密码、Token、SM2/SM4明文参数。
- 访问日志使用默认摘要信息，不记录请求体和 Authorization。
- 设置合理的上传大小、连接超时和代理超时，支持现有文件上传及长任务。
- Nginx不直接对外暴露后端 `8000`；现有宿主机监听暂保留，后续可通过防火墙进一步限制。

## 验收标准

- 本机 `http://127.0.0.1:5174/login` 返回生产构建页面，不包含 Vite客户端脚本。
- `/api/auth/token/captcha` 返回图片。
- 使用测试账号完成 `JCXT` 登录和当前用户查询。
- `/api/suyuan/health`、`/api/suyuan/ready` 返回 200。
- 匿名访问受保护业务接口返回 401。
- 使用有效 Token 和 `SUYUAN` 访问业务接口返回 200。
- Nginx容器重启后自动恢复，前端及代理入口继续可用。

## 范围边界

本次不修改公网 NAT 映射、不申请域名或证书、不修改公司认证网关、不取消 Nacos 注册，也不删除公司网关路由契约文件；该契约保留作为未来平台同源集成的备选方案。
