# 助手模式定向微信广播设计

## 目标

让运行在 Web 进程中的助手模式可以调用 `broadcast_social_users`，通过 Worker 中已初始化的微信消息总线，把正文和附件发送给明确指定的一个或多个后台微信用户，并持久化到每位用户的社交对话上下文。

## 约束

- `target_user_ids` 必填且至少包含一个后台用户 ID。
- 不允许省略目标后退化为全员广播。
- 目标用户必须处于 `active` 状态、已绑定 `social_user_id`，且渠道为微信。
- Web 进程不直接创建或访问微信消息总线。
- Worker 内部接口沿用 `x-social-worker-token` 鉴权。
- 正文与附件必须进入接收用户的社交会话，支持后续连续对话。

## 架构

新增一个 Worker 内部定向广播接口。`broadcast_social_users` 工具调用该接口，而不是读取当前 Web 进程的消息总线。Worker 接口负责解析后台用户 ID、校验微信绑定、调用现有 `SocialBroadcastService`，并返回逐用户投递结果。

Worker 内部仍复用现有广播服务、用户注册表、消息总线和上下文持久化逻辑，不创建第二套发送实现。接口被注册到现有 Worker 内部 FastAPI 应用，并受现有内部 Token 中间件保护。

## 数据流

1. 助手调用 `broadcast_social_users`，提供 `message`、必填 `target_user_ids`，以及可选 `media`。
2. 工具校验目标列表非空，通过内部 HTTP 请求发送给 Worker。
3. Worker 按后台用户 ID 查询用户注册表。
4. Worker 拒绝不存在、禁用、未绑定或非微信渠道的用户，并保留逐用户错误。
5. 对有效用户，Worker 调用 `SocialBroadcastService.broadcast`，只传入解析后的 `social_user_id`。
6. 广播服务发送正文和附件，并把广播内容、附件及调用元数据写入每位用户的社交会话。
7. Worker 返回总体状态和逐用户结果，工具按原工具结果格式交给 Agent。

## 接口

工具参数：

```json
{
  "message": "广播正文",
  "target_user_ids": ["后台用户ID-1", "后台用户ID-2"],
  "media": ["/absolute/path/report.docx"]
}
```

Worker 内部接口请求包含相同业务字段，并附加来源元数据：

```json
{
  "message": "广播正文",
  "target_user_ids": ["后台用户ID-1"],
  "media": ["/absolute/path/report.docx"],
  "context_metadata": {
    "source": "assistant_tool",
    "tool_name": "broadcast_social_users"
  }
}
```

响应沿用广播服务的 `status`、`success`、`channels_sent`、`failed_user_ids`、`delivery_results`、`media_sent` 和 `summary` 字段，并确保每个投递结果包含后台 `user_id`。

## 错误处理

- 目标列表为空：工具本地失败，不发起请求。
- Worker 不可达或超时：返回“社交 Worker 不可用”，不得尝试本地群发。
- 目标用户无效：逐用户返回错误；有效目标仍可发送。
- 所有用户无效或全部发送失败：总体 `success=false`。
- 部分成功：总体保留成功状态，同时返回失败用户及错误，供助手明确告知用户。
- 附件不存在或微信发送失败：由广播服务记录到对应投递结果。

## 测试

- 工具 Schema 要求 `target_user_ids`。
- 空目标列表在工具层被拒绝，且不会调用 Worker。
- Web 工具请求携带内部 Token 并正确转发正文、目标和附件。
- Worker 只解析并发送给指定的有效微信用户。
- 无效用户不会导致广播给其他未指定用户。
- Worker 返回逐用户发送结果。
- 成功广播会把正文、附件和来源元数据写入目标用户社交会话。
- Worker 不可用时工具返回明确失败。

## 非目标

- 不实现按姓名模糊匹配用户。
- 不允许助手省略目标后群发全部用户。
- 不迁移助手 Agent 到 Worker。
- 不引入通用工具 RPC 框架。
