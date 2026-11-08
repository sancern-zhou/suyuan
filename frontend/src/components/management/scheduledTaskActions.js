const requireTaskId = (task) => {
  const taskId = task?.task_id
  if (!taskId) throw new Error('Task is missing task_id')
  return taskId
}


export const refreshScheduledTaskManagement = async (store) => {
  // 任务列表与统计相互独立，并行请求，避免串行等待拖慢面板首屏。
  await Promise.all([
    store.fetchTasks(),
    store.fetchStats()
  ])
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
