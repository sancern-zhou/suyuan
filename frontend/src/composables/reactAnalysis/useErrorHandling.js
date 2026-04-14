/**
 * 错误处理 Composable
 * 统一的错误处理和用户提示
 */
import { ref, computed } from 'vue'

export function useErrorHandling(options = {}) {
  const {
    showAlert = true, // 是否显示alert
    logToConsole = true, // 是否记录到控制台
    onError = null // 错误回调
  } = options

  // ========== 状态 ==========
  const errors = ref([])
  const lastError = ref(null)

  // ========== 计算属性 ==========

  /**
   * 是否有错误
   */
  const hasErrors = computed(() => errors.value.length > 0)

  /**
   * 错误数量
   */
  const errorCount = computed(() => errors.value.length)

  /**
   * 最近的错误
   */
  const recentErrors = computed(() => {
    return errors.value.slice(-5) // 最近5个错误
  })

  // ========== 方法 ==========

  /**
   * 处理错误
   * @param {Error|string} error - 错误对象或字符串
   * @param {object} context - 错误上下文
   */
  const handleError = (error, context = {}) => {
    const errorObj = normalizeError(error, context)

    // 记录到控制台
    if (logToConsole) {
      console.error('[错误处理]', errorObj)
    }

    // 添加到错误列表
    errors.value.push(errorObj)
    lastError.value = errorObj

    // 显示alert
    if (showAlert) {
      alert(errorObj.message)
    }

    // 触发回调
    if (onError) {
      onError(errorObj)
    }

    return errorObj
  }

  /**
   * 规范化错误对象
   * @param {Error|string} error - 原始错误
   * @param {object} context - 上下文
   * @returns {object} 规范化后的错误对象
   */
  const normalizeError = (error, context) => {
    const timestamp = new Date().toISOString()

    if (error instanceof Error) {
      return {
        message: error.message,
        stack: error.stack,
        name: error.name,
        timestamp,
        ...context
      }
    }

    if (typeof error === 'string') {
      return {
        message: error,
        timestamp,
        ...context
      }
    }

    return {
      message: '未知错误',
      timestamp,
      ...context,
      original: error
    }
  }

  /**
   * 清除所有错误
   */
  const clearAll = () => {
    errors.value = []
    lastError.value = null
  }

  /**
   * 清除特定索引的错误
   * @param {number} index - 错误索引
   */
  const clearAt = (index) => {
    if (index >= 0 && index < errors.value.length) {
      errors.value.splice(index, 1)
    }
  }

  /**
   * 重试操作
   * @param {function} operation - 要重试的操作
   * @param {number} maxRetries - 最大重试次数
   * @returns {Promise} 操作结果
   */
  const retry = async (operation, maxRetries = 3) => {
    let lastError = null

    for (let i = 0; i < maxRetries; i++) {
      try {
        return await operation()
      } catch (error) {
        lastError = error
        if (i < maxRetries - 1) {
          // 等待一段时间后重试
          await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)))
        }
      }
    }

    // 所有重试都失败
    handleError(lastError, {
      context: 'retry',
      attempts: maxRetries
    })

    throw lastError
  }

  /**
   * 创建错误边界
   * @param {function} fallback - 降级函数
   * @returns {function} 包装后的函数
   */
  const createErrorBoundary = (fallback) => {
    return async (fn, ...args) => {
      try {
        return await fn(...args)
      } catch (error) {
        handleError(error, {
          context: 'errorBoundary'
        })

        if (fallback) {
          return fallback(error, ...args)
        }

        throw error
      }
    }
  }

  /**
   * 异步错误处理包装器
   * @param {function} fn - 异步函数
   * @returns {function} 包装后的函数
   */
  const withErrorHandling = (fn) => {
    return async (...args) => {
      try {
        return await fn(...args)
      } catch (error) {
        handleError(error)
        throw error
      }
    }
  }

  return {
    // 状态
    errors,
    lastError,

    // 计算属性
    hasErrors,
    errorCount,
    recentErrors,

    // 方法
    handleError,
    clearAll,
    clearAt,
    retry,
    createErrorBoundary,
    withErrorHandling
  }
}

/**
 * 创建特定类型的错误处理器
 */
export function createApiErrorHandler() {
  const { handleError, clearAll } = useErrorHandling()

  return {
    /**
     * 处理API错误
     * @param {Response} response - 响应对象
     * @returns {Promise<Error>} 错误对象
     */
    async handleApiError(response) {
      let message = `请求失败 (${response.status})`

      try {
        const data = await response.json()
        message = data.message || data.error || message
      } catch (e) {
        // 无法解析JSON，使用默认消息
      }

      return handleError(new Error(message), {
        type: 'api',
        status: response.status,
        url: response.url
      })
    },

    clearAll
  }
}
