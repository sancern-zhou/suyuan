# 实时文档资源刷新设计

## 背景

Agent 生成文档后，统一资源存储会在终态事件发出前完成持久化，并在
`complete` 事件中提供 `resource_durable` 和 `resource_version`。当前前端只处理
旧的 `office_documents`、`last_office_document` 以及带预览字段的实时工具结果，
不会根据资源版本刷新统一资源接口，导致新生成的 Excel 等文档无法主动打开右侧预览。

## 目标

- 当当前会话收到已持久化且版本更新的 `complete` 事件时，刷新统一文档资源。
- 将接口资源转换成现有 Office 文档状态结构，触发现有右侧面板 watcher。
- 避免同一资源版本重复请求。
- 会话已切换时丢弃过期响应，避免跨会话污染。
- 请求失败只记录错误，不影响最终答案和 complete 状态处理。

## 方案

前端以统一资源接口为唯一权威来源。在 `complete` 处理中，当
`resource_durable === true`、存在有效 `resource_version` 且存在会话 ID 时，启动一次
异步文档资源刷新。刷新调用现有
`GET /api/sessions/{session_id}/resources?presentation_type=document` 接口，并复用统一的
资源到 Office 文档映射函数。

映射完成后，仅当目标会话仍然处于对应模式状态时更新
`officeDocumentHistory`、`lastOfficeDocument` 和 `lazyArtifacts`。现有
`usePanelManagement` watcher 将据此显示右侧面板并切换到文档标签。

每个会话状态记录最后成功应用的资源版本。相同或更旧版本不再请求；失败的版本不标记
为已应用，以便后续事件或恢复流程重试。

## 组件边界

- 资源映射函数：纯函数，将统一资源 API 数据转换为 Office 文档对象。
- complete 刷新方法：负责版本判断、请求、会话一致性检查和状态更新。
- store complete 分支：只负责触发刷新，不阻塞最终答案落地。
- 面板管理：保持现状，通过 `lastOfficeDocument` 响应式变化自动展开。

## 错误与并发

- API 失败时输出带会话 ID 和版本的错误日志，不抛出到 SSE 事件处理链。
- 响应返回时重新确认目标状态的 session ID，若已变化则忽略响应。
- 同一版本正在请求时不重复发起请求。
- 只有请求成功并应用状态后才更新最后应用版本。

## 测试

- 已持久化的新版本 complete 会请求文档资源并更新文档状态。
- 同版本或旧版本 complete 不重复请求。
- 请求期间切换会话时不应用旧响应。
- 请求失败不更新已应用版本，并允许后续重试。
- 运行相关前端单元测试和完整生产构建。

## 部署验收

在 `/home/xckj/suyuan/frontend` 执行 `npm run build:standalone`，随后重新加载
`suyuan-nginx`。检查构建产物包含统一文档资源接口，并且不包含
`/office-documents` 和 `/visualizations` 旧接口。
