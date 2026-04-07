/**
 * 会话恢复功能的统一 Composable
 *
 * 统一处理会话恢复的所有逻辑，包括：
 * - 调用后端 API
 * - 消息格式转换
 * - 状态更新
 * - 可视化恢复
 * - 分页状态恢复
 * - 错误处理
 *
 * 替代原来分散在多个位置的重复代码（quickLoadSession、handleLoadSession、handleSessionRestore）
 */

import { ref } from 'vue'
import { restoreSession, getSessionMessages } from '@/api/session'

/**
 * 统一的会话恢复逻辑
 *
 * @param {Object} options - 配置选项
 * @param {Object} options.store - ReactStore 实例
 * @param {Function} options.switchMode - 模式切换函数
 * @param {Function} options.convertHistoryMessages - 消息转换函数
 * @param {Function} options.restoreVisualizations - 可视化恢复函数
 * @param {boolean} options.showAlert - 是否显示 alert 提示（默认 false）
 * @param {boolean} options.clearMessages - 是否清空当前消息（默认 true）
 * @returns {Object} 恢复结果 { success, error, messageCount, visualCount }
 */
export function useSessionRestore(options) {
  const {
    store,
    switchMode,
    convertHistoryMessages,
    restoreVisualizations,
    showAlert = false,
    clearMessages = true
  } = options

  const isLoading = ref(false)
  const error = ref(null)

  /**
   * 恢复会话的主函数
   *
   * @param {string} sessionId - 会话ID
   * @param {number} messageLimit - 首次加载的消息数量（默认5）
   * @returns {Promise<Object>} 恢复结果
   */
  const restoreSession = async (sessionId, messageLimit = 5) => {
    if (isLoading.value) {
      console.warn('[useSessionRestore] 正在恢复中，请勿重复调用')
      return { success: false, error: '正在恢复中' }
    }

    isLoading.value = true
    error.value = null

    try {
      console.log('[useSessionRestore] 开始恢复会话:', sessionId, '消息限制:', messageLimit)

      // 1. 调用后端 API
      const response = await restoreSession(sessionId, messageLimit)
      console.log('[useSessionRestore] API响应:', response)

      const sessionData = response.session

      // 2. 验证会话数据
      const hasConversationHistory = sessionData?.conversation_history?.length > 0
      const hasDataOrVisuals = (sessionData?.data_ids?.length > 0) ||
                              (sessionData?.visual_ids?.length > 0) ||
                              sessionData?.last_result

      if (!hasConversationHistory && !hasDataOrVisuals) {
        throw new Error('会话数据为空')
      }

      // 3. 提取并切换模式
      const mode = extractModeFromSession(sessionData, sessionId)
      if (mode && switchMode) {
        await switchMode(mode, false) // false = 不清空消息，稍后统一处理
      }

      // 4. 清空当前消息（如果需要）
      if (clearMessages && store.currentState.messages.length > 0) {
        store.setMessages([])
      }

      // 5. 转换并恢复消息
      let messageCount = 0
      if (hasConversationHistory) {
        const convertedHistory = convertHistoryMessages(sessionData.conversation_history)
        store.setMessages(convertedHistory)
        messageCount = convertedHistory.length
        console.log('[useSessionRestore] 消息已恢复，数量:', messageCount)
      }

      // 6. 恢复会话状态
      store.setSessionId(sessionData.session_id)
      if (sessionData.state === 'completed') {
        store.setComplete(true)
      }
      if (sessionData.last_result) {
        store.currentState.lastExpertResults = sessionData.last_result
      }

      // 7. 恢复分页状态
      if (sessionData.has_more_messages !== undefined) {
        store.setPagination({
          hasMoreMessages: sessionData.has_more_messages,
          totalMessageCount: sessionData.total_message_count || 0,
          oldestSequence: sessionData.oldest_sequence ?? null
        })
      }

      // 8. 恢复可视化
      let visualCount = 0
      if (restoreVisualizations) {
        visualCount = await restoreVisualizations(sessionData)
      }

      console.log('[useSessionRestore] 会话恢复成功:', {
        sessionId: sessionData.session_id.substring(0, 12) + '...',
        messageCount,
        visualCount,
        hasMore: sessionData.has_more_messages
      })

      // 9. 显示成功提示（如果需要）
      if (showAlert) {
        alert(`会话 ${sessionId.substring(0, 12)}... 已恢复`)
      }

      return {
        success: true,
        messageCount,
        visualCount,
        hasMoreMessages: sessionData.has_more_messages
      }

    } catch (err) {
      console.error('[useSessionRestore] 恢复失败:', err)
      error.value = err

      if (showAlert) {
        alert('会话恢复失败: ' + err.message)
      }

      return {
        success: false,
        error: err.message
      }
    } finally {
      isLoading.value = false
    }
  }

  /**
   * 从会话数据中提取模式
   */
  function extractModeFromSession(sessionData, sessionId) {
    // 优先级：metadata.mode > session_id前缀
    if (sessionData.metadata?.mode) {
      return sessionData.metadata.mode
    }

    // 从 sessionId 提取模式（假设格式为 "mode_uuid"）
    if (sessionId.includes('_')) {
      const parts = sessionId.split('_')
      const potentialMode = parts[0]
      if (['assistant', 'expert'].includes(potentialMode)) {
        return potentialMode
      }
    }

    return null // 保持当前模式
  }

  return {
    isLoading,
    error,
    restoreSession
  }
}

/**
 * 便捷函数：直接使用（不依赖 setup 语法）
 *
 * 使用示例：
 * ```javascript
 * import { restoreSessionHandler } from '@/composables/useSessionRestore'
 *
 * const result = await restoreSessionHandler(sessionId, {
 *   store,
 *   switchMode,
 *   convertHistoryMessages,
 *   restoreVisualizations
 * })
 * ```
 */
export async function restoreSessionHandler(sessionId, options = {}) {
  const { restoreSession } = useSessionRestore(options)
  return await restoreSession(sessionId, options.messageLimit || 5)
}
