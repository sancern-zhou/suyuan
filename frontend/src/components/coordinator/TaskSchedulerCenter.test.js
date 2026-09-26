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
  assert.match(source, /task\.subject_id/)
  assert.match(source, /formatDataImpact|data_impact/)
  // 页签、类型筛选、统计看板与区块标题均已移除，页面只保留审核结果列表。
  assert.doesNotMatch(source, /status-grid|任务总数|运行中智能体/)
  assert.doesNotMatch(source, /scheduler-tabs|task-type-filters|section-header|REVIEW LIST/)
  assert.doesNotMatch(source, /eventTasks|scheduledTasks|task-cards-grid|formatTaskSchedule/)
  assert.doesNotMatch(source, /fetchRecentExecutions|listJiangsuSmartEventTasks|executionToAttentionItem|smartEventTasks/)
})

test('review list keeps conversation entry, detail dialog and shared emits', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /emit\('select-review', task\)/)
  assert.match(source, /'select-task', 'select-review'/)
  assert.match(source, /selectedReviewId = task\.review_id/)
  const view = await readFile(new URL('../../views/ReactAnalysisView.vue', import.meta.url), 'utf8')
  assert.match(view, /@select-review="handleTodoReviewOpen"/)
  assert.match(view, /suppressSmartEventCommandOpen/)
  const layout = await readFile(new URL('../reactAnalysis/MainLayout.vue', import.meta.url), 'utf8')
  assert.match(layout, /@select-review="\$emit\('select-review', \$event\)"/)
})
