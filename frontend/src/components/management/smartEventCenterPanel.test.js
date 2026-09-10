import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const source = fs.readFileSync(
  path.join(import.meta.dirname, 'SmartEventCenterPanel.vue'),
  'utf8'
)

test('smart event center renders a fixed list and detail surface', () => {
  assert.match(source, /aria-label="智能事件列表"/)
  assert.match(source, /aria-label="智能事件详情"/)
  assert.match(source, /ai_judgment/)
  assert.match(source, /final_response/)
})

test('smart event detail can open the corresponding scheduled task workspace', () => {
  assert.match(source, /listJiangsuSmartEventTasks/)
  assert.match(source, /\$emit\('open-task', task\)/)
  assert.match(source, /task\.task_id/)
})

test('event list exposes a manual AI judgment dispatch action', () => {
  assert.match(source, /AI研判/)
  assert.match(source, /dispatchJiangsuSmartEventAiJudgment/)
  assert.match(source, /@click\.stop="dispatchAiJudgment\(event\)"/)
})

test('smart event workspace handles Agent focus, comparison, history, and task commands', () => {
  assert.match(source, /command\.type === 'focus_evidence'/)
  assert.match(source, /command\.type === 'compare_events'/)
  assert.match(source, /command\.type === 'show_operation_history'/)
  assert.match(source, /command\.type === 'open_task'/)
  assert.match(source, /workspaceMode === 'compare'/)
  assert.match(source, /workspaceMode === 'history'/)
})

test('fixed event detail exposes confirmation and archive controls', () => {
  assert.match(source, /TaskReviewPanel/)
  assert.match(source, /refreshSelectedReview/)
  assert.match(source, /label: '处置操作'/)
  assert.match(source, /派单处理/)
  assert.match(source, /工单说明/)
  assert.match(source, /dispatchDialogVisible/)
  assert.match(source, /role="dialog" aria-modal="true" aria-label="工单派发"/)
  assert.doesNotMatch(source, /label: '人工确认'/)
  assert.match(source, /platform_alarm: '平台报警'/)
  assert.match(source, /video: '视频监控记录'/)
  assert.doesNotMatch(source, /ALMsummary/)
})

test('disposal area submits dispatch order, incremental feedback, and archive confirmation', () => {
  assert.match(source, /dispatchJiangsuSmartEventOrder/)
  assert.match(source, /submitJiangsuSmartEventFeedback/)
  assert.match(source, /事件反馈/)
  assert.match(source, /aria-label="事件反馈"/)
  assert.match(source, /反馈将以增量对话提交给上一轮 AI 研判/)
  assert.match(source, /handleFeedbackAttachments/)
  assert.match(source, /submitDispatchOrder/)
  assert.match(source, /submitFeedback/)
  assert.match(source, /aria-label="操作历史"/)
  assert.match(source, /operationActionLabel/)
  assert.match(source, /暂无处置记录/)
})

test('fixed event detail presents old workbench style evidence sections', () => {
  assert.match(source, /workbench-index/)
  assert.match(source, /workbench-content/)
  assert.match(source, /证据目录/)
  assert.match(source, /事件基础信息/)
  assert.doesNotMatch(source, /抓取\/更新证据包/)
  assert.match(source, /sourceStatusClass/)
  assert.match(source, /查询时间窗口|time_range/)
  assert.match(source, /暂无.*数据/)
  assert.match(source, /sourceColumnDefinitions/)
  assert.match(source, /getBoundingClientRect\(\)\.top <= containerTop \+ 8/)
  assert.match(source, /workbench-content::after/)
})

test('event list keeps internal event identifiers out of the visible table', () => {
  assert.doesNotMatch(source, /<small>\{\{ event\.event_id \}\}<\/small>/)
})

