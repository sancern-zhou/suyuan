# 广东项目本地部署说明（Windows / M 盘）

- 部署位置：`M:\suyuan-guangdong`（分支 `project/guangdong`，含完整 git 历史）
- 运行时位置：`M:\suyuan-tools`（Node.js v22.23.4 便携版、Python 3.11.9、backend_py311 虚拟环境）
- 原始克隆（开发用）：`C:\Users\Administrator\.zcode\workspace\draft-f7a71490-1877-447e-a511-279773a49164\suyuan`
- git：`C:\Users\Administrator\Tools\PortableGit\bin\git.exe`

## 组件与端口（全部为 Windows 服务，开机自启、崩溃自动重启）

| 组件 | 端口 | 服务名 |
|------|------|--------|
| 统一入口网关（nginx） | 8092 | `suyuan-gateway-8092` |
| 后端 web (uvicorn，3 workers) | 8000 | `suyuan-web` |
| 后端 worker（须与 web 成对启动） | 内部 8011 | `suyuan-worker` |
| 独立 bge-m3 嵌入服务（web/worker 共享一份权重） | 8020 | `suyuan-embedding` |
| 前端静态服务 + 反向代理 | 5176 | `suyuan-frontend` |
| Redis | 6379 | `suyuan-redis` |
| PostgreSQL（会话库） | 5433 | `suyuan-pgsql` |
| Qdrant（本地向量库） | 6334 | `suyuan-qdrant` |

web/worker 服务声明依赖 `suyuan-embedding`（WinSW `<depend>`），开机自启时嵌入服务先起；`.env.guangdong` 的 `EMBEDDING_SERVICE_URL=http://127.0.0.1:8020` 使两者走远程嵌入，不再各自加载约 1G 的 bge-m3 权重，web 多开 worker 不受模型内存约束。

常用操作：

```bat
net start suyuan-web      & net start suyuan-worker & net start suyuan-frontend   :: 启动
net stop suyuan-worker    & net stop suyuan-web     & net stop suyuan-frontend   :: 停止
deploy-local\start-web.bat / stop-all.bat（内部即上述命令）
```

服务配置（WinSW）位于 `M:\suyuan-tools\winsvcs\`，修改 `.env` 后需 `net stop/start suyuan-web`、`suyuan-worker` 生效。

## 统一入口网关（8092，公网 113.108.142.147:8093）

防火墙把公网 `113.108.142.147:8093` 映射到本机 `8092`。原运维平台（IIS `Operation` 站点，ASP.NET）独占了该入口；2026-10-27 起改为 nginx 统一分流，两个平台共用一个公网地址：

| 公网地址 | 后端 |
|---|---|
| `http://113.108.142.147:8093/` | 运维平台（IIS `Operation` 站点，绑定已从 8092 改为 **8094**） |
| `http://113.108.142.147:8093/suyuan/` | 智能体平台（`suyuan-frontend` :5176，内部再分流静态/API/认证/WS） |

- nginx 配置：`deploy-local\nginx-8092\conf\nginx.conf`（独立实例，与 `L:\nginx` 默认实例互不影响；`/suyuan/` 已关闭缓冲并放通 WebSocket，保证对话 SSE 流式输出）。改配置后 `deploy-local\stop-gateway-8092.bat && deploy-local\start-gateway-8092.bat`，或 `net stop/start suyuan-gateway-8092`。
- **禁止**把 IIS `Operation` 站点绑定改回 8092（与网关冲突）。网关停止期间，运维平台在内网仍可经 `:8094` 直达。
- 运维平台经网关后响应头会带 `Server: nginx`，ASP.NET 相关头（`X-Powered-By: Suncereltd` 等）原样透传，属预期。
- **安全现状**：~~`.env.guangdong` 为 `AUTH_MODE=mock`~~ **2026-10-27 已切换为 `AUTH_MODE=operation`（复用运维平台登录）**，详见下一节。

## 运维平台单点登录（AUTH_MODE=operation，2026-10-27）

智能体平台复用本机运维平台（IIS `Operation` 站点，ASP.NET Forms 认证，cookie 名 `GDOperation`，120 分钟超时）的登录态，用户登录运维平台后访问智能体页面免登：

```
浏览器（GDOperation cookie，同源自动携带）
  └─> 智能体前端 POST /suyuan/api/suyuan/auth/operation-session
        └─> 后端 app/auth/operation_client.py 携带 cookie 服务端调用
              http://127.0.0.1:8094/AuthWhoAmI.aspx  （M:\suncereltd\Operation\AuthWhoAmI.aspx）
        └─> 200 {"authenticated":true,"userName":"..."} → CurrentUser(id=ops-<用户名>, auth_source=operation)
```

