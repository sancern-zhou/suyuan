# 溯源 Agent Android 客户端

这是新的 Android-only 客户端工程，使用 Kotlin、Jetpack Compose、OkHttp 和 Gradle Version Catalog。旧的 React Native 工程不作为本仓库的依赖或构建入口。

## 本地运行

1. 使用 JDK 17 和 Android SDK 34 打开本目录。
2. 后端配置 `APP_AUTH_SECRET` 与 `APP_ACCOUNTS_JSON`，启动 `D:\溯源\backend`。
3. App 默认访问 `http://219.135.180.51:54333`。如需连接其他环境，可在构建时通过 `-PapiBaseUrl=...` 覆盖。HTTP 地址已在 Android 清单中允许明文访问。
4. 推荐执行 `.\build-debug.ps1 -Install` 构建并安装调试包。脚本会从 `../backend/.env` 读取 `PUSH_GETUI_APP_ID`，自动传给 Gradle，并固定使用 JDK 17；`local.properties` 由本机 Android SDK 自动生成，不提交到版本库。

构建并安装示例：

```powershell
.\build-debug.ps1 -Install
```

如需指定 API 地址或设备：

```powershell
.\build-debug.ps1 -ApiBaseUrl http://219.135.180.51:54333 -Install -DeviceId A43TVB4A25013903
```

后端模型配置应使用部署环境中已验证的提供商配置；本次联调使用参考环境文件中的 Doubao 主链路。不要把 API key 写入 Android 工程或提交到版本库。

## 个推统一推送联调

后台广播推送使用个推 UniPush，Android 工程不区分华为、荣耀、小米等厂商。
后端只配置 `PUSH_PROVIDER=getui`、`PUSH_GETUI_APP_ID`、
`PUSH_GETUI_APP_KEY` 和 `PUSH_GETUI_MASTER_SECRET`；其中 App Key 和 Master
Secret 仅放在后端环境变量，不能写入 App 或提交 Git。构建时把同一个 App ID
传给 Gradle。推荐使用上面的 `build-debug.ps1`，避免遗漏；不要把真实 App ID
或其他推送密钥写入 Android 工程或提交 Git。

```powershell
.\build-debug.ps1 -Install
```

首次登录并允许 Android 13+ 通知权限后，App 会自动获取 CID 并注册到
`POST /api/social/app/push/devices`。然后触发一个配置了社交广播收件人的定时任务，
检查广播先写入 App 收件箱、个推返回 `sent`、手机收到系统通知，点击通知后 App
刷新收件箱。详细的后端环境变量和排查顺序见
`D:\溯源\backend\docs\android-unified-push.md`。

广播和历史会话列表采用分段加载：首次请求最新 30 条，滚动到列表底部后继续加载更早内容；
广播详情页的操作菜单支持删除，删除只移除收件箱记录，不会自动删除服务器上的原始附件文件。

构建前可执行 `powershell -ExecutionPolicy Bypass -File .\check-environment.ps1` 检查 JDK 17 和 Android SDK 34。当前开发机已完成 SDK 34 配置，并可构建 Debug APK。

## 已接入接口

- `POST /api/social/app/auth/login`：App 账号登录并签发 HMAC token。
- `GET /api/social/app/auth/oidc/config`：读取公司 IDBase OIDC/PKCE 公共配置。
- `POST /api/social/app/auth/oidc/exchange`：后端用授权码和 PKCE verifier 交换 ID token，并调用 `authenticationMore` 映射公司业务账号。
- `POST /api/social/app/auth/refresh`：轮换 App access/refresh token；App 启动和接口收到 401 时自动使用 refresh token 恢复会话。
- `GET /api/social/app/me`：当前账号信息。
- `POST /api/social/app/chat/stream`：Social 模式 Agent SSE 流。
- `GET /api/social/app/sessions`：当前账号的持久会话。
- `POST /api/social/app/sessions`：创建新的 App 会话。
- `GET /api/social/app/sessions/{session_id}/messages`：恢复历史会话消息。
- `POST /api/social/app/upload`：上传并绑定当前会话的附件。
- `POST /api/social/app/voice/transcribe`：m4a 录音上传转写。

App 身份由服务端从 token 解析为 `app:android:<account_id>`，客户端不能通过请求体伪造其他用户。`app:` 会话映射不受现有社交平台 24 小时清理策略影响。

## 公司统一登录配置

公司登录使用 IDBase OIDC Authorization Code + PKCE（S256）。后端环境文件需要配置
`COMPANY_OIDC_CLIENT_ID` 和 `COMPANY_AUTHENTICATION_MORE_URL`；客户端只接收公共授权端点和
redirect URI，不保存公司密码。回调地址固定为 `com.suyuan.mobile://oauth/callback`，需在 IDBase
移动端客户端登记同一地址。refresh token 只保存在 Android 私有存储中，退出登录时清除。
