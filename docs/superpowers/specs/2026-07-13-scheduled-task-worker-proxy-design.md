# 任务管理 Worker 代理修复设计

## 问题

生产采用 `APP_ROLE=web` 的多 Web worker 与单独 `APP_ROLE=worker`。任务服务只在后台 worker 初始化，但 `/api/scheduled-tasks` 目前由 Web 进程本地处理，因此列表和管理请求返回 `ScheduledTaskService not initialized`。

前端同时仍使用旧字段和旧 Store 方法：操作事件读取 `task.id`，而实际主键是 `task.task_id`；启停和立即执行调用的方法也与当前 Store 不一致。

## 设计

- 在 worker 内部 HTTP 应用注册现有 `scheduled_task_routes`，复用 worker 已初始化的唯一任务服务。
- 新增任务管理代理中间件。仅当 `APP_ROLE=web` 且路径为 `/api/scheduled-tasks` 或其子路径时，保持 HTTP 方法、查询参数、请求体和响应状态转发至 worker。
- worker/all 角色不代理，避免回环。
- worker 不可用时返回 503，不回退到 Web 本地执行，防止多进程重复调度或 Agent 执行。
- 前端使用 `task.task_id`，启停分别调用 `enableTask`/`disableTask`，立即执行调用 `executeTaskNow`，删除调用 `deleteTask`。
- 打开管理面板时加载任务列表和统计信息。

## 验收

- Web 角色的任务列表请求能够从 worker 返回任务，包括“运城市告警溯源分析”。
- 内部 worker API 受内部令牌保护并暴露任务路由。
- 启停、立即执行和删除使用正确任务 ID 与 Store 方法。
- 代理失败返回 503；其他 API 和 worker 角色行为不变。

