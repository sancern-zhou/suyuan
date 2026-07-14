# Suyuan 网关鉴权设计

## 1. 背景与目标

Suyuan 当前由 Vue 3 前端和 FastAPI 后端组成。后端尚未接入 Nacos，也没有统一的入口鉴权中间件；部分知识库接口直接读取浏览器可控的 `X-User-Id` 和 `X-Is-Admin`，不能作为可信身份来源。前端请求也没有统一注入公司 Bearer Token。

公司公共架构位于同级 `NormCraftAI` 仓库。该架构确认了以下约定：

- 公司前端使用 `Authorization: Bearer <token>` 和 `SysCode` 请求头。
- 登录接口为 `/auth/token/authentication`，当前用户接口为 `/auth/account/getCurrentUser`，登出接口为 `/auth/token/logout`。
- 登录参数使用公司公共包的 SM2/SM4 加密与 `Sign` 签名协议。
- 后端服务通过 Nacos 注册并由平台网关发现。
- 测试环境使用 Nacos Namespace `normcraft-ai` 和 Group `DEFAULT_GROUP`。

本设计支持两种入口，但只使用一套公司身份：

1. 用户访问 Suyuan 独立登录页，使用公司统一账号登录。
2. 用户从公司既有平台进入同域部署的 Suyuan 页面，复用平台登录态。

两个入口的所有生产 API 请求都必须经过 `platform-gateway`。Suyuan 不创建本地账号体系，也不签发自己的长期登录 Token。

## 2. 已确认标识与边界

| 项目 | 值 |
| --- | --- |
| SysCode | `SUYUAN` |
| Nacos Namespace | `normcraft-ai` |
| Nacos Group | `DEFAULT_GROUP` |
| Nacos ServiceName | `suyuan-agent` |
| 外部 API 前缀 | `/api/suyuan` |
| Redis key 前缀 | `suyuan:auth:` |
| 生产入口 | 仅 `platform-gateway` |
| 默认访问策略 | 业务接口默认要求认证，显式白名单除外 |

本次范围包括登录适配、Token 传递、当前用户解析、Nacos 注册、Redis 身份缓存、HTTP/SSE/WebSocket 鉴权、已有权限接口迁移、异常处理和验证。范围不包括自建用户表、自建密码认证、签发独立 JWT、重新实现公司认证中心，以及与网关鉴权无关的业务权限重构。

## 3. 方案选择

### 3.1 选定方案

保留现有 Vue 3 与 FastAPI 技术栈，实现轻量公司认证适配层。

不直接引入完整的 `@suncereltd/suncere-sys`，因为该公共包基于 Vue 2，与当前 Vue 3 应用不兼容。Suyuan 只复用其认证协议、标准存储键和请求头约定。将来认证中心支持标准 OIDC/SSO 回调后，可以新增重定向式 Provider，而不改变业务 API 的身份模型。

### 3.2 未选方案

- 整体迁移到公司 Vue 2 平台壳：兼容性最直接，但会导致前端大规模倒退和重构。
- Suyuan 自建账号与 Token：会形成重复身份源，增加账号同步和安全风险。
- 首期只做 SSO 重定向：当前公共仓库未给出可验证的 SSO 回调协议，无法作为首期交付依据。

## 4. 总体架构

### 4.1 前端认证适配层

新增 Vue 3 认证适配层，对页面和业务请求暴露稳定接口：

- `resolveSession()`：从公司标准同域存储读取 `Access-Token`，并加载当前用户。
- `login(credentials)`：按公共包 2.1.4 的 SM2/SM4 与 `Sign` 协议调用统一认证中心。
- `logout()`：调用统一登出接口并清理标准登录存储。
- `getAccessToken()`：只向统一请求客户端提供 Token，不向业务组件传播密码或认证协议细节。
- `getCurrentUser()`：返回规范化用户对象。