- **运维平台侧唯一改动**：新增 `M:\suncereltd\Operation\AuthWhoAmI.aspx`（纯增量文件，只读回显 `Request.IsAuthenticated` 与 `User.Identity.Name`；无 cookie/伪 cookie 被 Forms 认证 302 到登录页）。删除该文件即解除集成，运维平台代码零改动。
- **后端**：`AUTH_MODE=operation` + `AUTH_OPERATION_VALIDATE_URL` / `AUTH_OPERATION_COOKIE_NAME` / `AUTH_OPERATION_ADMIN_USERNAMES`（逗号分隔的运维用户名视为管理员）。中间件默认拒绝，凭 cookie 走 Oracle 校验，Redis 缓存 60 秒（`AUTH_IDENTITY_CACHE_TTL_SECONDS`）。
- **智能体会话令牌（2026-10-28 增加，解决运维平台登录态短命问题）**：运维平台自身登录态很短（进程内 Session 未配置、默认 20 分钟；Forms cookie 为非持久化会话 cookie；平台内部还会主动失效），实测空闲约 20–30 分钟就要求重登。因此智能体在**每次运维 cookie 校验成功后额外签发一枚 HMAC 会话令牌**（`AUTH_SESSION_TOKEN_SECRET`，TTL `AUTH_SESSION_TOKEN_TTL_SECONDS`，默认 28800 秒 = 8 小时），浏览器存 localStorage，所有 API 请求自动以 `Authorization: Bearer` 携带；中间件**优先验证令牌**（本地验签，不再问运维平台），令牌失效后才回退到运维 cookie 走 Oracle。每次打开/刷新智能体页面会续发新令牌（滑动续期）。
  - 安全权衡：令牌有效期内即使运维平台会话已退出，智能体仍可用。需要严格跟随运维会话时把 `AUTH_SESSION_TOKEN_TTL_SECONDS=0`（回退为每个请求都校验运维 cookie），或调小 TTL。
  - 令牌路径已验证：有效令牌 200、过期/篡改 401、无凭证 401，公网链路同验；后端测试 `tests/auth/test_session_tokens.py` 6 项。
- **前端**：`runtime-config` 返回 `authMode=operation`；静默换取会话，失败/未登录时整窗跳转运维平台登录页 `/Home/LogOn?ReturnUrl=<当前路径>`（iframe 内会用 `window.top` 跳出）。前端测试 `npm run test:auth` 35 项全过。
- **验证**：无 cookie/伪 cookie 时 runtime-config 200、`operation-session` 401（经 Oracle 真实拒绝）、业务 API 401。**正向路径（运维登录→免登进入智能体）需用真实运维账号在浏览器验证。**
- **角色映射**：运维平台角色不同步，统一为 `SUYUAN_USER`；`AUTH_OPERATION_ADMIN_USERNAMES` 中列出的用户名授予 `SUYUAN_ADMIN`。
- **运维单位访问白名单（2026-10-30 增加）**：`AUTH_OPERATION_ACCESS_CONTROL_ENABLED=true` 时，worker/web 每 `AUTH_OPERATION_ACCESS_SYNC_INTERVAL_SECONDS`（默认 300 秒）从运维平台库（`OPS_SQLSERVER_*` 指向的 `Operation_SC_GD`@172.20.105.179）同步 `SYS_USER`+`SYS_DEPARTMENT`+`SYS_USERROLE/SYS_ROLE/SYS_ROLETYPE` 名册（含登录名、姓名、用户类型、部门、运维单位、角色名），快照落盘 `backend_data_registry\operation_access\roster.json`。判定规则（白名单制）：`AUTH_OPERATION_ALLOWED_USERTYPES`（默认 `1,5` = 省中心/市级 局方账号）放行；`AUTH_OPERATION_ALLOWED_USERNAMES`（逗号分隔）与 admin 用户名无条件放行；`AUTH_OPERATION_BLOCKED_USERNAMES` 无条件拒绝；其余用户类型（2=技术支持、3=运维单位、4=现场检查、6=数据复审）及名册同步成功后的未知账号一律拒绝（403 `operation_account_blocked`，前端显示 `/suyuan/access-denied` 无权限页，不跳回运维登录页）。拦截在网关中间件按请求生效，**8 小时会话令牌不能绕过**；名册从未同步成功时（冷启动且运维库不可达）暂时放行并告警。重复登录名与同名冲突的取值规则：登录名优先于显示名别名（显示名撞他人登录名时不得覆盖真实账户）；同一登录名有多条 `SYS_USER` 记录时按记录活性取活账户（`DATASTATE=1` → `STATUS=Enabled` → 局方类型），避免取到失效/已禁用的旧记录。管理员可用 admin 账号查 `GET /api/suyuan/auth/operation-access` 核对名册与判定。后端测试 `tests/auth/test_operation_access.py` 20 项。
- 切回 mock/company：改 `.env.guangdong` 的 `AUTH_MODE` 并 `net stop/start suyuan-web suyuan-worker`。company 模式依赖 10.10.204.80:8025（当前本机不可达）。
- 页面嵌入运维平台：运维平台菜单是数据库驱动的，可在其菜单管理里添加指向 `/suyuan/` 的条目（同源 iframe，cookie 自动携带），或直接把 `http://113.108.142.147:8093/suyuan/` 作为入口链接分发。

