import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const readSource = (relativePath) => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8'
)


test('scheduled task store requests execution history with the selected limit', () => {
  const source = readSource('../../stores/scheduledTasks.js')

  assert.match(source, /async fetchTaskExecutions\(taskId, limit = 50\)/)
  assert.match(source, /\$\{API_BASE\}\/\$\{taskId\}\/executions\?limit=\$\{limit\}/)
})


test('task workspace only requests executions for the selected task', () => {
  const source = readSource('./TaskExecutionWorkspace.vue')

  assert.match(source, /const taskId = props\.task\?\.task_id/)
  assert.match(source, /fetchTaskExecutions\(taskId, 50\)/)
  assert.doesNotMatch(source, /fetchRecentExecutions\(/)
})


test('task workspace titles each record with its execution date and time', () => {
  const source = readSource('./TaskExecutionWorkspace.vue')

  assert.match(source, /<strong>\{\{ formatExecutionTitle\(record\.started_at\) \}\}<\/strong>/)
  assert.match(source, /date\.getFullYear\(\).*date\.getMonth\(\).*date\.getDate\(\)/s)
  assert.match(source, /date\.getHours\(\).*date\.getMinutes\(\).*date\.getSeconds\(\)/s)
  assert.match(source, /return `\$\{executionTime\} 分析记录`/)
  assert.doesNotMatch(source, /<strong>\{\{ record\.task_name/)
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