独立入口没有有效 Token 时显示 Suyuan 登录页；平台入口在同域环境中读取公司标准登录态。两种入口取得 Token 后使用完全相同的请求客户端和后端鉴权路径。

前端业务请求统一添加：

```text
Authorization: Bearer <company-access-token>
SysCode: SUYUAN
```

前端不再发送 `X-User-Id` 或 `X-Is-Admin`。收到 `401` 时清理失效登录态并进入登录页；收到 `403` 时保留登录态并展示无权限提示。

### 4.2 平台网关

平台网关负责：

1. 校验公司 Token。
2. 删除客户端提供的身份类请求头，包括 `X-User-Id`、`X-Is-Admin` 以及后续定义的内部身份头。
3. 将 `/api/suyuan/**` 路由到 Nacos 服务 `suyuan-agent`。
4. 保留 `Authorization`、`SysCode`、请求 ID 和链路追踪头。
5. 对入口执行公司统一的限流、跨域和请求体限制策略。

现有 FastAPI 路由前缀并不统一。首期由网关兼容性重写维护外部 `/api/suyuan/**` 与现有内部路径之间的明确映射，避免大规模修改业务路由。新增接口一律使用统一外部前缀。兼容映射必须形成可测试的静态规则，不能用模糊的任意路径猜测。

测试环境当前可从 Nacos 看到健康的 `platform-gateway`、`platform-authentication` 和 `normcraft-ai-base` 实例，但直接访问公共前端包声明的认证路径返回 `404`。因此，认证路由映射是实施验收的基础设施前置条件：未配置成功时，独立登录不得标记为完成。

### 4.3 FastAPI 鉴权中间件

新增统一鉴权中间件和依赖注入模型。中间件默认保护业务路由，并执行以下流程：

1. 判断请求是否命中显式白名单。
2. 读取 Bearer Token；缺失时返回 `401`。
3. 对 Token 做不可逆摘要，使用摘要查询 Redis 身份缓存。
4. 缓存未命中时，携带原 Token 调用公司当前用户接口。
5. 将认证中心结果映射为 `CurrentUser`，写入 `request.state`。
6. 路由通过依赖注入取得 `CurrentUser`，不再自行解析浏览器身份头。

统一身份模型至少包含：

```text
id
username
display_name
role_codes
is_admin
sys_code
auth_source
```

`is_admin` 只能由认证中心返回的角色代码与环境配置的管理员角色允许列表求交集得出。未配置允许列表或没有匹配角色时一律为 `false`，不得根据前端布尔值推断管理员身份。

### 4.4 认证中心适配器

FastAPI 通过独立适配器调用公司认证中心，避免业务代码依赖具体报文。适配器负责：

- 携带原始 Bearer Token 请求当前用户接口。
- 将公司响应包装和字段命名转换为 `CurrentUser`。
- 将认证拒绝映射为 `401`。
- 将认证中心超时或不可用映射为 `503`。
- 对响应字段做严格校验，缺少用户主键时拒绝建立身份。

适配器的认证服务地址必须来自环境配置或 Nacos 服务发现，不得在业务代码中硬编码。浏览器登录和后端当前用户查询可以使用不同的内部/外部基地址，但必须复用同一公司认证源。

### 4.5 Redis

Redis 使用现有配置模型，并在测试环境指向库 10。认证相关键统一使用 `suyuan:auth:` 前缀。

Redis 只保存：

- Token 不可逆摘要到规范化用户资料的短期缓存。
- WebSocket 一次性 ticket。
- 后续认证中心明确支持时使用的撤销或会话失效标记。

Redis 不保存明文密码、完整 Token 或前端加密前的登录参数。身份缓存 TTL 取“配置上限”和“Token 剩余有效期”中的较小值；无法可靠取得 Token 到期时间时使用较短的配置上限。登出后即使没有撤销事件，短 TTL 也限制陈旧身份的存活时间。

## 5. 请求数据流

### 5.1 独立登录入口

