# 通用事件触发 Agent 任务设计

## 背景

当前高频任务依赖 Heartbeat 或定时任务按周期唤醒 Agent，再由 Agent 判断是否存在需要处理的业务事件。以运城市空气质量盯守为例，即使没有告警，每小时仍会执行社交 Agent，产生不必要的模型调用和费用。

项目已经具备以下可复用能力：

- `ScheduledTask` 的配置、启停、Agent 步骤、执行记录和统计
- Fetcher 的确定性数据采集和规则判断
- `SocialBroadcastService` 的多用户定向广播和附件发送
- 社交用户注册表、用户与主社交会话的映射、会话持久化

本设计在现有任务系统中增加通用事件触发能力。无业务事件时不调用 Agent；事件发生后只执行一次 Agent，再将结果广播给管理员配置的多个微信用户。

## 目标

1. 任务同时支持定时触发和事件触发。
2. 无告警时不运行社交 Agent，也不产生 MiMo 调用。
3. 事件任务复用现有任务启停、执行步骤、执行记录和统计能力。
4. 管理员可在 Web 任务管理页面多选固定微信接收人。
5. 一次事件只执行一次 Agent，与接收人数无关。
6. 广播正文和附件写入每位接收用户的主社交会话，支持连续追问。
7. 事件处理具备跨进程、重启后的幂等能力。
8. 首个接入事件为运城市空气质量告警，但事件机制不绑定具体场景。

## 非目标

- 不建设独立消息队列或通用事件平台。
- 不允许普通微信用户配置本类后台告警任务。
- 不在无告警时调用 LLM 判断是否需要执行。
- 不为每位接收用户分别运行 Agent。
- 本期不提供任意表达式脚本；事件过滤仅支持结构化等值和集合匹配。

## 方案选择

### 采用：扩展现有任务系统

在 `ScheduledTask` 中增加触发配置，由任务服务接收业务事件、匹配事件任务并调用现有执行器。该方案复用范围最大，且任务状态和执行记录仍由一个系统管理。

### 未采用：Fetcher 直接调用 Agent

实现较快，但 Fetcher 会同时承担采集、规则、Agent 编排、用户配置和消息发送职责，难以复用，也不利于统一记录执行状态。

### 未采用：独立事件队列和消费者

扩展性和隔离性更强，但当前只有单机 worker 和有限事件类型，引入额外基础设施不符合本期范围。

## 任务模型

保留现有 `ScheduledTask`，新增以下字段：

```text
trigger_type: "schedule" | "event"         默认 "schedule"
event_type: string | null                    事件任务必填
event_filters: object                        默认空对象
target_user_ids: string[]                    后台 SocialUserRecord.id
broadcast_enabled: boolean                   默认 false
```

约束：

- `trigger_type=schedule` 时沿用现有 `schedule_type` 和时间参数。
- `trigger_type=event` 时必须填写 `event_type`，不注册 APScheduler job。
- 启用广播时必须至少选择一个处于 `active`、已绑定且渠道为微信的后台用户。
- 保存稳定的 `SocialUserRecord.id`；运行时解析其当前 `social_user_id`，避免重新绑定后配置失效。
- 旧任务缺少新增字段时按定时任务读取，保持向后兼容。

## 事件模型

业务代码向任务系统发布结构化事件：

```json
{
  "event_id": "yuncheng-20260713-1600-aqi",
  "event_type": "yuncheng.alert.created",
  "occurred_at": "2026-07-13T16:00:00+08:00",
  "attributes": {
    "city": "运城市",
    "alert_level": "medium",
    "target_pollutant": "AQI"
  },
  "payload": {
    "alert_json_path": "/absolute/path/alert.json",
    "tracing_context_manifest_path": "/absolute/path/tracing_context_manifest.json",
    "evidence_dir": "/absolute/path/evidence"
  }
}
```

`event_type` 使用分层字符串。`event_filters` 首期支持：

- 标量等值：`{"city": "运城市"}`
- 集合包含：`{"alert_level": ["medium", "high"]}`
- 空过滤器：匹配该类型的所有事件

过滤字段只从 `attributes` 读取，避免任务配置依赖任意深层负载结构。

## 事件分发

任务服务增加 `publish_event(event)`：

1. 校验事件结构和必填字段。
2. 查找 `enabled=true`、`trigger_type=event` 且 `event_type` 相同的任务。
3. 应用 `event_filters`。
4. 对每个匹配任务以 `task_id + event_id` 申请持久化执行权。
5. 获得执行权后创建现有 `TaskExecution`，将事件负载注入步骤上下文并执行。
6. 任务成功且启用了广播时，解析广播正文和附件并执行定向发送。
7. 保存执行状态、Agent 结果、逐用户投递结果和错误信息。

`publish_event` 不等待用户交互。Fetcher 可以等待事件被可靠登记，但 Agent 执行作为任务系统中的受控异步执行运行，避免阻塞下一轮采集。

## 幂等和并发

幂等键为 `task_id + event_id`。执行存储增加事件索引，状态至少包括：

```text
claimed -> running -> succeeded | failed
```

领取操作必须是跨进程原子的。当前项目采用持久化文件存储，因此使用同目录锁和原子创建执行声明文件；任务执行记录中同时保存 `event_id` 和 `event_type`。多个 worker 收到同一事件时只能有一个获得执行权。

重启恢复规则：

- `succeeded` 不再运行 Agent，也不重复广播。
- `running` 超过任务超时时间后可转为 `failed`，由管理员手动重试。
- `failed` 默认不自动重新运行 Agent，防止失控计费。
- 已生成有效报告但仅部分用户发送失败时，只重试失败用户，不重新运行 Agent。

## Agent 执行