test('event list shows stored pages first and refreshes in the background', () => {
  assert.match(source, /pollSyncStatus\(syncGeneration\)/)
  assert.match(source, /listJiangsuSmartEvents\(\{ \.\.\.activeQuery\.value, refresh: false \}\)/)
  assert.match(source, /watchBackgroundSync\(\)/)
  assert.doesNotMatch(source, /refresh: true/)
  assert.match(source, /applySyncedEvents\(payload\)/)
  assert.match(source, /applyListPage\(payload\)/)
  assert.match(source, /onUnmounted\(\(\) => \{\n?\s*stopSyncWatch\(\)/)
  assert.match(source, /window\.removeEventListener\('resize', handleChartResize\)/)
  assert.match(source, /syncing \? '同步中…' : lastSyncTime/)
})

test('event list renders all merged clue tags in parallel with counts and expand control', () => {
  assert.match(source, /visibleTagChips\(event\)/)
  assert.match(source, /hiddenTagCount\(event\)/)
  assert.match(source, /expandTags\(event\.event_id\)/)
  assert.match(source, /更多 \{\{ hiddenTagCount\(event\) \}\} 个/)
  assert.match(source, /class="clue-chip"/)
  assert.doesNotMatch(source, /<td>\{\{ event\.primary_clue_tag \|\| event\.source_alarm_rule_type \|\| '告警事件' \}\}<\/td>/)
})

test('merged events surface pending delta and incremental judgment continuity', () => {
  assert.match(source, /event\.pending_delta/)
  assert.match(source, /新增线索待研判/)
  assert.match(source, /增量研判/)
  assert.match(source, /selectedEvent\.value\?\.judgment_history/)
  assert.match(source, /研判轮次记录/)
  assert.match(source, /线索数量/)
  assert.match(source, /研判轮次'/)
  assert.match(source, /aria-label="线索标签集合"/)
})

test('judgment panel renders Markdown conclusion and keeps structured details out of the result', () => {
  assert.match(source, /TaskReviewPanel/)
  assert.match(source, /<MarkdownRenderer[^>]*:content="judgmentText"/)
  assert.doesNotMatch(source, /aria-label="数据详细分析"|<summary>研判依据与参数快照/)
  assert.match(source, /getJiangsuSmartEventConfig/)
  assert.match(source, /AI 重新研判/)
  assert.match(source, /执行 AI 研判/)
})

test('monitoring section renders six-pollutant line chart, table toggle, and regional delta bars', () => {
  assert.match(source, /import \* as echarts from 'echarts'/)
  assert.match(source, /aria-label="六参五分钟折线时序图"/)
  assert.match(source, /aria-label="监测数据视图切换"/)
  assert.match(source, /aria-label="监测数据表"/)
  assert.match(source, /aria-label="区域差异柱状图"/)
  assert.match(source, /minuteChartOption/)
  assert.match(source, /deltaChartOption/)
  assert.match(source, /regionalDeltas/)
  assert.match(source, /'与周边站点差值', type: 'bar', itemStyle: \{ color: '#1677ff' \}/)
  assert.match(source, /'与全市其余站点差值', type: 'bar', itemStyle: \{ color: '#d4380d' \}/)
  assert.match(source, /POLLUTANT_SERIES/)
  assert.match(source, /monitoringView === 'chart'/)
  assert.match(source, /recordPollutant/)
})


test('stored list is displayed before the background refresh resolves', async () => {
  const body = source.match(/const loadEvents = async \(page = 1\) => \{([\s\S]*?)\n\}\n\nconst resetFilters/)[1]
  const loading = { value: false }
  const events = { value: [] }
  let backgroundStarted = false
  const run = new Function('loading', 'events', 'error', 'lastSync', 'props',
    'stopSyncWatch', 'listJiangsuSmartEvents', 'watchBackgroundSync',
    'activeQuery', 'PAGE_SIZE', 'statusFilter', 'typeFilter', 'keyword', 'applyListPage',
    `return (async (page = 1) => {${body}})()`)
  await run(loading, events, { value: '' }, { value: null }, {}, () => {},
    async params => {
      assert.equal(params.refresh, false)
      assert.equal(params.limit, 10)
      assert.equal(params.page, 1)
      return { events: [{ event_id: 'stored' }] }
    }, () => {
      assert.equal(loading.value, false)
      assert.equal(events.value[0].event_id, 'stored')
      backgroundStarted = true
    }, { value: {} }, 10, { value: '' }, { value: '' }, { value: '' }, payload => { events.value = payload.events })
  assert.equal(backgroundStarted, true)
  assert.match(source, /v-if="loading && !events.length"/)
})
