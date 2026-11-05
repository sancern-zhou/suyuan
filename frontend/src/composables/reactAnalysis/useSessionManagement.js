import { authFetch } from '@/auth/http.js'
import { onAccountChanged } from '@/auth/accountSession.js'
/**
 * 会话管理 Composable
 * 处理会话的创建、恢复、清理等操作
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { preserveCatalogFields } from '@/components/management/sessionHistoryAccess.js'
import { useConversationActions } from './useConversationActions.js'
import { filterConversationHistory } from '@/components/conversationListPolicy.js'
import { AGENT_MODE_IDS } from '@/config/agentModes.js'
import { projectConfig, resolveProjectDefaultAgentMode } from '@/config/projectConfig.js'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { confirmResourcePreviewLeave } from '@/services/resourcePreviewLeaveGuard.js'
import {
  listSessions,
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
  const assistantConversations = ref([])
  const applyAssistantConversations = rows => { assistantConversations.value = rows }
  const unsubscribeAssistantAccount = onAccountChanged(() => { assistantConversations.value = [] })
  let autoRefreshTimer = null
  let refreshInFlight = null
  let restoreRequestToken = 0
  const { handleSend, restore, doRestoreSession, currentConversationPolicy } = useConversationActions(store, {
    onSettled: () => refreshSessionHistory({ silent: true })
  })

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

    for (const session of assistantConversations.value) {
      byId.set(session.session_id, {
        ...(byId.get(session.session_id) || {}), ...session,
        query: session.title, metadata: { ...(byId.get(session.session_id)?.metadata || {}), mode: 'assistant' }
      })
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

  // ========== 会话操作方法 ==========

  /**
   * 发送消息
   * @param {string|object} payload - 消息内容或包含选项的对象
   */
  // 发送与追问直通由 useConversationActions 统一提供给全页和浮窗。

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

  const handleSessionRestore = async (sessionId) => restore(sessionId)
  const handleLoadSession = async (sessionId) => restore(sessionId)

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
    unsubscribeAssistantAccount()
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
    applyAssistantConversations,
    handleSessionCleanup,
    deleteSession,
    deleteSessions,
    handleToggleSessionCase,

    // 会话管理器
    openSessionManager,
    closeSessionManager
  }
}
