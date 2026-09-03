const requireTaskId = (task) => {
  const taskId = task?.task_id
  if (!taskId) throw new Error('Task is missing task_id')
  return taskId
}


export const refreshScheduledTaskManagement = async (store) => {
  await store.fetchTasks()
  await store.fetchStats()
}


export const toggleScheduledTask = async (store, task) => {
  const taskId = requireTaskId(task)
  return task.enabled
    ? store.disableTask(taskId)
    : store.enableTask(taskId)
}


export const executeScheduledTask = (store, task) => (
  store.executeTaskNow(requireTaskId(task))
)


export const deleteScheduledTask = (store, task) => (
  store.deleteTask(requireTaskId(task))
)


export const loadScheduledTaskExecutions = (store, task, options = {}) => (
  store.fetchTaskExecutions(requireTaskId(task), options)
)


export const sortExecutionsNewestFirst = (executions = []) => (
  [...executions].sort((left, right) => {
    const leftTime = Date.parse(left?.started_at || '') || 0
    const rightTime = Date.parse(right?.started_at || '') || 0
    return rightTime - leftTime
  })
)


const EXECUTION_STATUS_META = {
  pending: { key: 'pending', label: '等待执行' },
  running: { key: 'running', label: '执行中' },
  success: { key: 'success', label: '成功' },
  failed: { key: 'failed', label: '失败' },
  timeout: { key: 'timeout', label: '超时' },
  cancelled: { key: 'cancelled', label: '已取消' }
}


export const executionStatusMeta = (status) => (
  EXECUTION_STATUS_META[status] || { key: 'unknown', label: '未知' }
)


export const canRestoreExecution = (execution) => (
  typeof execution?.session_id === 'string' && execution.session_id.trim().length > 0
)