事件任务仍使用现有 `ScheduledTaskExecutor` 和 `ReActAgent.analyze()`：

- Agent 每个事件任务只执行一次。
- 步骤提示词在运行时附加可信的结构化事件上下文，包括事件 ID、属性和文件路径。
- 运城首个任务使用 `manual_mode=social`，由社交 Agent 按现有职责调用 Assistant/Expert Agent 生成报告。
- Agent 最终结果需要提供可解析的广播正文和附件路径；任务执行器在广播前校验附件存在。
- 目标用户 ID 不交给 LLM 决策，接收范围完全由后台配置和代码控制。

## 定向广播

复用 `SocialBroadcastService.broadcast()`：

1. 根据任务中的后台用户 ID 查询用户注册表。
2. 仅保留 `active`、有 `social_user_id` 且微信渠道匹配的用户。
3. 使用解析后的 `social_user_id` 调用 `broadcast(target_user_ids=...)`。
4. 记录每个用户的发送成功或失败状态。

一次 Agent 结果可广播给多个用户。增加接收人不会增加 Agent 或 MiMo 调用次数。

## 广播会话持久化

广播发送成功后，必须向该用户的主 social session 追加一条助手消息。消息包含：

```json
{
  "id": "broadcast:{task_id}:{event_id}:{user_id}",
  "type": "broadcast",
  "role": "assistant",
  "content": "广播正文",
  "timestamp": "ISO-8601",
  "data": {
    "task_id": "...",
    "execution_id": "...",
    "event_id": "...",
    "event_type": "...",
    "attachments": [
      {"name": "report.docx", "path": "/absolute/path/report.docx", "type": "file"}
    ]
  }
}
```

持久化流程：

1. 使用 `SessionMapper` 获取或创建目标用户的主 social session。
2. 使用 social 模式会话存储加载 Session。
3. 按消息 ID 幂等追加广播消息。
4. 将 Word 等附件合并到 `office_documents`，不能覆盖已有文档。
5. 使用 `append_session_transcript_for_mode(..., mode="social")` 保存。

后续用户发送消息时，Social Agent 从主会话中恢复该广播正文、事件来源和附件信息，从而理解“刚才的告警报告”等指代。

会话落库失败不回滚已经成功的微信发送，但必须记为投递警告并允许单独补写；微信发送失败则不写入“已发送”的会话消息。

## Web 管理

现有“定时任务管理”调整为“任务管理”，创建和编辑表单增加：

- 触发方式：定时触发 / 事件触发
- 事件类型：从后端注册的事件类型列表选择
- 事件过滤：首期提供城市、告警级别等结构化字段，不提供任意脚本
- 广播开关
- 微信接收人：多选已绑定、启用的微信用户

用户选项来自 `/api/social/users`，展示用户名称、渠道和绑定状态。提交时保存后台用户 ID，不直接保存界面文案。

任务列表对事件任务显示事件类型，不显示“下次执行时间”；继续支持启停、编辑、删除、执行记录和统计。事件任务的“立即执行”首期使用最近一条同类型事件作为测试输入；没有可用事件时明确拒绝执行。

## 运城事件接入

`YunchengTrialFetcher` 保持每小时运行，并继续使用普通代码完成采集和规则判断：

1. `has_alert=false` 或 `status=silent`：保存证据后结束，不发布事件。
2. 告警为 `pending_trace`：收集溯源上下文。
3. `tracing_context_manifest.json` 成功生成后发布 `yuncheng.alert.created`。
4. `event_id` 使用稳定的 `alert_id`。
5. 删除或禁用现有用户 HEARTBEAT 中的“运城市告警溯源报告推送”任务，避免双路径重复执行。

## 错误处理

- 事件格式无效：拒绝并记录，不运行 Agent。
- 没有匹配任务：记录事件已接收，不运行 Agent。
- 没有有效接收人：任务执行失败，不运行 Agent，避免生成无人接收的付费报告。
- Agent 或报告生成失败：记录失败，不广播，不自动重复付费执行。
- 附件不存在：广播阶段失败，不发送不完整通知。
- 部分用户发送失败：保留成功用户结果，只允许重试失败用户。
- 会话持久化失败：发送结果标记警告，支持单独补写上下文。

## 测试策略

### 后端单元测试

- 旧定时任务模型向后兼容。
- 事件任务不注册定时调度器。
- 事件类型和过滤器正确匹配。
- 无匹配事件、禁用任务和无有效接收人均不调用 Agent。
- 同一 `task_id + event_id` 并发发布只执行一次。
- Agent 执行一次后广播给多个目标用户。
- 部分投递失败只重试失败用户。
- 广播消息和附件幂等写入各自主社交会话。

### 运城场景测试

- 无告警时不调用事件发布和 Agent。
- 告警但上下文未完成时不发布事件。
- 告警上下文完成后发布一次结构正确的事件。
- 重复处理相同告警不重复运行 Agent。

### 前端测试

- 定时触发和事件触发表单字段切换正确。
- 事件任务支持多选微信用户并提交后台用户 ID。
- 非 active 或未绑定用户不可选。
- 事件任务列表展示事件类型和最近执行状态。

## 验收标准

1. 运城无告警小时的社交 Agent 和 MiMo 调用数为 0。
2. 有告警且上下文就绪时，匹配任务只运行一次 Agent。
3. 多个微信接收人收到相同摘要和报告附件，不增加 Agent 执行次数。
4. 每个成功接收用户的主会话都包含广播正文和附件元数据。
5. 用户随后追问“刚才的报告”时，Social Agent 能从会话中恢复对应上下文。
6. 相同事件重复发布、服务重启或多个 worker 并发时不重复执行。
7. 管理员可在 Web 后台完成事件任务的创建、接收人多选、启停和执行记录查看。