## 启动前必须完成的配置（`backend\.env.guangdong`）

部署已完成代码、依赖和构建，但以下外部依赖需要真实凭据/服务才能完整工作：

1. **LLM API Key** [必填]：`DOUBAO_API_KEY`（或改用其他 provider）
2. **PostgreSQL** [必填]：`DATABASE_URL` 当前指向 `localhost:5432`，本机尚未安装 PostgreSQL，需安装或指向现有库
3. **Qdrant** [必填]：本地知识库向量服务 `localhost:6334`，尚未安装
4. **Redis** [可选]：`localhost:6379`，未配置时部分接口（cancel/steer 跨进程）不可用
5. **广东数据源凭据**：`GD_SUNCERE_API_USERNAME` / `GD_SUNCERE_API_PASSWORD`
6. **公司认证网关**：`AUTH_SERVICE_URL=http://10.10.204.80:8025`（内网地址，确认本机可达）

## 与标准部署的差异（Windows 本地版）

- `requirements.windows.txt`：将 `python-dateutil==2.9.0` 调整为 `2.9.0.post0`（原版本与 htmldate 依赖冲突，pip 无法解析）。更新代码后如重新安装依赖请使用此文件。
- 前端通过 `frontend\.env.standalone.local`（`PROJECT=guangdong`）注入项目标识构建，不改动 git 跟踪的 `.env.standalone`。
- `deploy-local\serve-frontend.mjs` 替代 Linux 部署中的 nginx 容器：静态资源 + `/suyuan/api/suyuan` → `:8000/api` 反向代理 + WebSocket 转发。
- `.env.guangdong` 中 `NACOS_REGISTER_ENABLED=false`：本地部署不向公司内网 Nacos 注册。
- ~~`ENABLE_AUTO_FETCHING=False`~~：`.env.guangdong` 实际未设置该变量（默认 `true`），fetcher 调度器运行中（`/api/fetchers/status` → `scheduler_running:true`，当前 38 个 fetcher；未配置凭据的许昌等外部 fetcher 会周期性报错，属预期噪音）。
- **LibreOffice 26.8.1** 已安装（`C:\Program Files\LibreOffice`）：站点运行日报的 PDF 渲染依赖 `soffice`，缺失时日报工作流在 render_pdf 阶段失败（WinError 2）。
- **Quarto 1.10.19** 已安装（`C:\Program Files\Quarto\bin`）：`render_report_package`（工单月报 docx/html 渲染）依赖 `quarto` CLI，缺失时报告包只有 report.qmd 无渲染产物。安装后需重启 web+worker 服务使进程 PATH 生效。
- **bge-m3 本地模型**：`backend\models\bge-m3-model\`（自 hf-mirror.com 下载）。由独立嵌入服务 `suyuan-embedding`（127.0.0.1:8020，启动即加载，`M:\suyuan-tools\winsvcs\suyuan-embedding\`）持有全机唯一一份权重；web/worker 经 `EMBEDDING_SERVICE_URL` 远程调用，仅在嵌入服务不可用回退时才各自加载。
- **本地 Qdrant**（Windows 服务 `suyuan-qdrant`，`M:\suyuan-tools\winsvcs\suyuan-qdrant\`）：HTTP 127.0.0.1:6334（gRPC 6335），存储 `M:\suyuan-tools\qdrant\storage`。知识库 `vector_store_scope=local` 走 `LOCAL_QDRANT_*`。中心 Qdrant（`180.184.30.94:6333`）当前对创建集合等写请求重置连接（读正常），新建知识库须用 `local` scope。

## 更新代码

```bat
cd /d M:\suyuan-guangdong
C:\Users\Administrator\Tools\PortableGit\bin\git.exe pull
cd frontend && set PATH=M:\suyuan-tools\node;%PATH% && call npm run build:standalone
deploy-local\stop-all.bat && deploy-local\start-web.bat && deploy-local\start-worker.bat && deploy-local\start-frontend.bat
```
