# APP 公司平台同源鉴权（OIDC）接入契约与账号体系迁移

2026-11-26 定版。目标：APP 端登录与 Web 端使用同一公司平台认证源，web 改密码后 APP 下次登录自动生效；后台按平台 userId 自动关联 web 与 APP 的用户资产（会话、推送、记忆）。

## 一、现状与过渡措施（已生效）

- APP 静态账号（`APP_ACCOUNTS_JSON`，`.env`）与公司平台是两套独立口令，web 改密不同步。
- **过渡措施（2026-11-26 已部署）**：`APP_REFRESH_TOKEN_TTL_SECONDS=31536000`（1 年，schema 上限）。`/api/social/app/auth/refresh` 刷新时**不校验静态密码**，且每次刷新换发全新 1 年 refresh token——已登录设备只要一年内用过一次即无限续期，web 改密不影响在用设备。
- 该措施只救存量登录；新设备首次登录仍需静态密码，治本靠下述 OIDC。

## 二、OIDC 登录流程（Authorization Code + PKCE）

后端链路已实现并测试通过（`app/social/company_oauth.py`、`app/api/social_app_routes.py`），等待平台侧注册 client_id 后即可启用。

```
APP                                     后端                          公司平台
 │  GET /api/social/app/auth/oidc/config │                              │
 │──────────────────────────────────────>│  (返回 authorize 端点等配置)  │
 │                                        │                              │
 │  WebView/Custom Tab 打开 authorization_endpoint                      │
 │  参数: client_id / redirect_uri / response_type=code                  │
 │       scope / code_challenge(S256) / code_challenge_method=S256      │
 │──────────────────────────────────────────────────────────────────────>│
 │  用户在平台页面输入账号密码（与 web 相同）登录                          │
 │<─ 302 redirect_uri#code=... (com.suyuan.mobile://oauth/callback) ────│
 │                                        │                              │
 │  POST /api/social/app/auth/oidc/exchange {code, code_verifier}       │
 │──────────────────────────────────────>│ POST token_endpoint ────────>│
 │                                        │<─ id_token ─────────────────│
 │                                        │ POST authenticationMore      │
 │                                        │   (Bearer id_token + SysCode)│
 │                                        │<─ 业务账号 userId/姓名/角色   │
 │<─ {access_token, refresh_token, ...} ─│                              │
 │  之后照常 /auth/refresh 长期续期        │                              │
```

### 端点契约

| 端点 | 说明 |
|---|---|
| `GET /api/social/app/auth/oidc/config` | 下发 `{issuer, authorization_endpoint, token_endpoint, client_id, redirect_uri, scopes, code_challenge_method:"S256"}`。**`client_id` 为空字符串表示 OIDC 未启用，APP 应回退静态账号登录** |
| `POST /api/social/app/auth/oidc/exchange` | body `{code, code_verifier}`；成功返回与 `/auth/login` 同构的 `AppLoginResponse`（access+refresh+账号信息）。redirect_uri 必须与服务端配置一致，否则 400 |
| `POST /api/social/app/auth/refresh` | 与现状一致，`{refresh_token}` → 新 token 对；company 来源不做静态账号校验 |
| `POST /api/social/app/auth/login` | 静态账号兜底保留，OIDC 可用后 APP 优先走 OIDC |

### 签发语义（2026-11-26 修复后）

- OIDC 换发签出 `auth_source=company` 的 token 对，`social_user_id=company:{平台userId}`，**角色码（roleCodes）随 access/refresh token 签名携带并在刷新链中保留**（`app_identity.py` 的 `roles` claim）。
- access TTL 7 天（`APP_ACCESS_TOKEN_TTL_SECONDS`），refresh TTL 1 年（`APP_REFRESH_TOKEN_TTL_SECONDS`）。
- APP 端 token 刷新建议：收到 401（`app_token_expired`）时先尝试 refresh，refresh 失败（`refresh_token_expired`）才重走登录；不要每次启动都重登录。

### 用户自动关联（后台机制，无需 APP 参与）

- `app/auth/identity_matching.py` 把 web 会话的 owner（裸平台 `userId`）与 APP company 登录的 owner（`company:{userId}`）归一为同一人（`primary_owner_id`）：web/APP 会话互通、推送受众（`company:{userId}` 形式）、助手个人记忆自动对齐。
- OIDC 登录的用户**天然继承**其在 web 端的全部会话与资产，无需绑定操作；静态账号（`app:android:{account_id}`）只有显式 `bind_user_id` 才关联。
- 登录态会话共享契约：APP 请求带 `X-App-Conversation-Version: 2` 头（新版 APK 已具备）。

## 三、启用前待办（外部依赖）

1. **平台管理员注册移动端 client**：client_id + 回调 `com.suyuan.mobile://oauth/callback`（自定义 scheme，App 工程需注册该 scheme）。
2. **确认 OIDC 端点**：settings 默认指向 CNEMC IDBase（`idaut.cnemc.cn/connect/*`）；许昌部署的认证平台是本地 5180 门户（`AUTH_SERVICE_URL`），实际 issuer/authorize/token 端点以平台管理员答复为准，在 `.env` 覆盖 `COMPANY_OIDC_*`。
3. **后端出网验证**：token 交换在后端完成（8000 → token_endpoint），部署机需可达该端点。
4. `.env` 配置 `COMPANY_OIDC_CLIENT_ID`（占位注释已在 `.env:417`）→ 重启 web → `/auth/oidc/config` 返回非空 client_id 即对 APP 可用。
5. APP 发版切换 OIDC 登录；观察一个迭代后，静态账号表收缩为应急兜底（保留 android_demo 等）。

## 四、APP 退出当前用户功能（2026-11-26 已实现，随下次发版上线）

- 后端 token 为无状态 HMAC 签名，**退出无需后端接口**：APP 端 `logout()` 清除本地 access/refresh token、注销个推设备、取消在跑流式任务。
- **按钮位置（已实现）**：任务中心 tab 顶栏右上角账号图标 → 弹层展示「当前账号：{display_name}」+「退出当前账号」（红色，二次确认）。
- 退出后回到登录页；公司登录可用时优先走 OIDC WebView（自然支持改密后的新密码），否则静态账号表单。
- 若后续要求服务端强制失效（设备丢失场景），再补 jti 黑名单（Redis）+ `/auth/logout` 端点，当前不建。

## 五、APP 端改造现状（2026-11-26，android-native）

以下均已实现，待构建发版（`build-release.ps1`）：

- **OIDC 登录**：`AppViewModel.startCompanyLogin`（PKCE S256 + state）+ `handleCompanyOAuthCallback`（回调校验 + `/auth/oidc/exchange`），manifest 已注册 `com.suyuan.mobile://oauth/callback`。
- **入口自适应**：登录页按 `/auth/oidc/config` 的 `client_id` 是否非空显示/隐藏「公司统一登录」，每次登录页出现时重探——后端注册 client 后无需发版即出现。
- **刷新策略**：OkHttp authenticator 收到 401 自动用 refresh token 换发（`tokenRefreshMutex` 防并发），换发失败清库回登录页；access 7d + refresh 1y 与服务端一致。

## 六、相关测试

- `backend/tests/social/test_app_gateway_contract.py`：OIDC exchange→authenticationMore 契约、company token 往返（含角色码跨刷新保留）、app 来源不带角色码。
