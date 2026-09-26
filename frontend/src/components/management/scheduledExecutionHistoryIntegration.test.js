import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const readSource = (relativePath) => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8'
)


test('scheduled task store requests a selected page of execution summaries', () => {
  const source = readSource('../../stores/scheduledTasks.js')

  assert.match(source, /async fetchTaskExecutions\(taskId, \{ page = 1, pageSize = 10 \} = \{\}\)/)
  assert.match(source, /page_size: String\(pageSize\)/)
  assert.match(source, /totalPages: Number\(data\?\.total_pages\)/)
})


test('results view only requests structured results for the selected task', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')

  assert.match(source, /const taskId = props\.task\?\.task_id/)
  assert.match(source, /store\.fetchTaskResults\(\{/)
  assert.match(source, /pageSize: pagination\.value\.pageSize/)
  assert.match(source, /pagination\.totalPages > 1/)
  assert.doesNotMatch(source, /fetchRecentExecutions\(/)
})


test('results view filters executions by date, station, and pollutant', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')

  assert.match(source, /v-model="filters\.startDate"/)
  assert.match(source, /v-model="filters\.endDate"/)
  assert.match(source, /v-model="filters\.stationId"/)
  assert.match(source, /v-model="filters\.pollutant"/)
  assert.match(source, /startDate: filters\.startDate/)
  assert.match(source, /endDate: filters\.endDate/)
  assert.match(source, /stationId: filters\.stationId/)
  assert.match(source, /pollutant: filters\.pollutant/)
  assert.match(source, /fetchTaskResultFacets/)
  // 筛选栏与列表同宽、均匀分布在一行
  assert.match(source, /\.results-toolbar \{[^}]*justify-content: space-between/)
  assert.match(source, /\.toolbar-field \{[^}]*flex: 1 1 130px/)
})


test('results view defaults the date filter to today when entering the page', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')

  assert.match(source, /function todayStr\(\)/)
  assert.match(source, /startDate: todayStr\(\)/)
  assert.match(source, /endDate: todayStr\(\)/)
  assert.match(source, /filters\.startDate = todayStr\(\)/)
  assert.match(source, /filters\.endDate = todayStr\(\)/)
})


test('results view renders each record as one row of database fields', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')

  assert.match(source, /<table class="record-table">/)
  assert.match(source, /<th class="col-time">时间<\/th>/)
  assert.match(source, /<th class="col-status">状态<\/th>/)
  assert.match(source, /<th class="col-city">城市<\/th>/)
  assert.match(source, /<th class="col-station">站点<\/th>/)
  assert.match(source, /<th class="col-pollutant">污染物<\/th>/)
  assert.match(source, /<th class="col-brief">结论<\/th>/)
  assert.match(source, /<th class="col-assets">产物<\/th>/)
  assert.match(source, /<th class="col-actions">操作<\/th>/)
  assert.match(source, /<td class="col-time">\{\{ formatRowTime\(record\) \}\}<\/td>/)
  assert.match(source, /record\.city \|\| '—'/)
  assert.match(source, /record\.station_name \|\| record\.station_id \|\| '—'/)
  assert.match(source, /record\.pollutant \|\| '—'/)
  assert.match(source, /date\.getFullYear\(\).*date\.getMonth\(\).*date\.getDate\(\)/s)
  assert.match(source, /date\.getHours\(\).*date\.getMinutes\(\)/s)
})


test('report and session actions live directly in the list rows', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')

  assert.match(source, /v-if="record\.has_report"/)
  assert.match(source, /@click="viewReport\(record\)"/)
  assert.match(source, /查看报告/)
  assert.match(source, /v-if="canOpenSession\(record\)"/)
  assert.match(source, /@click="enterSession\(record\)"/)
  assert.match(source, /进入会话/)
  assert.match(source, /function viewReport\(record\)/)
})


test('results view drops the detail panel and gives all space to the list', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')

  assert.doesNotMatch(source, /record-detail/)
  assert.doesNotMatch(source, /ImageLightbox/)
  assert.doesNotMatch(source, /selectedImages/)
  assert.match(source, /report-backdrop/)
  assert.match(source, /<iframe/)
  assert.match(source, /class="results-body"/)
})


