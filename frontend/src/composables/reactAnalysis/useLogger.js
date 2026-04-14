/**
 * 日志记录 Composable
 * 统一的日志记录和调试工具
 */
import { ref } from 'vue'

export function useLogger(options = {}) {
  const {
    prefix = '[App]',
    level = 'info', // debug | info | warn | error
    enableConsole = true,
    enableStorage = false,
    storageKey = 'app_logs'
  } = options

  // ========== 状态 ==========
  const logs = ref([])
  const maxLogs = 1000 // 最大日志数量

  // ========== 日志级别 ==========

  const levels = {
    debug: 0,
    info: 1,
    warn: 2,
    error: 3
  }

  const currentLevel = levels[level] || levels.info

  // ========== 方法 ==========

  /**
   * 添加日志
   * @param {string} level - 日志级别
   * @param {string} message - 消息
   * @param {object} data - 附加数据
   */
  const addLog = (level, message, data = null) => {
    const logEntry = {
      timestamp: new Date().toISOString(),
      level,
      message: `${prefix} ${message}`,
      data,
      stack: level === 'error' ? new Error().stack : null
    }

    // 添加到内存
    logs.value.push(logEntry)

    // 限制日志数量
    if (logs.value.length > maxLogs) {
      logs.value.shift()
    }

    // 输出到控制台
    if (enableConsole && shouldLog(level)) {
      outputToConsole(logEntry)
    }

    // 保存到存储
    if (enableStorage) {
      saveToStorage()
    }

    return logEntry
  }

  /**
   * 检查是否应该记录日志
   * @param {string} level - 日志级别
   * @returns {boolean}
   */
  const shouldLog = (level) => {
    return levels[level] >= currentLevel
  }

  /**
   * 输出到控制台
   * @param {object} logEntry - 日志条目
   */
  const outputToConsole = (logEntry) => {
    const { level, message, data, stack } = logEntry

    switch (level) {
      case 'debug':
        console.debug(message, data || '')
        break
      case 'info':
        console.log(message, data || '')
        break
      case 'warn':
        console.warn(message, data || '')
        break
      case 'error':
        console.error(message, data || '')
        if (stack) {
          console.error(stack)
        }
        break
    }
  }

  /**
   * 保存到本地存储
   */
  const saveToStorage = () => {
    try {
      const logsToSave = logs.value.slice(-100) // 只保存最近100条
      localStorage.setItem(storageKey, JSON.stringify(logsToSave))
    } catch (error) {
      console.error('[日志] 保存失败:', error)
    }
  }

  /**
   * 从本地存储加载
   */
  const loadFromStorage = () => {
    try {
      const stored = localStorage.getItem(storageKey)
      if (stored) {
        logs.value = JSON.parse(stored)
      }
    } catch (error) {
      console.error('[日志] 加载失败:', error)
    }
  }

  /**
   * Debug级别日志
   * @param {string} message - 消息
   * @param {object} data - 数据
   */
  const debug = (message, data = null) => {
    return addLog('debug', message, data)
  }

  /**
   * Info级别日志
   * @param {string} message - 消息
   * @param {object} data - 数据
   */
  const info = (message, data = null) => {
    return addLog('info', message, data)
  }

  /**
   * Warn级别日志
   * @param {string} message - 消息
   * @param {object} data - 数据
   */
  const warn = (message, data = null) => {
    return addLog('warn', message, data)
  }

  /**
   * Error级别日志
   * @param {string} message - 消息
   * @param {object} data - 数据
   */
  const error = (message, data = null) => {
    return addLog('error', message, data)
  }

  /**
   * 清空日志
   */
  const clear = () => {
    logs.value = []
    if (enableStorage) {
      localStorage.removeItem(storageKey)
    }
  }

  /**
   * 导出日志
   * @returns {string} JSON格式的日志
   */
  const exportLogs = () => {
    return JSON.stringify(logs.value, null, 2)
  }

  /**
   * 按级别筛选日志
   * @param {string} level - 日志级别
   * @returns {Array} 筛选后的日志
   */
  const filterByLevel = (level) => {
    return logs.value.filter(log => log.level === level)
  }

  /**
   * 按时间范围筛选日志
   * @param {Date} start - 开始时间
   * @param {Date} end - 结束时间
   * @returns {Array} 筛选后的日志
   */
  const filterByTimeRange = (start, end) => {
    return logs.value.filter(log => {
      const timestamp = new Date(log.timestamp)
      return timestamp >= start && timestamp <= end
    })
  }

  /**
   * 搜索日志
   * @param {string} keyword - 关键词
   * @returns {Array} 匹配的日志
   */
  const search = (keyword) => {
    const lowerKeyword = keyword.toLowerCase()
    return logs.value.filter(log =>
      log.message.toLowerCase().includes(lowerKeyword) ||
      (log.data && JSON.stringify(log.data).toLowerCase().includes(lowerKeyword))
    )
  }

  return {
    // 状态
    logs,

    // 方法
    debug,
    info,
    warn,
    error,
    clear,
    exportLogs,
    filterByLevel,
    filterByTimeRange,
    search,
    loadFromStorage
  }
}

/**
 * 创建性能日志记录器
 */
export function usePerformanceLogger() {
  const metrics = ref(new Map())

  /**
   * 开始计时
   * @param {string} label - 标签
   */
  const start = (label) => {
    metrics.value.set(label, {
      startTime: performance.now(),
      endTime: null,
      duration: null
    })
  }

  /**
   * 结束计时
   * @param {string} label - 标签
   * @returns {number} 持续时间（毫秒）
   */
  const end = (label) => {
    const metric = metrics.value.get(label)
    if (!metric) {
      console.warn(`[性能] 未找到标签: ${label}`)
      return 0
    }

    metric.endTime = performance.now()
    metric.duration = metric.endTime - metric.startTime

    console.log(`[性能] ${label}: ${metric.duration.toFixed(2)}ms`)

    return metric.duration
  }

  /**
   * 测量异步操作
   * @param {string} label - 标签
   * @param {function} fn - 异步函数
   * @returns {Promise} 函数结果
   */
  const measure = async (label, fn) => {
    start(label)
    try {
      const result = await fn()
      end(label)
      return result
    } catch (error) {
      end(label)
      throw error
    }
  }

  /**
   * 获取所有指标
   * @returns {Array} 指标列表
   */
  const getAllMetrics = () => {
    return Array.from(metrics.value.entries()).map(([label, metric]) => ({
      label,
      ...metric
    }))
  }

  /**
   * 清空指标
   */
  const clear = () => {
    metrics.value.clear()
  }

  return {
    start,
    end,
    measure,
    getAllMetrics,
    clear
  }
}
