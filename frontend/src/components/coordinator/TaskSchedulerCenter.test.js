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

test('review conversation handler resolves one session and serializes clicks', async () => {
  const source = await readFile(new URL('../../views/ReactAnalysisView.vue', import.meta.url), 'utf8')
  const body = source.match(/const handleReviewConversationOpen = async \(review, \{ returnToTaskCenter = false \} = \{\}\) => \{([\s\S]*?)\r?\n\}/)[1]
  const state = { value: { reviewId: '', busy: false, error: '' } }
  let resolveCalls = 0
  let restoreCalls = 0
  const run = new Function('reviewConversationState', 'resolveReviewSession', 'restoreReviewConversation', 'focusEventEvidenceInRightPanel', 'openSmartEventDetail', 'console',
    `return async review => {${body}}`)(state, async reviewId => {
      resolveCalls += 1
      assert.equal(reviewId, 'review-target')
      await new Promise(resolve => setTimeout(resolve, 10))
      return 'session-target'
    }, async sessionId => { assert.equal(sessionId, 'session-target'); restoreCalls += 1; return true }, () => {}, () => assert.fail('work order must not open smart event'), console)

  await Promise.all([run({ review_id: 'review-target', category: '工单审核' }), run({ review_id: 'review-target', category: '工单审核' })])

  assert.equal(resolveCalls, 1)
  assert.equal(restoreCalls, 1)
  assert.deepEqual(state.value, { reviewId: 'review-target', busy: false, error: '' })
})

test('review conversation failure stays a work-order error instead of opening an event', async () => {
  const source = await readFile(new URL('../../views/ReactAnalysisView.vue', import.meta.url), 'utf8')
  const body = source.match(/const handleReviewConversationOpen = async \(review, \{ returnToTaskCenter = false \} = \{\}\) => \{([\s\S]*?)\r?\n\}/)[1]
  const state = { value: { reviewId: '', busy: false, error: '' } }
  const run = new Function('reviewConversationState', 'resolveReviewSession', 'restoreReviewConversation', 'focusEventEvidenceInRightPanel', 'openSmartEventDetail', 'console',
    `return async review => {${body}}`)(state, async () => { throw new Error('Failed to fetch task review') }, () => assert.fail('must not restore'), () => {}, () => assert.fail('must not request FA as a smart event'), console)

  await run({ review_id: 'review-target', category: '工单审核', subject_id: 'FA261107179401929027665' })

  assert.equal(state.value.busy, false)
  assert.equal(state.value.error, 'Failed to fetch task review')
})

test('review list fits its container and shows only the completion timestamp', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /table-layout: fixed/)
  assert.doesNotMatch(source, /min-width:\s*980px/)
  assert.doesNotMatch(source, /review-list-wrap\s*\{[^}]*overflow-x:\s*auto/)
  assert.match(source, /review-row-actions \.row-action\s*\{[^}]*width:\s*100%/)
  assert.match(source, /overflow-wrap:\s*anywhere/)
  assert.match(source, /return Number\.isNaN\(date\.getTime\(\)\) \? String\(value\) : date\.toLocaleString/)
  assert.doesNotMatch(source, /完成于/)
  // 窄屏不隐藏字段，改为带字段名的卡片行，避免以横向滚动承载表格。
  for (const label of ['状态', '审核建议', '数据处置', '审核结论', '完成时间']) {
    assert.match(source, new RegExp(`data-label="${label}"`))
  }
  assert.match(source, /@media \(max-width: 1100px\)/)
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
  assert.match(view, /:review-conversation-state="reviewConversationState"/)
  assert.match(view, /handleTodoReviewOpen = review => handleReviewConversationOpen\(review, \{ returnToTaskCenter: true \}\)/)
  // 工单审核失败只在原列表报错，不能把 FA 工单号送到智能事件详情。
  assert.match(view, /原审核对话不可用，请通过“查看详情”查看审核依据。/)
  assert.match(view, /if \(isEventReview\) \{\s*openSmartEventDetail\(review\?\.subject_id, \{ returnToTaskCenter \}\)/)
  assert.doesNotMatch(view, /else \{\s*openSmartEventDetail/)
  assert.match(source, /:disabled="conversationState\.busy"/)
  assert.match(source, /conversationState\.busy && conversationState\.reviewId === task\.review_id \? '打开中…' : '进入对话区'/)
  assert.match(source, /conversationState\.error \|\| loadError/)
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