test('report modal swaps fullscreen toggle for a multi-format download dropdown', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')
  const storeSource = readSource('../../stores/scheduledTasks.js')

  assert.doesNotMatch(source, /放大|还原|reportFullscreen/)
  assert.match(source, /⬇ 下载文档/)
  assert.match(source, /downloadMenuVisible/)
  assert.match(source, /store\.fetchTaskReportFormats\(/)
  assert.match(source, /:download="fmt\.filename"/)
  assert.match(storeSource, /async fetchTaskReportFormats\(executionId\)/)
})


test('results view opens the report with the preview ticket through the content endpoint', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')

  assert.match(source, /record\.has_report/)
  assert.match(source, /record\?\.preview_ticket/)
  assert.match(source, /\/report\/_t\/\$\{encodeURIComponent\(record\.preview_ticket\)\}\/report\.html/)
})


test('results view only enters the session for non-workflow tasks with a session', () => {
  const source = readSource('./ScheduledTaskResultsView.vue')

  assert.match(source, /const isWorkflowTask = computed\(\(\) => props\.task\?\.execution_mode === 'workflow'\)/)
  assert.match(source, /!isWorkflowTask\.value/)
  assert.match(source, /emit\('restore-execution-session', record\.session_id\)/)
})


test('scheduled task panel switches between tasks and execution results', () => {
  const panelSource = readSource('./ScheduledTasksPanel.vue')
  const viewSource = readSource('./ScheduledTaskResultsView.vue')

  assert.match(panelSource, /执行记录/)
  assert.match(panelSource, /openExecutionHistory\(task\)/)
  assert.match(panelSource, /返回任务列表/)
  assert.match(panelSource, /ScheduledTaskResultsView/)
  assert.match(panelSource, /@restore-execution-session="\$emit\('restore-execution-session', \$event\)"/)
  assert.match(viewSource, /task-results-view/)
})


test('task workspace embeds the shared results view and forwards session restore', () => {
  const source = readSource('./TaskExecutionWorkspace.vue')

  assert.match(source, /ScheduledTaskResultsView/)
  assert.match(source, /:task="task"/)
  assert.match(source, /@restore-execution-session="\$emit\('restore-execution-session', \$event\)"/)
  assert.doesNotMatch(source, /fetchRecentExecutions\(/)
})


test('scheduled and event task editor loads, selects, and restores one skill', () => {
  const panelSource = readSource('./ScheduledTasksPanel.vue')
  const storeSource = readSource('../../stores/scheduledTasks.js')

  assert.match(panelSource, /v-model="createForm\.skill_id"/)
  assert.match(panelSource, /skill_id: task\.skill_id \|\| ''/)
  assert.match(panelSource, /fetchAvailableSkills\(\)/)
  assert.match(panelSource, /事件任务和定时任务均可选择一个已发布 Skill/)
  assert.match(storeSource, /\$\{API_BASE\}\/skills/)
  assert.doesNotMatch(panelSource, /compatible|missing_tools|兼容/)
})


test('execution record selection restores the existing session in the chat workspace', () => {
  const layoutSource = readSource('../reactAnalysis/MainLayout.vue')
  const viewSource = readSource('../../views/ReactAnalysisView.vue')

  assert.match(layoutSource, /@restore-execution-session="\$emit\('restore-execution-session', \$event\)"/)
  assert.match(layoutSource, /'restore-execution-session'/)
  assert.match(viewSource, /@restore-execution-session="handleSessionRestoreAndClosePanel"/)
})

test('switching between task workspace entries opens the new page without toggling the panel off', () => {
  const viewSource = readSource('../../views/ReactAnalysisView.vue')
  const branchStart = viewSource.indexOf("actionId?.type === 'task-workspace'")
  const branchEnd = viewSource.indexOf('const newTaskMode', branchStart)
  const branch = viewSource.slice(branchStart, branchEnd)

  assert.ok(branchStart >= 0)
  assert.ok(branchEnd > branchStart)
  assert.match(branch, /taskWorkspaceTask\.value\?\.task_id !== task\.task_id/)
  assert.match(branch, /hideManagementPanel\(\)[\s\S]*showManagementPanel\('task-workspace'\)/)
})
