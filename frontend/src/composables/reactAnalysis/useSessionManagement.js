import { authFetch } from '@/auth/http.js'
/**
 * 会话管理 Composable
 * 处理会话的创建、恢复、清理等操作
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { preserveCatalogFields } from '@/components/management/sessionHistoryAccess.js'
import { restoredConversationPolicy } from '@/components/socialHistoryReadOnly.js'
import { resolveRestoredAgentMode } from '@/components/agentPlatform/restoreModePolicy.js'
import { filterConversationHistory } from '@/components/conversationListPolicy.js'
import { AGENT_MODE_IDS } from '@/config/agentModes.js'
import { projectConfig, resolveProjectDefaultAgentMode } from '@/config/projectConfig.js'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { chooseRestoredResource } from '@/services/sessionResourceLifecycle.js'
import { confirmResourcePreviewLeave } from '@/services/resourcePreviewLeaveGuard.js'
import {
  listSessions,
  restoreSession,
  getSessionMessages,
  deleteSession as deleteSessionRequest,
  markSessionCase,
  unmarkSessionCase
} from '@/api/session'

export function useSessionManagement(store) {
  const resourceStore = useSessionResourceStore()
  // ========== 状态 ==========
  const showSessionManager = ref(false)
  const sessionHistoryLoading = ref(false)
  const persistedSessionHistoryData = ref([])
  const sessionHistoryStats = ref(null)
  let autoRefreshTimer = null
  let refreshInFlight = null
  let restoreRequestToken = 0

  const localSessionHistoryData = computed(() => {
    return Object.values(store.sessionStates || {})
      .filter(session => session.sessionId)
      .map(session => {
        const firstUser = session.messages?.find(m => m.type === 'user')
        const lastMessage = session.messages?.[session.messages.length - 1]
        const hasError = session.messages?.some(m => m.type === 'error') || !!session.error
        return {
          session_id: session.sessionId,
          query: firstUser?.content || '新对话',
          updated_at: lastMessage?.timestamp || new Date().toISOString(),
          created_at: session.createdAt,
          has_error: hasError,
          state: session.isAnalyzing ? 'running' : (hasError ? 'error' : 'completed'),
          status: session.isAnalyzing ? 'running' : (hasError ? 'error' : 'completed'),
          is_running: !!session.isAnalyzing,
          is_local: true,
          message_count: session.messages?.length || 0
        }
      })
  })

  const sessionHistoryData = computed(() => {
    const byId = new Map()
    for (const session of persistedSessionHistoryData.value) {
      byId.set(session.session_id, preserveCatalogFields({}, {
        ...session,
        status: session.status || session.state || (session.has_error ? 'error' : 'completed')
      }))
    }
    for (const session of localSessionHistoryData.value) {
      byId.set(
        session.session_id,
        preserveCatalogFields(byId.get(session.session_id) || {}, session)
      )
    }

    return filterConversationHistory(Array.from(byId.values())).sort((a, b) => {
      if (!!a.is_running !== !!b.is_running) return a.is_running ? -1 : 1
      return new Date(b.updated_at || 0) - new Date(a.updated_at || 0)
    })
  })

  const applySessionCaseState = (sessionId, isCase, metadataOverride = null) => {
    const markedAt = new Date().toISOString()
    persistedSessionHistoryData.value = persistedSessionHistoryData.value.map(session => {
      if (session.session_id !== sessionId) return session

      const metadata = metadataOverride
        ? { ...metadataOverride }
        : {
            ...(session.metadata || {}),
            is_case: isCase,
            ...(isCase ? { case_marked_at: markedAt } : {})
          }

      if (!isCase) {
        delete metadata.case_marked_at
      }

      return {
        ...session,
        metadata
      }
    })
  }

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
  const currentConversationPolicy = computed(() => restoredConversationPolicy(
    store.currentState?.conversationAccess || {}
  ))

  // ========== 会话操作方法 ==========

  /**
   * 发送消息
   * @param {string|object} payload - 消息内容或包含选项的对象
   */
  const handleSend = async (payload) => {
    if (currentConversationPolicy.value.readOnly) return false
    const query = payload.query
    const knowledgeBaseIds = payload.knowledgeBaseIds || []
    const agentMode = payload.agentMode || store.agentMode
    const skillIds = payload.skillIds || []
    const contextRefs = payload.contextRefs || []
    const activeContexts = Array.isArray(payload.activeContexts) ? payload.activeContexts : null
    const messageAttachments = payload.messageAttachments || []
    const modelTier = payload.modelTier || 'auto'

    // 构建分析选项
    const options = {
      knowledgeBaseIds,
      agentMode,  // ✅ 传递agentMode参数
      modelTier,
      skillIds,
      contextRefs,
      activeContexts,
      messageAttachments,
      onAccepted: payload.onAccepted
    }

    // 使用store的分析方法
    try {
      await store.analyze(query, options)
    } finally {
      refreshSessionHistory({ silent: true })
    }
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

  const hasRestorableLocalState = sessionState => {
    if (!sessionState) return false
    return (Array.isArray(sessionState.messages) && sessionState.messages.length > 0) ||
      !!sessionState.isAnalyzing ||
      !!sessionState.isComplete ||
      !!sessionState.finalAnswer
  }

  /**
   * 执行会话恢复的统一逻辑
   * @param {string} sessionId - 会话ID
   * @param {object} options - 恢复选项
   * @returns {object} 恢复结果
   */
  const doRestoreSession = async (sessionId, options = {}) => {
    const { messageLimit = 100 } = options
    const requestToken = ++restoreRequestToken

    try {
      // 1. 调用恢复API
      const [restoreResult] = await Promise.all([
        restoreSession(sessionId, { messageLimit }),
        resourceStore.loadCatalog(sessionId)
      ])
      if (requestToken !== restoreRequestToken) {
        return { success: false, cancelled: true, error: '会话已切换' }
      }

      if (!restoreResult) {
        return {
          success: false,
          error: '恢复失败：API返回为空'
        }
      }

      // 后端返回格式：{ message: "...", session: {...} }
      const sessionData = restoreResult.session || restoreResult
      let messages = sessionData.conversation_history || []
      if (messages.length === 0) {
        throw new Error('该历史会话没有可恢复的消息，消息持久化可能失败')
      }

      // 详细分析 final 消息（只根据type字段判断）
      const finalMessages = messages.filter(m => {
        const msgType = (m.type || '').toLowerCase()
        return msgType === 'final' || msgType === 'assistant'
      })

      // 【修复】final消息按ID去重，只过滤真正重复ID的消息
      const idMap = new Map()
      finalMessages.forEach(m => {
        if (m.id) {
          if (idMap.has(m.id)) {
            // 发现重复ID
            const existing = idMap.get(m.id)
            console.warn('[会话恢复] 发现重复ID的final消息:', {
              id: m.id,
              原消息时间: existing.timestamp || 'N/A',
              重复消息时间: m.timestamp || 'N/A'
            })
          } else {
            idMap.set(m.id, m)
          }
        }
      })

      // 只保留每个ID的第一次出现
      const seenIds = new Set(idMap.keys())
      const beforeCount = messages.length
      messages = messages.filter(m => {
        // 只检查final/assistant消息的ID
        const msgType = (m.type || '').toLowerCase()
        if (msgType === 'final' || msgType === 'assistant') {
          return !m.id || seenIds.has(m.id)
        }
        return true
      })

      if (messages.length !== beforeCount) {
        console.log(`[会话恢复] 按ID去重：${beforeCount} → ${messages.length} (过滤${beforeCount - messages.length}条)`)
      }

      // 2. 更新对话状态；资源状态由 sessionResourceStore 独立维护。
      const restoredMode = resolveRestoredAgentMode(sessionData, sessionId, store.currentMode)
      store.switchMode(restoredMode)
      store.reset()
      store.setSessionId(sessionId, restoredMode)
      store.currentState.conversationAccess = {
        source: sessionData.source || 'web',
        read_only_on_web: sessionData.read_only_on_web === true
      }
      store.setMessages(messages)
      const restoredBoard = sessionData.metadata?.drawio_board || sessionData.drawio_board || null
      if (restoredMode === 'board' && restoredBoard?.board_id &&
          typeof store.ensureDrawioBoardState === 'function' &&
          typeof store.loadDrawioBoardVersions === 'function') {
        const board = store.ensureDrawioBoardState(store.currentState)
        board.activeBoardId = restoredBoard.board_id
        board.title = restoredBoard.title || board.title
        board.acceptedVersionId = restoredBoard.accepted_version_id || restoredBoard.acceptedVersionId || null
        board.workingVersionId = restoredBoard.working_version_id || restoredBoard.workingVersionId ||
          restoredBoard.candidate_version_id || restoredBoard.candidateVersionId || null
        board.candidateVersionId = restoredBoard.candidate_version_id || restoredBoard.candidateVersionId || null
        try {
          await store.loadDrawioBoardVersions(store.currentState)
        } catch (error) {
          console.warn('[会话恢复] 画板版本和手动草稿恢复失败:', error)
        }
      }
      resourceStore.activateSession(sessionId)
      await resourceStore.refreshIfNewer(sessionId, sessionData.resource_version || 0)
      if (requestToken !== restoreRequestToken || resourceStore.activeSessionId !== sessionId) {
        return { success: false, cancelled: true, error: '会话已切换' }
      }
      chooseRestoredResource(resourceStore, sessionId)

      // 设置分页信息
      if (sessionData.has_more_messages !== undefined || sessionData.total_message_count !== undefined) {
        store.setPagination({
          hasMoreMessages: sessionData.has_more_messages || false,
          totalMessageCount: sessionData.total_message_count || messages.length,
          oldestSequence: sessionData.oldest_sequence,
          loadingMore: false
        })
      }

      return {
        success: true,
        messageCount: messages.length,
        resourceCount: resourceStore.sessionState(sessionId)?.resources?.length || 0
      }

    } catch (error) {
      if (requestToken !== restoreRequestToken) {
        return { success: false, cancelled: true, error: '会话已切换' }
      }
      console.error('[会话恢复] 恢复会话时出错:', error)
      if (hasRestorableLocalState(store.sessionStates?.[sessionId])) {
        store._activateSession(sessionId)
        return {
          success: true,
          session: store.sessionStates[sessionId],
          local: true,
          degraded: true,
          error: error.message
        }
      }
      return {
        success: false,
        error: error.message
      }
    }
  }

  const activateLocalSessionIfAvailable = async (sessionId) => {
    const localSessionState = store.sessionStates?.[sessionId]
    if (!hasRestorableLocalState(localSessionState)) return false

    restoreRequestToken += 1
    store._activateSession(sessionId, localSessionState.mode)
    resourceStore.activateSession(sessionId)
    void resourceStore.loadCatalog(sessionId).then(() => chooseRestoredResource(resourceStore, sessionId))
    console.log('[会话切换] 已激活本地会话状态，跳过后端恢复:', {
      sessionId,
      messageCount: localSessionState.messages?.length || 0,
      isAnalyzing: !!localSessionState.isAnalyzing
    })
    return true
  }

  /**
   * 处理会话恢复
   * @param {string} sessionId - 会话ID
   */
  const handleSessionRestore = async (sessionId) => {
    if (resourceStore.activeSessionId && resourceStore.activeSessionId !== sessionId) {
      if (!await confirmResourcePreviewLeave()) return false
    }
    if (await activateLocalSessionIfAvailable(sessionId)) {
      return true
    }

    const result = await doRestoreSession(sessionId, { messageLimit: 100, restoreOfficeDocs: true })

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
    if (resourceStore.activeSessionId && resourceStore.activeSessionId !== sessionId) {
      if (!await confirmResourcePreviewLeave()) return false
    }
    if (await activateLocalSessionIfAvailable(sessionId)) {
      return true
    }

    const result = await doRestoreSession(sessionId, {
      messageLimit: 100,
      restoreOfficeDocs: true
    })

    return result.success
  }

  const startNewWebConversation = async () => {
    if (!await confirmResourcePreviewLeave()) return false
    restoreRequestToken += 1
    const defaultAgentMode = resolveProjectDefaultAgentMode(projectConfig, AGENT_MODE_IDS)
    if (store.currentMode !== defaultAgentMode) {
      store.switchMode(defaultAgentMode)
    }
    store.reset()
    resourceStore.activateSession(null)
    store.currentState.conversationAccess = {
      source: 'web',
      read_only_on_web: false
    }
    return true
  }

  // ========== 会话历史管理 ==========

  /**
   * 刷新会话历史
   */
  const refreshSessionHistory = async (options = {}) => {
    const { silent = false } = options
    if (refreshInFlight) return refreshInFlight

    if (!silent) sessionHistoryLoading.value = true
    try {
      refreshInFlight = (async () => {
        const data = await listSessions({ limit: 200 })
        persistedSessionHistoryData.value = data.sessions || []
        sessionHistoryStats.value = data.stats || null
      })()
      await refreshInFlight
    } catch (error) {
      console.error('Failed to refresh session history:', error)
    } finally {
      refreshInFlight = null
      if (!silent) sessionHistoryLoading.value = false
    }
  }

  const localSessionSignature = computed(() => {
    return localSessionHistoryData.value
      .map(session => `${session.session_id}:${session.status}:${session.message_count}:${session.updated_at}`)
      .join('|')
  })

  watch(localSessionSignature, () => {
    refreshSessionHistory({ silent: true })
  })

  onMounted(() => {
    refreshSessionHistory({ silent: true })
    autoRefreshTimer = window.setInterval(() => {
      refreshSessionHistory({ silent: true })
    }, 15000)
  })

  onUnmounted(() => {
    if (autoRefreshTimer) {
      window.clearInterval(autoRefreshTimer)
      autoRefreshTimer = null
    }
  })

  /**
   * 清理会话
   */
  const handleSessionCleanup = async () => {
    try {
      const response = await authFetch('/api/sessions/cleanup', { method: 'POST' })
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
  const deleteSessions = async (sessionIds) => {
    const ids = Array.from(new Set((sessionIds || []).filter(Boolean)))
    if (ids.length === 0) return false

    const message = ids.length === 1
      ? '确定要删除此会话吗？此操作不可恢复。'
      : `确定要删除选中的 ${ids.length} 个会话吗？此操作不可恢复。`
    if (!confirm(message)) return false

    try {
      await Promise.all(ids.map(sessionId => deleteSessionRequest(sessionId)))
      await refreshSessionHistory()
      return true
    } catch (error) {
      console.error('Failed to delete sessions:', error)
      alert('删除失败: ' + error.message)
      return false
    }
  }

  /**
   * 删除单个会话
   * @param {string} sessionId - 会话ID
   */
  const deleteSession = async (sessionId) => {
    return deleteSessions([sessionId])
  }

  const handleToggleSessionCase = async (session) => {
    if (!session?.session_id) return false

    const isCase = session.metadata?.is_case === true
    const previousMetadata = { ...(session.metadata || {}) }
    applySessionCaseState(session.session_id, !isCase)

    try {
      if (isCase) {
        await unmarkSessionCase(session.session_id)
      } else {
        await markSessionCase(session.session_id)
      }
      refreshSessionHistory({ silent: true })
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('session-case-updated'))
      }
      return true
    } catch (error) {
      applySessionCaseState(session.session_id, isCase, previousMetadata)
      console.error('Failed to toggle session case:', error)
      alert('案例标记失败: ' + error.message)
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
    currentConversationPolicy,

    // 会话操作
    handleSend,
    handlePause,
    handleRestart,
    toggleAnalysis,

    // 会话恢复
    handleSessionRestore,
    handleLoadSession,
    doRestoreSession,
    startNewWebConversation,

    // 会话历史
    refreshSessionHistory,
    handleSessionCleanup,
    deleteSession,
    deleteSessions,
    handleToggleSessionCase,

    // 会话管理器
    openSessionManager,
    closeSessionManager
  }
}
