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

test('event list filters by a start and end event time', () => {
  assert.match(source, /v-model="listStartTime" type="datetime-local" aria-label="事件开始时间筛选"/)
  assert.match(source, /v-model="listEndTime" type="datetime-local" aria-label="事件结束时间筛选"/)
  assert.match(source, /start_time: listStartTime\.value \|\| undefined/)
  assert.match(source, /end_time: listEndTime\.value \|\| undefined/)
  assert.match(source, /开始时间不能晚于结束时间/)
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
  // 归档弹窗使用紧凑模式：隐藏检查项、数据影响区间明细与证据材料，避免信息过载。
  assert.match(source, /<TaskReviewPanel :review-id="selectedEvent\.review_id" compact/)
  assert.match(source, /refreshSelectedReview/)
  assert.match(source, /label: '处置操作'/)
  assert.match(source, /派单处理/)
  assert.match(source, /工单内容/)
  assert.match(source, /dispatchDialogVisible/)
  assert.match(source, /role="dialog" aria-modal="true" aria-label="工单派发"/)
  assert.doesNotMatch(source, /label: '人工确认'/)
  assert.doesNotMatch(source, /platform_alarm: '平台报警'/)
  assert.match(source, /hiddenSources/)
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
  // 详情内容区不再注入固定高度的伪元素，避免证据内容后出现空白占位。
  assert.doesNotMatch(source, /workbench-content::after/)
  // 动环门控未命中时证据源返回 skipped，详情页按中性状态展示而非获取失败。
  assert.match(source, /source\.status === 'skipped'/)
  assert.match(source, /按条件跳过/)
})

test('instrument status renders mapped projection while staying backward compatible', () => {
  // 新证据包 instrument_status.data 为映射投影（series），旧包为逐行原始记录，两者都要能展示。
  assert.match(source, /instrumentStatusRows/)
  assert.match(source, /Array\.isArray\(data\?\.series\)/)
  assert.match(source, /item\.param/)
  assert.match(source, /abnormalSummary/)
  assert.match(source, /valueSummary/)
  assert.match(source, /raw_points/)
})

