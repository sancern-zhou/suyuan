# Mock 鉴权配置简化设计

## 目标

简化本地 Mock 鉴权的启用方式，消除 `AUTH_MODE=mock` 与
`AUTH_MOCK_ENABLED=true` 两个开关表达同一意图的问题，同时保留生产环境的
硬性安全边界。

## 配置模型

鉴权模式只由 `AUTH_MODE` 决定：

- `AUTH_MODE=company`：使用公司认证平台。
- `AUTH_MODE=mock`：使用固定的本地 Mock 用户。

运行环境仍由 `ENVIRONMENT` 独立决定。`AUTH_MODE` 不得修改、推导或覆盖
`ENVIRONMENT`，因为运行环境还控制 Nacos、Cookie、安全检查和其他非鉴权行为。

`AUTH_MOCK_ENABLED` 从配置模型、示例配置和运行时代码中移除，不再作为第二道
Mock 开关。

## 安全规则

- 当 `ENVIRONMENT=production` 且 `AUTH_MODE=mock` 时，配置校验必须失败，应用拒绝启动。
- 非生产环境下，`AUTH_MODE=mock` 足以启用 Mock 鉴权。
- `AUTH_MODE=company` 的现有认证平台流程及生产环境校验保持不变。
- 不允许因选择 Mock 鉴权而将生产环境静默降级成开发环境。

## 运行时行为

后端鉴权中间件、身份服务和 `/auth/runtime-config` 使用同一个判断条件：
`AUTH_MODE=mock`。前端从运行时配置得到 `authMode=mock` 后继续使用现有固定用户
引导流程，不新增前端环境变量。

推荐的本地配置为：

```env
ENVIRONMENT=development
AUTH_MODE=mock
```

生产配置继续使用：

```env
ENVIRONMENT=production
AUTH_MODE=company
```

## 兼容性

已有环境中的 `AUTH_MOCK_ENABLED` 将成为无效的旧配置。由于 Settings 当前允许
忽略额外环境变量，旧变量短期残留不会阻止启动，但文档和模板应删除它，避免继续
误导使用者。

这是一项有意的行为变更：非生产环境只要配置 `AUTH_MODE=mock` 就会真正启用 Mock
身份，不再要求额外确认开关。

## 测试范围

- 非生产环境下 `AUTH_MODE=mock` 能构建配置并返回 Mock 运行时配置。
- Mock 请求无需公司令牌即可得到固定身份。
- `ENVIRONMENT=production` 与 `AUTH_MODE=mock` 的组合拒绝启动。
- `AUTH_MODE=company` 的公司鉴权、中间件信任边界和前端运行时配置保持通过。
- 配置模板和相关测试不再引用 `AUTH_MOCK_ENABLED`。

## 非目标

- 不改变 Mock 用户的账号、角色或管理员判定方式。
- 不改变生产环境定义或其他开发/生产配置。
- 不改变公司认证平台协议、网关信任边界和会话归属规则。
