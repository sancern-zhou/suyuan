import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('scheduler center renders only the structured review list', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /listTaskReviews\(\)/)
  assert.match(source, /TaskReviewPanel :review-id="selectedReviewId"/)
  // 人工确认归档弹窗同样使用紧凑模式，避免信息过载。
  assert.match(source, /TaskReviewPanel :review-id="selectedReviewId" compact/)
  // 待办以结构化审核结果列表展示（业务编号/审核依据/建议/数据处置等列）。
  assert.match(source, /review-list/)
  // 业务编号列已按用户要求整列移除（2026-09-23），subject_id 只在详情里展示。
  assert.doesNotMatch(source, /task\.subject_id/)
  assert.match(source, /formatDataImpact|data_impact/)
  // 已归档/已退回记录保留在列表中：状态筛选 + 徽章样式 + 中文状态兜底。
  assert.match(source, /v-model="filters\.status"/)
  assert.match(source, /status-archived/)
  assert.match(source, /archived: '已归档', rejected: '已退回'/)
  const api = await readFile(new URL('../../services/taskReviewsApi.js', import.meta.url), 'utf8')
  assert.match(api, /pending_only=false/)
  // 页签、类型筛选、统计看板与区块标题均已移除，页面只保留审核结果列表。
  assert.doesNotMatch(source, /status-grid|任务总数|运行中智能体/)
  assert.doesNotMatch(source, /scheduler-tabs|task-type-filters|section-header|REVIEW LIST/)
  assert.doesNotMatch(source, /eventTasks|scheduledTasks|task-cards-grid|formatTaskSchedule/)
  assert.doesNotMatch(source, /fetchRecentExecutions|listJiangsuSmartEventTasks|executionToAttentionItem|smartEventTasks/)
})

test('review list keeps conversation entry, detail dialog and shared emits', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /emit\('select-review', task\)/)
  assert.match(source, /'select-task', 'select-review', 'open-review-detail', 'open-event-detail'/)
  assert.match(source, /selectedReviewId = task\.review_id/)
  // 两类行操作区一致：查看详情直达整页工作台（不进对话）；人工确认表单保留在快速审核弹窗。
  assert.match(source, /emit\('open-review-detail', task\)/)
  assert.match(source, /isWorkOrderTask/)
  assert.match(source, /快速审核/)
  assert.match(source, /进入对话区/)
  // 智能事件行的查看详情按 subject_id（事件 ID）分流到 open-event-detail。
  assert.match(source, /emit\('open-event-detail', task\)/)
  const view = await readFile(new URL('../../views/ReactAnalysisView.vue', import.meta.url), 'utf8')
  assert.match(view, /@select-review="handleTodoReviewOpen"/)
  assert.match(view, /suppressSmartEventCommandOpen/)
  assert.match(view, /@open-review-detail="handleTodoReviewDetailOpen"/)
  // 直达详情复用工单审核工作台命令契约，整页管理面板直显（同智能事件中心），不进对话不出右侧 tab。
  assert.match(view, /WORK_ORDER_REVIEW_COMMANDS\.OPEN, working_order_code: code/)
  assert.match(view, /managementPanel\.value = 'work-order-review'/)
  // 智能事件行查看详情复用 open_event_detail 命令契约整页直显；面板关闭按进入来源回任务调度中心。
  assert.match(view, /@open-event-detail="handleTodoEventDetailOpen"/)
  assert.match(view, /open_event_detail', event_id: eventId/)
  assert.match(view, /managementPanel\.value = 'smart-events'/)
  assert.match(view, /@close-smart-event-management-panel="handleSmartEventManagementPanelClose"/)
  const layout = await readFile(new URL('../reactAnalysis/MainLayout.vue', import.meta.url), 'utf8')
  assert.match(layout, /@select-review="\$emit\('select-review', \$event\)"/)
  assert.match(layout, /@open-review-detail="\$emit\('open-review-detail', \$event\)"/)
  assert.match(layout, /@open-event-detail="\$emit\('open-event-detail', \$event\)"/)
  // 管理面板插槽内宿主整页工单审核工作台；返回列表直接关闭回任务调度中心，不展示内部工单列表。
  assert.match(layout, /managementPanel === 'work-order-review'/)
  assert.match(layout, /WorkOrderReviewCenterPanel[\s\S]*?:list-return-closes="true"/)
  // 智能事件中心整页宿主的关闭走专属事件，由宿主决定回落点（任务调度中心或当前对话）。
  assert.match(layout, /managementPanel === 'smart-events'/)
  assert.match(layout, /@close="\$emit\('close-smart-event-management-panel'\)"/)
  // 对话右侧 tab 仅展示当前工单分析，不提供刷新/返回列表（整页模式保持默认 true）。
  const panel = await readFile(new URL('../management/WorkOrderReviewCenterPanel.vue', import.meta.url), 'utf8')
  assert.match(panel, /showListActions: \{ type: Boolean, default: true \}/)
  assert.match(panel, /listReturnCloses: \{ type: Boolean, default: false \}/)
  assert.match(panel, /if \(props\.listReturnCloses\) \{\s*\n\s*emit\('close'\)/)
  const rightPanel = await readFile(new URL('../reactAnalysis/RightPanelContainer.vue', import.meta.url), 'utf8')
  assert.match(rightPanel, /:show-list-actions="false"/)
})