1. 用户访问 Suyuan。
2. 前端没有发现有效的 `Access-Token`，显示独立登录页。
3. 登录页按公司公共包协议加密和签名登录参数。
4. 请求经平台网关到统一认证中心。
5. 登录成功后保存公司 `accessToken`，再获取当前用户。
6. 前端进入 Suyuan 页面，后续业务请求统一访问 `/api/suyuan/**`。

### 5.2 公司平台入口

1. 用户已在公司平台登录。
2. Suyuan 作为同域子路径加载。
3. 前端认证适配层读取公司标准 `Access-Token`。
4. 前端获取当前用户并进入页面。
5. 后续业务请求与独立入口完全一致。

同域共享只读取公司定义的认证键。Suyuan 不扫描或复制无关 localStorage/sessionStorage 内容。

### 5.3 普通 HTTP 与 SSE

普通 HTTP 和基于 `fetch` 的 SSE 请求都携带 Bearer Token。平台网关完成入口校验并路由，FastAPI 建立 `CurrentUser` 后再调用业务处理器。

任何业务接口需要用户 ID、所有者或管理员身份时，必须从 `CurrentUser` 获取。现有知识库、知识图谱和知识场景接口中直接读取 `X-User-Id`、`X-Is-Admin` 的位置应迁移到该依赖。

### 5.4 WebSocket

浏览器 WebSocket API 不能可靠设置自定义 Authorization 请求头，因此不把长期 Token 放入查询字符串。连接流程为：

1. 前端通过已认证 HTTP 请求申请 WebSocket ticket。
2. 后端在 Redis 写入随机、高熵、短 TTL、单次使用的 ticket，并绑定用户 ID 和目标用途。
3. 前端使用 ticket 建立 WebSocket。
4. 后端原子消费 ticket；不存在、过期、用途不符或已使用时拒绝连接。
5. 消费成功后将 ticket 绑定的 `CurrentUser` 放入 WebSocket 会话上下文。

ticket 不得复用，不得写入普通访问日志，且不能用于普通 HTTP API。

### 5.5 登出

前端调用公司统一登出接口，清除标准认证存储和本地用户状态。认证身份缓存依靠短 TTL 收敛；如果公司认证中心提供可靠的注销事件或撤销查询，再通过适配器增加主动失效，不改变业务层接口。

## 6. 白名单与默认拒绝

默认所有业务接口都要求认证。首期白名单仅包括：

- 存活和就绪健康检查。
- 应用启动所必需的静态资源。
- 已有带独立短期签名且只返回签名限定资源的媒体/报告/HTML 分享接口。
- 平台完成认证所必需、且实际由认证服务处理的登录相关路由。

Swagger/OpenAPI 是否对测试环境开放由显式配置控制；生产默认不匿名开放。白名单使用精确路径或受限路径模板，禁止用宽泛的 `/api/*`、`/share/*` 规则。

## 7. Nacos 生命周期

FastAPI 启动时注册：

```text
Namespace: normcraft-ai
Group: DEFAULT_GROUP
ServiceName: suyuan-agent
Cluster: DEFAULT
Enabled: true
Healthy: true
```

注册实例的 IP、端口和 metadata 从部署环境读取。服务运行期间维持心跳，正常关闭时注销实例。

当 `RegisterEnabled=true` 时：

- 生产环境注册或心跳初始化失败，应用启动失败。
- 非生产环境记录明确错误；只有显式关闭注册时才允许本地离线启动。

就绪检查必须区分“进程存活”和“可通过网关提供服务”。生产就绪状态应反映 Nacos 注册、认证依赖和必要数据库状态。

## 8. 配置与密钥管理

新增配置按现有 Pydantic Settings 方式从环境变量读取，覆盖以下类别：

