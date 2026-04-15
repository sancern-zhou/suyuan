/**
 * 会话管理 Composable
 * 处理会话的创建、恢复、清理等操作
 */
import { ref, computed } from 'vue'
import { restoreSession, getSessionMessages } from '@/api/session'

export function useSessionManagement(store) {
  // ========== 状态 ==========
  const showSessionManager = ref(false)
  const sessionHistoryLoading = ref(false)
  const sessionHistoryData = ref([])
  const sessionHistoryStats = ref(null)

  // ========== 计算属性 ==========

  /**
   * 当前会话ID
   */
  const currentSessionId = computed(() => store.currentState.sessionId)

  /**
   * 当前消息数量
   */
  const currentMessageCount = computed(() => store.currentState.messages?.length || 0)

  /**
   * 是否正在分析
   */
  const isAnalyzing = computed(() => store.currentState.isAnalyzing)

  /**
   * 是否可以输入
   */
  const canInput = computed(() => store.canInput)

  // ========== 会话操作方法 ==========

  /**
   * 发送消息
   * @param {string|object} payload - 消息内容或包含选项的对象
   */
  const handleSend = async (payload) => {
    // 处理新的输入格式：可能是字符串（向后兼容）或对象
    const query = typeof payload === 'string' ? payload : payload.query
    const knowledgeBaseIds = typeof payload === 'object' ? payload.knowledgeBaseIds || [] : []
    const agentMode = typeof payload === 'object' ? payload.agentMode || store.agentMode : store.agentMode
    const attachments = typeof payload === 'object' ? payload.attachments || null : null

    // 构建分析选项
    const options = {
      knowledgeBaseIds,
      agentMode,  // ✅ 传递agentMode参数
      attachments  // ✅ 传递附件信息
    }

    // 使用store的分析方法
    await store.analyze(query, options)
  }

  /**
   * 暂停分析
   */
  const handlePause = async () => {
    await store.pauseAnalysis()
  }

  /**
   * 重新开始会话
   */
  const handleRestart = () => {
    store.restart()
  }

  /**
   * 切换分析状态
   */
  const toggleAnalysis = async () => {
    if (isAnalyzing.value) {
      await handlePause()
    } else {
      // 恢复分析（如果支持）
      console.log('恢复分析功能待实现')
    }
  }

  // ========== 会话恢复 ==========

  /**
   * 执行会话恢复的统一逻辑
   * @param {string} sessionId - 会话ID
   * @param {object} options - 恢复选项
   * @returns {object} 恢复结果
   */
  const doRestoreSession = async (sessionId, options = {}) => {
    const {
      messageLimit = 200,
      restoreOfficeDocs = true
    } = options

    try {
      // 1. 调用恢复API
      const restoreResult = await restoreSession(sessionId, { messageLimit })

      if (!restoreResult) {
        return {
          success: false,
          error: '恢复失败：API返回为空'
        }
      }

      // 后端返回格式：{ message: "...", session: {...} }
      const sessionData = restoreResult.session || restoreResult
      let messages = sessionData.conversation_history || []

      // 详细分析 final 消息（只根据type字段判断）
      const finalMessages = messages.filter(m => {
        const msgType = (m.type || '').toLowerCase()
        return msgType === 'final' || msgType === 'assistant'
      })

      // 【新增】检查是否有重复内容
      const contentMap = new Map()
      const contentDuplicates = []
      finalMessages.forEach(m => {
        const content = m.content?.substring(0, 100)
        if (content && contentMap.has(content)) {
          contentDuplicates.push({
            原消息ID: contentMap.get(content),
            重复消息ID: m.id,
            内容: content
          })
        } else if (content) {
          contentMap.set(content, m.id)
        }
      })

      // 过滤重复的final消息
      if (contentDuplicates.length > 0) {
        const duplicateIds = new Set(contentDuplicates.map(d => d.重复消息ID))
        messages = messages.filter(m => {
          if (duplicateIds.has(m.id)) {
            const msgType = (m.type || '').toLowerCase()
            return !(msgType === 'final' || msgType === 'assistant')
          }
          return true
        })
      }

      // 2. 提取可视化内容
      const visuals = extractVisualsFromMessages(messages)

      // 3. 更新store
      store.reset()
      store.setSessionId(sessionId)
      store.setMessages(messages)

      // 设置分页信息
      if (sessionData.has_more_messages !== undefined || sessionData.total_message_count !== undefined) {
        store.setPagination({
          hasMoreMessages: sessionData.has_more_messages || false,
          totalMessageCount: sessionData.total_message_count || messages.length,
          oldestSequence: sessionData.oldest_sequence,
          loadingMore: false
        })
      }

      // 无论 visuals 是否为空都要设置，确保清空旧会话的图表数据
      store.setVisualizationHistory(visuals)

      // 4. 恢复Office文档
      if (restoreOfficeDocs) {
        let officeDocs = sessionData.office_documents || []

        // 如果sessionData中没有，从消息中提取
        if (officeDocs.length === 0) {
          const extractedDocs = extractOfficeDocuments(messages)
          if (extractedDocs.length > 0) {
            officeDocs = extractedDocs
          }
        }

        if (officeDocs.length > 0) {
          store.setLastOfficeDocument(officeDocs[officeDocs.length - 1])
        }
      }

      return {
        success: true,
        messageCount: messages.length,
        visualCount: visuals.length,
        officeDocCount: restoreOfficeDocs ? (sessionData.office_documents || []).length : 0
      }

    } catch (error) {
      console.error('[会话恢复] 恢复会话时出错:', error)
      return {
        success: false,
        error: error.message
      }
    }
  }

  /**
   * 从消息中提取可视化内容
   * @param {array} messages - 消息列表
   * @returns {array} 可视化列表
   */
  const extractVisualsFromMessages = (messages) => {
    const visuals = []

    for (const msg of messages) {
      if (msg.type === 'observation' || msg.type === 'OBSERVATION') {
        const obs = msg.data?.observation
        if (!obs) continue

        // observation.visuals 在顶层
        if (Array.isArray(obs.visuals) && obs.visuals.length > 0) {
          visuals.push(...obs.visuals)
        }
        // 兼容旧路径：observation.data.visuals
        if (Array.isArray(obs.data?.visuals) && obs.data.visuals.length > 0) {
          visuals.push(...obs.data.visuals)
        }
        // 多工具结果：observation.tool_results[].result.visuals
        if (Array.isArray(obs.tool_results)) {
          for (const tr of obs.tool_results) {
            const rv = tr?.result?.visuals
            if (Array.isArray(rv) && rv.length > 0) {
              visuals.push(...rv)
            }
          }
        }
      }
    }

    // 去重（基于ID）
    const seen = new Set()
    const deduplicated = visuals.filter(v => {
      if (!v.id) return true
      if (seen.has(v.id)) return false
      seen.add(v.id)
      return true
    })

    return deduplicated
  }

  /**
   * 从消息中提取Office文档
   * @param {array} messages - 消息列表
   * @returns {array} Office文档列表
   */
  const extractOfficeDocuments = (messages) => {
    const docs = []

    for (const msg of messages) {
      if (msg.type === 'observation' || msg.type === 'OBSERVATION') {
        const obs = msg.data?.observation
        if (!obs) continue

        const obsData = obs.data
        if (!obsData) continue

        // 提取 pdf_preview 或 markdown_preview
        // 注意：数据结构需要符合 reactStore.setLastOfficeDocument 的期望格式
        if (obsData.pdf_preview) {
          docs.push({
            pdf_preview: obsData.pdf_preview,
            file_path: obsData.file_path || obsData.pdf_preview.pdf_path,
            generator: obsData.generator || 'word_processor'
          })
        } else if (obsData.markdown_preview) {
          docs.push({
            markdown_preview: obsData.markdown_preview,
            file_path: obsData.file_path,
            generator: obsData.generator || 'read_file'
          })
        }
      }
    }

    return docs
  }

  /**
   * 处理会话恢复
   * @param {string} sessionId - 会话ID
   */
  const handleSessionRestore = async (sessionId) => {
    const result = await doRestoreSession(sessionId, { messageLimit: 200, restoreOfficeDocs: true })

    if (result.success) {
      return true
    } else {
      console.error('[会话恢复] 恢复会话失败:', result.error)
      return false
    }
  }

  /**
   * 从侧边栏快速加载会话
   * @param {string} sessionId - 会话ID
   */
  const handleLoadSession = async (sessionId) => {
    const result = await doRestoreSession(sessionId, {
      messageLimit: 100,
      restoreOfficeDocs: true
    })

    return result.success
  }

  // ========== 会话历史管理 ==========

  /**
   * 刷新会话历史
   */
  const refreshSessionHistory = async () => {
    sessionHistoryLoading.value = true
    try {
      const response = await fetch('/api/sessions')
      if (!response.ok) throw new Error('Failed to fetch sessions')

      const data = await response.json()
      sessionHistoryData.value = data.sessions || []
      sessionHistoryStats.value = data.stats || null
    } catch (error) {
      console.error('Failed to refresh session history:', error)
    } finally {
      sessionHistoryLoading.value = false
    }
  }

  /**
   * 清理会话
   */
  const handleSessionCleanup = async () => {
    try {
      const response = await fetch('/api/sessions/cleanup', { method: 'POST' })
      if (!response.ok) throw new Error('Failed to cleanup sessions')

      const data = await response.json()
      alert(`已清理 ${data.deleted_count} 个过期会话`)
      await refreshSessionHistory()
    } catch (error) {
      console.error('Failed to cleanup sessions:', error)
      alert('清理失败: ' + error.message)
    }
  }

  /**
   * 删除会话
   * @param {string} sessionId - 会话ID
   */
  const deleteSession = async (sessionId) => {
    if (!confirm('确定要删除此会话吗？此操作不可恢复。')) return

    try {
      const response = await fetch(`/api/sessions/${sessionId}`, {
        method: 'DELETE'
      })

      if (!response.ok) throw new Error('Failed to delete session')

      await refreshSessionHistory()
      return true
    } catch (error) {
      console.error('Failed to delete session:', error)
      alert('删除失败: ' + error.message)
      return false
    }
  }

  // ========== 会话管理器控制 ==========

  /**
   * 打开会话管理器
   */
  const openSessionManager = () => {
    showSessionManager.value = true
    refreshSessionHistory()
  }

  /**
   * 关闭会话管理器
   */
  const closeSessionManager = () => {
    showSessionManager.value = false
  }

  return {
    // 状态
    showSessionManager,
    sessionHistoryLoading,
    sessionHistoryData,
    sessionHistoryStats,

    // 计算属性
    currentSessionId,
    currentMessageCount,
    isAnalyzing,
    canInput,

    // 会话操作
    handleSend,
    handlePause,
    handleRestart,
    toggleAnalysis,

    // 会话恢复
    handleSessionRestore,
    handleLoadSession,
    doRestoreSession,

    // 会话历史
    refreshSessionHistory,
    handleSessionCleanup,
    deleteSession,

    // 会话管理器
    openSessionManager,
    closeSessionManager
  }
}
