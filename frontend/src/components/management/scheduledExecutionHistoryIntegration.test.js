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


test('scheduled task panel switches between tasks and execution records', () => {
  const source = readSource('./ScheduledTasksPanel.vue')

  assert.match(source, /执行记录/)
  assert.match(source, /openExecutionHistory\(task\)/)
  assert.match(source, /返回任务列表/)
  assert.match(source, /execution-history-list/)
  assert.match(source, /restore-execution-session/)
  assert.match(source, /canRestoreExecution\(execution\)/)
})


test('execution record selection restores the existing session in the chat workspace', () => {
  const layoutSource = readSource('../reactAnalysis/MainLayout.vue')
  const viewSource = readSource('../../views/ReactAnalysisView.vue')

  assert.match(layoutSource, /@restore-execution-session="\$emit\('restore-execution-session', \$event\)"/)
  assert.match(layoutSource, /'restore-execution-session'/)
  assert.match(viewSource, /@restore-execution-session="handleSessionRestoreAndClosePanel"/)
})
