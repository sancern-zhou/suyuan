# 溯源 Agent Android 客户端

这是新的 Android-only 客户端工程，使用 Kotlin、Jetpack Compose、OkHttp 和 Gradle Version Catalog。旧的 React Native 工程不作为本仓库的依赖或构建入口。

## 本地运行

1. 使用 JDK 17 和 Android SDK 34 打开本目录。
2. 后端配置 `APP_AUTH_SECRET` 与 `APP_ACCOUNTS_JSON`，启动 `D:\溯源\backend`。
3. USB 真机调试默认访问 `http://127.0.0.1:8000`，配合 `adb reverse tcp:8000 tcp:8000` 使用；不需要电脑有外网端口。模拟器调试时，再以 `-PapiBaseUrl=http://10.0.2.2:8000` 构建。使用 Wi-Fi 真机时，将 API 地址改为局域网 HTTPS 地址。
4. 执行 `gradlew.bat :app:assembleDebug` 构建调试包；`local.properties` 由本机 Android SDK 自动生成，不提交到版本库。

USB 联调示例（保持手机 USB 调试和后端进程运行）：

```powershell
adb reverse tcp:8000 tcp:8000
gradlew.bat :app:assembleDebug
```

后端模型配置应使用部署环境中已验证的提供商配置；本次联调使用参考环境文件中的 Doubao 主链路。不要把 API key 写入 Android 工程或提交到版本库。

构建前可执行 `powershell -ExecutionPolicy Bypass -File .\check-environment.ps1` 检查 JDK 17 和 Android SDK 34。当前开发机已完成 SDK 34 配置，并可构建 Debug APK。

## 已接入接口

- `POST /api/social/app/auth/login`：App 账号登录并签发 HMAC token。
- `GET /api/social/app/me`：当前账号信息。
- `POST /api/social/app/chat/stream`：Social 模式 Agent SSE 流。
- `GET /api/social/app/sessions`：当前账号的持久会话。
- `POST /api/social/app/sessions`：创建新的 App 会话。
- `GET /api/social/app/sessions/{session_id}/messages`：恢复历史会话消息。
- `POST /api/social/app/upload`：上传并绑定当前会话的附件。
- `POST /api/social/app/voice/transcribe`：m4a 录音上传转写。

App 身份由服务端从 token 解析为 `app:android:<account_id>`，客户端不能通过请求体伪造其他用户。`app:` 会话映射不受现有社交平台 24 小时清理策略影响。
