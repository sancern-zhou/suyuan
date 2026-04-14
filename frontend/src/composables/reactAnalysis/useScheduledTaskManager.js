/**
 * 定时任务管理 Composable
 * 管理定时任务的列表、状态和操作
 */
import { ref, computed } from 'vue'

export function useScheduledTaskManager(tasksStore, options = {}) {
  const {
    autoRefresh = true,
    refreshInterval = 30000, // 30秒
    onRefresh = null
  } = options

  // ========== 状态 ==========
  const isRefreshing = ref(false)
  const lastRefreshTime = ref(null)
  const refreshTimer = ref(null)

  // ========== 计算属性 ==========

  /**
   * 任务列表
   */
  const tasks = computed(() => tasksStore.tasks || [])

  /**
   * 任务统计
   */
  const stats = computed(() => {
    const taskList = tasks.value
    return {
      total: taskList.length,
      active: taskList.filter(t => t.status === 'active').length,
      paused: taskList.filter(t => t.status === 'paused').length,
      failed: taskList.filter(t => t.status === 'failed').length
    }
  })

  /**
   * 按状态分组的任务
   */
  const tasksByStatus = computed(() => {
    const grouped = {
      active: [],
      paused: [],
      failed: [],
      completed: []
    }

    for (const task of tasks.value) {
      const status = task.status || 'unknown'
      if (grouped[status]) {
        grouped[status].push(task)
      }
    }

    return grouped
  })

  /**
   * 是否有任务
   */
  const hasTasks = computed(() => tasks.value.length > 0)

  // ========== 方法 ==========

  /**
   * 刷新任务列表
   */
  const refreshTasks = async () => {
    if (isRefreshing.value) return

    isRefreshing.value = true

    try {
      await tasksStore.fetchTasks()
      lastRefreshTime.value = new Date()

      if (onRefresh) {
        onRefresh(tasks.value)
      }
    } catch (error) {
      console.error('[定时任务] 刷新失败:', error)
      throw error
    } finally {
      isRefreshing.value = false
    }
  }

  /**
   * 切换任务状态（启用/禁用）
   * @param {string} taskId - 任务ID
   */
  const toggleTask = async (taskId) => {
    try {
      await tasksStore.toggleTask(taskId)
      await refreshTasks()
    } catch (error) {
      console.error('[定时任务] 切换失败:', error)
      throw error
    }
  }

  /**
   * 执行任务
   * @param {string} taskId - 任务ID
   */
  const executeTask = async (taskId) => {
    try {
      await tasksStore.executeTask(taskId)
      await refreshTasks()
    } catch (error) {
      console.error('[定时任务] 执行失败:', error)
      throw error
    }
  }

  /**
   * 编辑任务
   * @param {object} task - 任务对象
   */
  const editTask = (task) => {
    // 这里可以打开编辑对话框
    console.log('[定时任务] 编辑任务:', task.id)
    // TODO: 实现编辑对话框
  }

  /**
   * 删除任务
   * @param {string} taskId - 任务ID
   */
  const deleteTask = async (taskId) => {
    if (!confirm('确定要删除此任务吗？')) return

    try {
      await tasksStore.deleteTask(taskId)
      await refreshTasks()
    } catch (error) {
      console.error('[定时任务] 删除失败:', error)
      throw error
    }
  }

  /**
   * 获取任务状态文本
   * @param {string} status - 状态值
   * @returns {string} 状态文本
   */
  const getStatusText = (status) => {
    const statusMap = {
      active: '运行中',
      paused: '已暂停',
      completed: '已完成',
      failed: '失败'
    }
    return statusMap[status] || status
  }

  /**
   * 获取任务状态样式类
   * @param {string} status - 状态值
   * @returns {string} 样式类
   */
  const getStatusClass = (status) => {
    const classMap = {
      active: 'status-active',
      paused: 'status-paused',
      completed: 'status-completed',
      failed: 'status-failed'
    }
    return classMap[status] || 'status-unknown'
  }

  /**
   * 启动自动刷新
   */
  const startAutoRefresh = () => {
    if (!autoRefresh) return

    stopAutoRefresh()
    refreshTimer.value = setInterval(() => {
      refreshTasks()
    }, refreshInterval)
  }

  /**
   * 停止自动刷新
   */
  const stopAutoRefresh = () => {
    if (refreshTimer.value) {
      clearInterval(refreshTimer.value)
      refreshTimer.value = null
    }
  }

  /**
   * 格式化cron表达式
   * @param {string} cron - cron表达式
   * @returns {string} 格式化后的文本
   */
  const formatCron = (cron) => {
    // 简单的cron格式化
    // 可以使用更复杂的库来解析
    return cron || '未设置'
  }

  return {
    // 状态
    isRefreshing,
    lastRefreshTime,

    // 计算属性
    tasks,
    stats,
    tasksByStatus,
    hasTasks,

    // 方法
    refreshTasks,
    toggleTask,
    executeTask,
    editTask,
    deleteTask,
    getStatusText,
    getStatusClass,
    startAutoRefresh,
    stopAutoRefresh,
    formatCron
  }
}
