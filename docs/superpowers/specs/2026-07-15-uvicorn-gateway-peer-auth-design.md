# Uvicorn 网关对端鉴权修复设计

## 背景

生产流量经过 Nginx 后进入 Uvicorn。Nginx 设置 `X-Forwarded-For` 保存公网用户 IP，
而 Uvicorn 默认启用 `proxy_headers`，会把可信本机代理提供的公网地址写入 ASGI
`scope.client`。

`GatewayAuthenticationMiddleware` 需要用 `scope.client` 校验当前 TCP 对端是否属于
`TRUSTED_GATEWAY_NETWORKS`。地址被 Uvicorn 改写后，合法外网用户会被误判为直接
连接后端，业务接口在 Bearer Token 校验前返回 `403 untrusted_gateway_peer`。

该问题已稳定复现：经 Nginx 请求同一个受保护接口，不带外部 `X-Forwarded-For`
时返回 401；带公网地址时返回 403。

## 目标

- 鉴权中间件始终使用原始 TCP 对端判断请求是否来自可信网关。
- 外部用户经 Nginx 访问时不再因为公网 IP 被拒绝。
- 保留对绕过 Nginx、直接访问 8000 端口的拒绝能力。
- 不扩大可信网段，不信任客户端自行提供的身份头或转发头。

## 方案

关闭 Uvicorn 对代理头的解析，让 ASGI `scope.client` 保持为原始 socket 对端：

- `backend/start.sh` 增加 `--no-proxy-headers`。
- `backend/restart_server.sh` 增加 `--no-proxy-headers`。
- `backend/app/main.py` 的 `uvicorn.run()` 增加 `proxy_headers=False`。
- `backend/start_windows.py` 的 `uvicorn.run()` 增加 `proxy_headers=False`。

Nginx 保持现有 `X-Forwarded-For` 转发配置。公网 IP 的审计由 Nginx 访问日志负责；
后端安全边界只使用不可由 HTTP 头伪造的 TCP 对端。

不采用把公网地址加入 `TRUSTED_GATEWAY_NETWORKS` 的方案，因为这会允许外部来源
绕过网关信任检查。也不在鉴权中间件中解析 `X-Forwarded-For`，因为该字段描述原始
用户，不描述当前直连网关。

## 测试

增加启动契约测试，覆盖四个正式入口均禁用 Uvicorn 代理头解析：

- Shell 启动命令包含 `--no-proxy-headers`。
- Python 启动调用明确设置 `proxy_headers=False`。

部署验证：

1. 重启后端。
2. 通过 Nginx 请求受保护接口并显式携带公网 `X-Forwarded-For`。
3. 无 Token 时应返回 401 `authentication_required`，不得返回 403
   `untrusted_gateway_peer`。
4. 使用公司 Token 时应进入正常业务鉴权流程。
5. 健康检查、公司验证码和前端鉴权测试继续通过。

## 风险与回滚

关闭代理头解析后，Uvicorn 自身访问日志会显示 Nginx 对端地址而非公网用户地址；
公网访问审计应读取 Nginx 日志。这是维持可信网关边界所需的明确取舍。

如需回滚，移除四个入口的禁用配置并重启后端。但不得通过放宽
`TRUSTED_GATEWAY_NETWORKS` 临时绕过问题。
