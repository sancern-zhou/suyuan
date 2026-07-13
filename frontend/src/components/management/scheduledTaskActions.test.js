import assert from 'node:assert/strict'
import test from 'node:test'

import {
  deleteScheduledTask,
  executeScheduledTask,
  refreshScheduledTaskManagement,
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
    async deleteTask(taskId) { calls.push(['deleteTask', taskId]) }
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
