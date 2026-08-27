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


test('task workspace only requests executions for the selected task', () => {
  const source = readSource('./TaskExecutionWorkspace.vue')

  assert.match(source, /const taskId = props\.task\?\.task_id/)
  assert.match(source, /fetchTaskExecutions\(taskId, \{/)
  assert.match(source, /pageSize: pagination\.value\.pageSize/)
  assert.match(source, /pagination\.totalPages > 1/)
  assert.doesNotMatch(source, /fetchRecentExecutions\(/)
})


test('task workspace titles each record with its execution date and time', () => {
  const source = readSource('./TaskExecutionWorkspace.vue')

  assert.match(source, /<strong>\{\{ formatExecutionTitle\(record\) \}\}<\/strong>/)
  assert.match(source, /const taskName = record\?\.task_name \|\| props\.task\?\.name/)
  assert.match(source, /date\.getFullYear\(\).*date\.getMonth\(\).*date\.getDate\(\)/s)
  assert.match(source, /date\.getHours\(\).*date\.getMinutes\(\).*date\.getSeconds\(\)/s)
  assert.match(source, /return `\$\{executionTime\} \$\{taskName\}`/)
  assert.match(source, /Number\.isNaN\(date\.getTime\(\)\)\) return taskName/)
  assert.doesNotMatch(source, /时间未知的分析记录/)
})


test('scheduled task panel switches between tasks and execution records', () => {
  const source = readSource('./ScheduledTasksPanel.vue')

  assert.match(source, /执行记录/)
  assert.match(source, /openExecutionHistory\(task\)/)
  assert.match(source, /返回任务列表/)
  assert.match(source, /execution-history-list/)
  assert.match(source, /restore-execution-session/)
  assert.match(source, /canRestoreExecution\(execution\)/)
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
