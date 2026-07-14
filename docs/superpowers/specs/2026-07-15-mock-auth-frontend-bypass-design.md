# Mock 鉴权模式前端免登录设计

## 背景与目标

后端已经支持 `AUTH_MODE=mock` 与 `AUTH_MOCK_ENABLED=true`：请求不需要
Bearer Token，后端会为每个受保护请求注入固定开发用户。但前端目前始终安装公司
登录路由守卫，启动时还会尝试调用公司 `getCurrentUser`，因此仅切换后端配置仍不能
直接进入业务页面。

本改动的目标是让后端成为鉴权模式的唯一配置源：开发环境启用 Mock 鉴权并重启
后端后，前端自动识别该模式、初始化固定开发用户并直接进入业务页面。公司认证模式
的登录、会话恢复、退出和请求头行为保持不变。

Mock 模式统一使用现有稳定用户 ID `local-developer`，并默认赋予管理员身份。所有
开发人员和历史会话继续归属于同一个本地用户，避免因为自动生成用户或切换管理员
账号造成会话列表、资源所有者和用户管理数据分叉。

## 范围

包含：

- 提供不含敏感信息的公开鉴权运行时配置接口。
- 前端挂载路由守卫前加载运行时配置。
- Mock 模式下建立仅存在于内存中的固定管理员会话。
- 保持公司模式和生产环境的现有安全校验。
- 为后端接口、前端会话和路由行为增加回归测试。

不包含：

- 取消后端鉴权中间件。
- 在生产环境允许 Mock 鉴权。
- 新增完整的 RBAC 或修改现有资源权限。
- 将 Mock Token 或 Mock 用户持久化到浏览器存储。

## 方案选择

采用后端 JSON 运行时配置接口，而不是 `VITE_AUTH_MODE` 或 Nginx 动态生成 JS。
JSON 接口可以复用现有 `/api/suyuan/**` 业务代理，在 Vite 开发环境和 Nginx 部署中
行为一致，同时避免前后端重复配置。

## 后端设计

新增公开接口：

```text
GET /api/auth/runtime-config
```

网关外部地址为：

```text
GET /api/suyuan/auth/runtime-config
```

鉴权中间件将内部路径 `/api/auth/runtime-config` 加入精确白名单。接口只返回前端
选择认证流程所需的非敏感字段，并设置 `Cache-Control: no-store`，防止环境切换后
浏览器继续使用旧模式。

公司模式响应：

```json
{
  "authMode": "company",
  "sysCode": "SUYUAN"
}
```

Mock 模式响应：

```json
{
  "authMode": "mock",
  "sysCode": "SUYUAN",
  "mockUser": {
    "id": "local-developer",
    "userName": "local-developer",
    "name": "本地开发用户",
    "roleCodes": ["SUYUAN_ADMIN"],
    "isAdmin": true,
    "sysCode": "SUYUAN",
    "authSource": "mock"
  }
}
```

Mock 模式的用户 ID 默认并持续使用 `local-developer`；不生成随机用户，也不因为
浏览器或进程变化创建新身份。Mock 身份始终包含保留角色 `SUYUAN_ADMIN`，并设置
`isAdmin=true`。`AUTH_MOCK_ROLE_CODES` 可以追加其他测试角色，但不能移除 Mock
管理员身份。运行时配置与后端 `AuthenticationService` 复用同一个 Mock 用户构造
逻辑，避免前端展示身份与业务后端实际注入身份不一致。

`AUTH_MOCK_USER_ID` 仍保留为显式覆盖能力，但默认值不改。部署者只有在接受历史
会话和资源归属切换到新用户的情况下才应覆盖它。

接口不返回认证服务地址、Token、密钥、可信网段或其他部署配置。现有生产配置校验
继续拒绝 `AUTH_MODE=mock` 或 `AUTH_MOCK_ENABLED=true`。

## 前端启动与会话设计

新增独立的运行时配置加载模块。应用启动顺序调整为：

1. 创建 Vue 应用和 Pinia。
2. 请求 `/api/suyuan/auth/runtime-config`，请求使用 `cache: no-store`，且不携带
   Authorization。
