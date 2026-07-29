import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canRestoreExecution,
  deleteScheduledTask,
  executionStatusMeta,
  executeScheduledTask,
  loadScheduledTaskExecutions,
  refreshScheduledTaskManagement,
  sortExecutionsNewestFirst,
  toggleScheduledTask
} from './scheduledTaskActions.js'


const fakeStore = () => {
  const calls = []
  return {
    calls,
    async fetchTasks() { calls.push(['fetchTasks']) },
    async fetchStats() { calls.push(['fetchStats']) },
    async enableTask(taskId) { calls.push(['enableTask', taskId]) },
    async disableTask(taskId) { calls.push(['disableTask', taskId]) },
    async executeTaskNow(taskId) { calls.push(['executeTaskNow', taskId]) },
    async deleteTask(taskId) { calls.push(['deleteTask', taskId]) },
    async fetchTaskExecutions(taskId, limit) {
      calls.push(['fetchTaskExecutions', taskId, limit])
      return [{ execution_id: 'exec-1' }]
    }
  }
}


test('refresh loads tasks and statistics', async () => {
  const store = fakeStore()

  await refreshScheduledTaskManagement(store)

  assert.deepEqual(store.calls, [['fetchTasks'], ['fetchStats']])
})


test('toggle uses task_id and current enabled state', async () => {
  const store = fakeStore()

  await toggleScheduledTask(store, { task_id: 'enabled-task', enabled: true })
  await toggleScheduledTask(store, { task_id: 'disabled-task', enabled: false })

  assert.deepEqual(store.calls, [
    ['disableTask', 'enabled-task'],
    ['enableTask', 'disabled-task']
  ])
})


test('execute and delete use task_id', async () => {
  const store = fakeStore()

  await executeScheduledTask(store, { task_id: 'task-1' })
  await deleteScheduledTask(store, { task_id: 'task-1' })

  assert.deepEqual(store.calls, [
    ['executeTaskNow', 'task-1'],
    ['deleteTask', 'task-1']
  ])
})


test('loads up to fifty execution records for one task', async () => {
  const store = fakeStore()

  const result = await loadScheduledTaskExecutions(store, { task_id: 'task-1' })

  assert.deepEqual(result, [{ execution_id: 'exec-1' }])
  assert.deepEqual(store.calls, [['fetchTaskExecutions', 'task-1', 50]])
})


test('sorts executions newest first without mutating the API response', () => {
  const records = [
    { execution_id: 'old', started_at: '2026-07-16T08:00:00' },
    { execution_id: 'new', started_at: '2026-07-17T08:00:00' }
  ]

  const sorted = sortExecutionsNewestFirst(records)

  assert.deepEqual(sorted.map(record => record.execution_id), ['new', 'old'])
  assert.deepEqual(records.map(record => record.execution_id), ['old', 'new'])
})


test('maps every backend execution status to a user-facing label', () => {
  assert.deepEqual(executionStatusMeta('running'), { key: 'running', label: '执行中' })
  assert.deepEqual(executionStatusMeta('success'), { key: 'success', label: '成功' })
  assert.deepEqual(executionStatusMeta('failed'), { key: 'failed', label: '失败' })
  assert.deepEqual(executionStatusMeta('timeout'), { key: 'timeout', label: '超时' })
  assert.deepEqual(executionStatusMeta('cancelled'), { key: 'cancelled', label: '已取消' })
  assert.deepEqual(executionStatusMeta('pending'), { key: 'pending', label: '等待执行' })
  assert.deepEqual(executionStatusMeta('unexpected'), { key: 'unknown', label: '未知' })
})


test('only executions with a session id can restore a conversation', () => {
  assert.equal(canRestoreExecution({ session_id: 'session-1' }), true)
  assert.equal(canRestoreExecution({ session_id: '' }), false)
  assert.equal(canRestoreExecution({}), false)
})
