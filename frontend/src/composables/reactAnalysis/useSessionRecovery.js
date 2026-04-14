/**
 * 会话恢复 Composable
 * 处理会话恢复、消息加载和状态同步
 */
import { ref } from 'vue'
import { restoreSession, getSessionMessages } from '@/api/session'

export function useSessionRecovery(store, options = {}) {
  const {
    initialMessageLimit = 5, // 初始加载消息数
    onProgress = null, // 进度回调
    onComplete = null, // 完成回调
    onError = null // 错误回调
  } = options

  // ========== 状态 ==========
  const isRestoring = ref(false)
  const loadingMore = ref(false)
  const currentSessionId = ref(null)
  const messageCount = ref(0)
  const visualCount = ref(0)

  // ========== 方法 ==========

  /**
   * 恢复会话
   * @param {string} sessionId - 会话ID
   * @param {object} options - 恢复选项
   * @returns {Promise<object>} 恢复结果
   */
  const restoreSessionById = async (sessionId, restoreOptions = {}) => {
    const {
      messageLimit = initialMessageLimit,
      restoreOfficeDocs = true
    } = restoreOptions

    isRestoring.value = true
    currentSessionId.value = sessionId

    try {
      console.log(`[会话恢复] 开始恢复会话 ${sessionId.substring(0, 12)}...`)

      // 1. 调用恢复API
      const restoreResult = await restoreSession(sessionId)
      if (!restoreResult.success) {
        throw new Error(restoreResult.message || '恢复失败')
      }

      // 2. 获取会话消息
      const messagesResult = await getSessionMessages(sessionId, {
        limit: messageLimit,
        offset: 0
      })

      if (!messagesResult.success) {
        throw new Error(messagesResult.message || '获取消息失败')
      }

      const messages = messagesResult.data.messages || []
      messageCount.value = messages.length

      // 3. 提取可视化内容
      const visuals = extractVisualsFromMessages(messages)
      visualCount.value = visuals.length

      // 4. 提取Office文档
      const officeDocs = restoreOfficeDocs ? extractOfficeDocuments(messages) : []

      // 5. 更新store
      updateStoreState(sessionId, messages, visuals, officeDocs)

      const result = {
        success: true,
        sessionId,
        messageCount: messages.length,
        visualCount: visuals.length,
        officeDocCount: officeDocs.length
      }

      // 触发回调
      if (onComplete) onComplete(result)

      return result
    } catch (error) {
      console.error('[会话恢复] 恢复会话时出错:', error)
      if (onError) onError(error)
      return {
        success: false,
        error: error.message
      }
    } finally {
      isRestoring.value = false
    }
  }

  /**
   * 从消息中提取可视化内容
   * @param {Array} messages - 消息列表
   * @returns {Array} 可视化列表
   */
  const extractVisualsFromMessages = (messages) => {
    const visuals = []

    for (const msg of messages) {
      if (msg.type === 'observation' && msg.data?.observation?.data?.visuals) {
        visuals.push(...msg.data.observation.data.visuals)
      }
    }

    // 去重（基于ID）
    const seen = new Set()
    return visuals.filter(v => {
      if (!v.id) return true
      if (seen.has(v.id)) return false
      seen.add(v.id)
      return true
    })
  }

  /**
   * 从消息中提取Office文档
   * @param {Array} messages - 消息列表
   * @returns {Array} Office文档列表
   */
  const extractOfficeDocuments = (messages) => {
    const docs = []

    for (const msg of messages) {
      if (msg.type === 'observation' && msg.data?.observation?.data?.pdf_preview) {
        docs.push(msg.data.observation.data.pdf_preview)
      }
    }

    return docs
  }

  /**
   * 更新store状态
   * @param {string} sessionId - 会话ID
   * @param {Array} messages - 消息列表
   * @param {Array} visuals - 可视化列表
   * @param {Array} officeDocs - Office文档列表
   */
  const updateStoreState = (sessionId, messages, visuals, officeDocs) => {
    // 更新会话ID
    store.setSessionId(sessionId)

    // 更新消息
    store.setMessages(messages)

    // 更新可视化历史
    if (visuals.length > 0) {
      store.setVisualizationHistory(visuals)
    }

    // 更新Office文档
    if (officeDocs.length > 0) {
      const latestDoc = officeDocs[officeDocs.length - 1]
      store.setLastOfficeDocument(latestDoc)
    }
  }

  /**
   * 加载更多消息
   * @param {number} offset - 偏移量
   * @param {number} limit - 限制数量
   * @returns {Promise<object>} 加载结果
   */
  const loadMoreMessages = async (offset = null, limit = 20) => {
    if (!currentSessionId.value || loadingMore.value) {
      return { success: false, error: '没有活动会话或正在加载' }
    }

    loadingMore.value = true

    try {
      const actualOffset = offset ?? messageCount.value

      const result = await getSessionMessages(currentSessionId.value, {
        limit,
        offset: actualOffset
      })

      if (!result.success) {
        throw new Error(result.message || '加载消息失败')
      }

      const newMessages = result.data.messages || []
      messageCount.value += newMessages.length

      // 追加消息到store
      store.appendMessages(newMessages)

      return {
        success: true,
        messageCount: newMessages.length,
        hasMore: result.data.hasMore || false
      }
    } catch (error) {
      console.error('[加载更多消息] 加载失败:', error)
      return { success: false, error: error.message }
    } finally {
      loadingMore.value = false
    }
  }

  /**
   * 重置状态
   */
  const reset = () => {
    isRestoring.value = false
    loadingMore.value = false
    currentSessionId.value = null
    messageCount.value = 0
    visualCount.value = 0
  }

  return {
    // 状态
    isRestoring,
    loadingMore,
    currentSessionId,
    messageCount,
    visualCount,

    // 方法
    restoreSessionById,
    loadMoreMessages,
    extractVisualsFromMessages,
    extractOfficeDocuments,
    reset
  }
}