- `AUTH_MODE`：公司认证或开发模拟身份。
- `AUTH_SERVICE_URL`、当前用户路径、登录路径和登出路径。
- `AUTH_ADMIN_ROLE_CODES`。
- `AUTH_IDENTITY_CACHE_TTL_SECONDS`。
- `AUTH_MOCK_ENABLED` 与模拟用户字段。
- `NACOS_SERVER_ADDRESSES`、Namespace、Group、ServiceName、实例 IP/端口、注册开关和账号引用。
- Redis 主机、端口、库号、密码引用和认证 key 前缀。
- 网关外部前缀和可信代理网络范围。

测试环境地址可以进入环境模板，但密码、Token 和签名私钥不得提交到 Git。生产环境检测到开发模拟身份、空认证配置或宽泛可信代理范围时必须拒绝启动。

## 9. 异常与安全策略

| 场景 | 行为 |
| --- | --- |
| 缺少或无效 Token | `401`，前端清理登录态并进入登录页 |
| Token 有效但权限不足 | `403`，保留登录态 |
| 认证中心不可用且缓存未命中 | `503`，不得降级为匿名身份 |
| Redis 不可用 | HTTP 临时直连认证中心；WebSocket ticket 返回 `503` |
| 生产 Nacos 注册失败 | 启动失败 |
| 生产启用模拟身份 | 启动失败 |
| 用户身份响应缺少主键 | `401`，不建立身份 |

日志只记录请求 ID、用户 ID、Token 摘要的短前缀和结构化失败类型。不得记录密码、完整 Token、Nacos/Redis 密码、登录加密前参数或完整认证响应。

后端部署端口应只允许平台网关和受控运维网络访问。应用层鉴权不能替代网络层的入口限制。

## 10. 测试设计

### 10.1 单元测试

- 精确白名单与默认拒绝。
- Bearer Token 缺失、格式错误和认证拒绝。
- 公司用户响应到 `CurrentUser` 的映射。
- 管理员角色允许列表，验证客户端 `X-Is-Admin` 无效。
- Redis 身份缓存命中、过期、不可用和不保存完整 Token。
- 生产环境免登录保护。
- WebSocket ticket 的绑定、过期、用途校验和单次原子消费。
- Nacos 注册失败及关闭注册两种启动策略。

### 10.2 集成测试

- 使用模拟认证中心与 Redis 验证独立登录后的完整 API 请求。
- 使用预置公司 Token 验证同域平台入口。
- HTTP、SSE 与 WebSocket 都能获得同一用户身份。
- 知识库、知识图谱和知识场景接口不能通过伪造身份头越权。
- `401`、`403`、`503` 的前后端行为符合约定。
- 现有签名分享链接只访问签名限定资源。

### 10.3 真实环境验收

1. Nacos 中出现健康的 `suyuan-agent` 实例，信息与部署 IP/端口一致。
2. 网关 `/api/suyuan/**` 能正确路由所有纳入范围的现有接口。
3. 网关认证路由可访问公司登录、当前用户和登出接口。
4. 使用公司测试账号完成独立登录。
5. 从公司平台同域入口复用登录态进入 Suyuan。
6. 普通用户越权得到 `403`，过期 Token 得到 `401`。
7. SSE 和 WebSocket 在认证后可用，WebSocket ticket 无法复用。
8. Redis 短暂不可用时 HTTP 按设计降级，WebSocket ticket 明确返回 `503`。
9. 日志中不存在密码或完整 Token。

没有公司测试账号或网关认证路由仍返回 `404` 时，应将对应真实环境验收项标记为基础设施阻塞，不能宣称网关鉴权完整交付。

## 11. 成功标准

- 独立入口和平台入口使用同一公司身份，业务代码无需判断入口来源。
- 所有生产业务请求经平台网关进入 `suyuan-agent`。
- 浏览器无法通过伪造身份头获得其他用户或管理员权限。
- HTTP、SSE 和 WebSocket 具有一致、可测试的身份语义。
- 本地开发可显式使用模拟身份，生产环境无法误启免登录。
- Nacos、Redis、认证中心和网关故障均采用明确的失败策略，不静默降级为匿名访问。
- 现有业务功能在完成身份依赖迁移后通过回归测试。