test('event timestamps use one second-precision display format', () => {
  assert.match(source, /timeZone: 'Asia\/Shanghai'/)
  assert.match(source, /naiveDateTime/)
  assert.match(source, /`\$\{parts\.year\}-\$\{parts\.month\}-\$\{parts\.day\} \$\{parts\.hour\}:\$\{parts\.minute\}:\$\{parts\.second\}`/)
  assert.match(source, /formatTimeRange\(section\.value\.metadata\.time_range\)/)
  assert.match(source, /\(\?:time\|date\|_at\$\)/)
  assert.doesNotMatch(source, /date\.toLocaleString\('zh-CN'/)
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

test('judgment panel retains concise summary and exposes collapsible analysis', () => {
  assert.match(source, /TaskReviewPanel/)
  assert.match(source, /<MarkdownRenderer[^>]*:content="judgmentText"/)
  assert.match(source, /<summary>完整研判分析与依据<\/summary>/)
  assert.match(source, /getJiangsuSmartEventConfig/)
  assert.match(source, /AI 增量研判/)
  assert.match(source, /执行 AI 研判/)
})

test('completed AI judgments hide manual dispatch actions to avoid mis-clicks', () => {
  assert.match(source, /const hasCompletedJudgment = event =>/)
  assert.match(source, /v-if="!hasCompletedJudgment\(event\) \|\| event\.pending_delta"/)
  assert.match(source, /v-if="!hasCompletedJudgment\(selectedEvent\) \|\| selectedEvent\?\.pending_delta"/)
  assert.match(source, /AI 研判已完成，不再提供手动研判入口/)
  assert.match(source, /hasCompletedJudgment\(event\) && !event\.pending_delta/)
  assert.match(source, /该事件已完成 AI 研判，无需再次触发/)
})

test('regional comparison owns delta bars while raw monitoring remains hidden evidence', () => {
  assert.match(source, /import \* as echarts from 'echarts'/)
  assert.match(source, /aria-label="区域差异柱状图"/)
  assert.match(source, /aria-label="气象折线时序图"/)
  assert.match(source, /deltaChartOption/)
  assert.match(source, /weatherChartOption/)
  assert.match(source, /regionalDeltas/)
  assert.match(source, /new Set\(\['monitoring', 'platform_alarm'/)
  assert.match(source, /'与周边站点差值', type: 'bar', itemStyle: \{ color: CHART_PRIMARY \}/)
  assert.match(source, /'与全市其余站点差值', type: 'bar', itemStyle: \{ color: CHART_ALARM \}/)
  assert.match(source, /POLLUTANT_SERIES/)
  assert.match(source, /WEATHER_SERIES/)
  assert.match(source, /recordPollutant/)
  assert.match(source, /temperature: 4, humidity: 4, pressure: 5/)
  assert.match(source, /name: '气温 \(℃\) \/ 湿度 \(%\)'/)
  assert.match(source, /name: '气压 \(hPa\)', position: 'right'/)
  assert.match(source, /axisLabel: \{ show: gridIndex === 2/)
  assert.match(source, /axisPointer: \{ link: \[\{ xAxisIndex: 'all' \}\] \}/)
  assert.match(source, /\.weather-chart-canvas \{ height: 580px; \}/)
  assert.doesNotMatch(source, /aria-label="六参小时折线时序图"/)
  assert.doesNotMatch(source, /aria-label="监测数据视图切换"/)
  assert.doesNotMatch(source, /aria-label="监测数据表"/)
})

test('regional comparison renders target and peer time series instead of raw records table', () => {
  assert.match(source, /目标站与对比站小时趋势/)
  assert.match(source, /aria-label="片区对比污染物切换"/)
  assert.match(source, /aria-label="目标站与对比站小时趋势图"/)
  assert.match(source, /comparisonChartOption/)
  assert.match(source, /station\.name.*station\.code/)
  assert.doesNotMatch(source, /参与对比的小时记录/)
})


test('stored list is displayed before the background refresh resolves', async () => {
  const body = source.match(/const loadEvents = async \(page = 1\) => \{([\s\S]*?)\r?\n\}\r?\n\r?\nconst resetFilters/)[1]
  const loading = { value: false }
  const events = { value: [] }
  let backgroundStarted = false
  const run = new Function('loading', 'events', 'error', 'lastSync', 'props',
    'stopSyncWatch', 'listJiangsuSmartEvents', 'watchBackgroundSync',
    'activeQuery', 'PAGE_SIZE', 'statusFilter', 'selectedEventTypes', 'levelFilter', 'keyword',
    'categoryEventTypes',
    'listStartTime', 'listEndTime', 'applyListPage', 'actionMessage',
    `return (async (page = 1) => {${body}})()`)
  await run(loading, events, { value: '' }, { value: null }, {}, () => {},
    async params => {
      assert.equal(params.refresh, false)
      assert.equal(params.limit, 10)
      assert.equal(params.page, 1)
      assert.equal(params.event_types, undefined)
      return { events: [{ event_id: 'stored' }] }
    }, () => {
      assert.equal(loading.value, false)
      assert.equal(events.value[0].event_id, 'stored')
      backgroundStarted = true
    }, { value: {} }, 10, { value: '' }, { value: [] }, { value: '' }, { value: '' }, { value: null }, { value: '' }, { value: '' }, payload => { events.value = payload.events }, { value: '' })
  assert.equal(backgroundStarted, true)
  assert.match(source, /v-if="loading && !events.length"/)
})

test('category entry filters event types on the server instead of in the browser', () => {
  assert.match(source, /const categoryEventTypes = computed\(\(\) => CATEGORY_TYPES\[props\.category\] \|\| null\)/)
  const body = source.match(/const loadEvents = async \(page = 1\) => \{([\s\S]*?)\r?\n\}\r?\n\r?\nconst resetFilters/)[1]
  assert.match(body, /event_types: selectedEventTypes\.value\.length \? selectedEventTypes\.value : undefined/)
  assert.doesNotMatch(body, /event_type:/)
  assert.match(source, /const filteredEvents = computed\(\(\) => events\.value\)/)
})

test('entry preselects the whole category so the UI matches the queried scope', () => {
  assert.match(source, /selectedEventTypes\.value = \[\.\.\.\(categoryEventTypes\.value \|\| \[\]\)\]/)
  assert.match(source, /watch\(\(\) => props\.category, \(\) => \{\r?\n  selectedEventTypes\.value = \[\.\.\.\(categoryEventTypes\.value \|\| \[\]\)\]\r?\n  loadEvents\(\)\r?\n\}\)/)
  assert.match(source, /picked\.length === 1 \? picked\[0\] : `\$\{picked\[0\]\} 等 \$\{picked\.length\} 类`/)
})

test('event type dropdown collapses to an all-types trigger with checkbox menu', () => {
  assert.match(source, /const emptyTypeOptionLabel = computed\(\(\) => '全部类型'\)/)
  assert.match(source, /<button type="button" class="type-select-trigger" :aria-expanded="typeMenuOpen" aria-label="事件类型筛选"/)
  assert.match(source, /<span class="type-trigger-text">\{\{ typeTriggerLabel \}\}<\/span>/)
  assert.match(source, /if \(!picked\.length\) return emptyTypeOptionLabel\.value/)
  assert.match(source, /<input type="checkbox" :value="value" v-model="selectedEventTypes" @change="scheduleTypeLoad" \/>/)
  assert.match(source, /@click="clearTypeSelection">清空</)
  assert.match(source, /@click="closeTypeMenu">完成</)
  assert.match(source, /document\.addEventListener\('pointerdown', handleTypeMenuPointerDown\)/)
  assert.match(source, /appliedTypeKey = JSON\.stringify\(activeQuery\.value\.event_types \|\| \[\]\)/)
})

test('agent event_type and event_types filters backfill the multi-select', () => {
  const body = source.match(/if \(command\.type === 'show_event_list'([\s\S]*?)\r?\n  \}\r?\n\}, \{ deep: true, immediate: true \}\)/)[1]
  assert.match(body, /Array\.isArray\(filters\.event_types\) && filters\.event_types\.length/)
  assert.match(body, /String\(filters\.event_type \|\| filters\.type \|\| ''\)\.trim\(\) \? \[String\(filters\.event_type \|\| filters\.type\)\.trim\(\)\] : \[\]/)
  assert.match(body, /selectedEventTypes\.value = commandTypes\.length \? commandTypes : \[\.\.\.\(categoryEventTypes\.value \|\| \[\]\)\]/)
  assert.match(source, /const resetFilters = \(\) => \{[\s\S]*?selectedEventTypes\.value = \[\.\.\.\(categoryEventTypes\.value \|\| \[\]\)\]/)
})

test('type options union keeps category and agent-filtered values selectable', () => {
  assert.match(source, /\.\.\.listFilters\.value\.types,/)
  assert.match(source, /\.\.\.\(categoryEventTypes\.value \|\| \[\]\),/)
  assert.match(source, /\.\.\.selectedEventTypes\.value,/)
})

test('event list defaults to the current day time range', () => {
  assert.match(source, /start: `\$\{parts\.year\}-\$\{parts\.month\}-\$\{parts\.day\}T00:00`/)
})

test('video evidence template state is declared as refs', () => {
  // 视频证据区在模板中读写 videoImageUrls/previewImageUrl；
  // 未声明时 videoImageUrls[item.index] 会对 undefined 取下标，导致整个详情面板渲染崩溃白屏。
  assert.match(source, /const videoImageUrls = ref\(\{\}\)/)
  assert.match(source, /const previewImageUrl = ref\(''\)/)
})
