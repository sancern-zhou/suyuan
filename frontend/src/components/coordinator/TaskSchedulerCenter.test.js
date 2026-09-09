import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readSource = () => readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')

test('task scheduler center exposes todo and scheduled tabs', async () => {
  const source = await readSource()

  assert.match(source, /待办任务/)
  assert.match(source, /定时任务/)
  assert.match(source, /activeTab = ref\('todo'\)/)
  assert.match(source, /fetchRecentExecutions\(\{ pageSize: 50 \}\)/)
  assert.match(source, /listJiangsuSmartEventTasks\(\{ limit: 100 \}\)/)
  assert.match(source, /execution\.trigger_type === 'scheduled'/)
  assert.match(source, /executionToAttentionItem\(execution\)/)
  assert.match(source, /smartEventTasks\.value\.map\(card => toTodoCard/)
  assert.match(source, /sourceTask: sourceTask/)
})
