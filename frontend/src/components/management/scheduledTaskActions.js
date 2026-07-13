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

