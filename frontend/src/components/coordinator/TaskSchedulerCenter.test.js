import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('scheduler center renders only the structured review list', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /listTaskReviews\(\)/)
  assert.match(source, /TaskReviewPanel :review-id="selectedReviewId"/)
  // 人工确认归档弹窗同样使用紧凑模式，避免信息过载。
  assert.match(source, /TaskReviewPanel :review-id="selectedReviewId" compact/)
  // 待办以结构化审核结果列表展示（审核标题/审核建议/数据处置/结论等列）。
  assert.match(source, /review-list/)
  // 业务编号列已按江苏分支用户要求整列移除，subject_id 只在详情里展示。
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

test('guangdong adaptation: detail falls back to review dialog, no jiangsu workspaces', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  // 广东未迁移江苏的整页工单审核工作台/智能事件中心：查看详情直接打开审核详情弹窗。
  assert.match(source, /selectedReviewId\.value = task\.review_id/)
  assert.doesNotMatch(source, /open-review-detail|open-event-detail|isWorkOrderTask/)
  // 品牌与文案按广东适配，不残留江苏品牌。
  assert.doesNotMatch(source, /苏环智管/)
  assert.match(source, /快速审核/)
  assert.match(source, /进入对话区/)
  const layout = await readFile(new URL('../reactAnalysis/MainLayout.vue', import.meta.url), 'utf8')
  assert.match(layout, /@select-review="\$emit\('select-review', \$event\)"/)
  assert.match(layout, /workspace === 'task-center' && TaskSchedulerCenter/)
  const view = await readFile(new URL('../../views/ReactAnalysisView.vue', import.meta.url), 'utf8')
  assert.match(view, /@select-review="handleTodoReviewOpen"/)
  // 广东不接江苏的整页工单审核工作台与智能事件中心面板。
  assert.doesNotMatch(layout, /WorkOrderReviewCenterPanel|SmartEventCenterPanel/)
})