3. 将运行时配置交给鉴权 Store。
4. 安装现有路由守卫和路由。
5. 挂载应用。

如果配置请求失败、响应格式错误或返回未知模式，前端回退到 `company`，继续走现有
登录流程。这是安全失败策略，不能因为配置服务异常而意外免登录。

鉴权会话增加 `authMode` 和可选 `mockUser`：

- `company`：保持现有行为，Token 与用户从浏览器存储恢复，并通过公司接口校验。
- `mock`：启动时清除遗留的公司会话存储，以免后续业务请求意外携带旧 Token；
  `bootstrap()` 直接使用运行时配置中的固定管理员 `mockUser`，不调用公司认证
  API。
- Mock 用户和 Mock 状态只保存在 Pinia/会话内存中，不写入 `localStorage`。
- `isAuthenticated` 在公司模式要求 `token + user`，在 Mock 模式只要求有效的
  `mockUser`。
- Mock 模式调用 `login()` 不发送公司登录请求，直接返回开发用户。
- Mock 模式调用 `logout()` 不发送公司退出请求，并保持开发用户会话；开发模式没有
  可进入的登录态退出目标。

业务请求继续通过现有 `authFetch`/`authAxios` 发送 `SysCode: SUYUAN`。因为 Mock
启动时已清除本地 Token，请求不会携带 Bearer Token；后端 Mock 中间件仍会注入
固定用户。公司模式的请求头逻辑不变。

## 路由行为

现有全局路由守卫继续保留：

- Mock 模式的首次导航调用本地 `bootstrap()` 后立即视为已认证，直接进入目标业务
  页面。
- 访问 `/login` 时，由于 Mock 用户已认证，重定向到安全的本地目标或首页。
- 公司模式仍在无有效 Token 时重定向到 `/login`。

保留守卫而不是完全跳过它，可以维持统一的安全跳转处理，并避免其他代码将 Mock
模式误判为“没有当前用户”。

## 错误处理

- 运行时配置不可用或非法：回退公司模式。
- Mock 配置缺少有效用户 ID：视为非法配置并回退公司模式。
- 后端处于 Mock 模式但前端配置请求失败：前端显示公司登录页；不会静默绕过。
- 后端拒绝不安全的生产 Mock 配置：保持现有启动失败行为。

## 测试策略

后端测试：

- 公司模式只返回 `authMode` 与 `sysCode`。
- Mock 模式返回与认证服务一致的固定用户、角色和管理员标志。
- Mock 模式在未额外配置角色时仍返回用户 ID `local-developer`、角色
  `SUYUAN_ADMIN` 和 `isAdmin=true`。
- 运行时配置路径不需要 Bearer Token。
- 响应不包含认证服务地址、Token 或密钥，并带有 `Cache-Control: no-store`。

前端测试：

- Mock 会话启动时不调用公司认证 API、不写入 Mock Token，并清除旧公司会话。
- Mock 会话可直接通过现有业务路由守卫。
- Mock 登录和退出不调用公司认证 API。
- 公司模式继续恢复 Token、校验当前用户并在无会话时进入登录页。
- 运行时配置加载失败、非法或未知模式时回退公司模式。

验证命令：

```bash
cd /home/xckj/suyuan/frontend
npm run test:auth
npm run build:standalone

cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth tests/integration/test_gateway_auth_flow.py
```

## 验收标准

- 开发环境只设置后端 `AUTH_MODE=mock`、`AUTH_MOCK_ENABLED=true` 并重启相关服务后，
  浏览器访问任意业务页面不显示登录页，也不请求公司登录或当前用户接口。
- 业务后端收到的当前用户与 Mock 配置一致，默认用户 ID 为 `local-developer`，角色
  包含 `SUYUAN_ADMIN` 且 `is_admin=true`。
- 同一 Mock 环境重启或浏览器重新访问后仍使用相同用户 ID，已有会话和资源归属不
  产生新的用户分支。
- 切回 `AUTH_MODE=company` 后，现有公司登录流程恢复且无行为回归。
- 生产环境无法启用 Mock 鉴权。
