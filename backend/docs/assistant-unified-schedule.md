# 助手统一调度入口

助手模式只暴露 `manage_assistant_schedule`，替换 `schedule_task`、
`create_scheduled_task`、`manage_scheduled_tasks`、`manage_assistant_followups`。
不读取或迁移旧 HEARTBEAT 计划，不提供旧任务兼容查询。其他专业场景保留自身现有工具。

## 使用契约

- `purpose=remind`：本人提醒；原子登记提醒事项与触发计划，不要求先调用事项工具。
- `purpose=followup`：明确授权的事项只读跟进，必须引用已有事项及版本。
- `purpose=execute`：交给项目已开放的办公或专业主模式定时执行，不能使用 social、custom
  或历史 assistant 模式绕过角色边界，不因此给助手增加专业工具。
- `schedule.kind=once/interval/cron`：单次、间隔、五段 cron，显式 IANA 时区。
  `feedback` 仅用于事项跟进，接收到新的已保存反馈才执行；不采集微信群记录。
- 所有类型返回统一 `plan_id/revision/state/schedule/next_at`。
  `list/get/history/results` 查询实际计划、运行和投递记录。
- `update` 只改指令及触发条件，不能修改归属、收件人、执行模式或把提醒升级为分析。
  `pause/resume/cancel` 使用查询得到的 revision，冲突后重新查询。取消不可恢复。
- 提醒暂停或取消会撤销该计划的待执行、运行中结果发布和待投递记录；
  专业任务暂停或取消只停止后续触发，已有执行可能继续，已发送消息无法撤回。
- 当前人类会话交办才能变更；后台事件、子任务和模型参数不能替用户授权。
  即使当前账号是管理员，助手也只管理本人、当前项目的计划。

## 执行和持久化

调度工具通过签名身份访问单实例 worker 的 `/internal/assistant-schedule`。
worker 再验证来源会话归属。该内部路由不挂载到公共 Web API。
HTTP 超时返回未确认，不重试创建，也不回退到 Web 进程的本地调度。

提醒和事项跟进复用数据库 trigger/run/outbox 与现有 worker；后台执行复用
ScheduledTaskService、现有任务存储和 APScheduler。计划 ID 含后端类型与真实记录 ID，
不另建易失步的映射副本。新任务创建幂等于当前用户请求与明确计划配置。
后台任务保存来源会话、请求及原始交办；提醒记录沿用现有 grant 审计字段。

新增后台任务 cron 与 timezone 配置保存在现有 JSON 任务记录中，不需要新增数据库表。
统一入口不改变事项、跟进和只读分析的已有数据库表结构。

提醒/分析仍受现有开关约束，关闭时禁止新建或恢复相应执行，仍可查询和停止。
后台办公/专业执行遵守项目 scheduled_tasks_enabled。创建成功不是执行成功或通知送达。
`inbox_saved` 只表示站内记录保存；`provider_accepted` 只表示渠道受理。

## 验证边界

使用临时 SQLite、临时任务目录和真实 worker ASGI 路由验证生命周期、请求重放、
并发创建、用户/项目隔离、事项反馈触发、时区及消息撤销。
工具与 worker 之间使用内存 HTTP transport，不启动服务器、不调用真实模型、不发送外部消息。
不自动启用部署开关，不执行真实数据库迁移或部署。
