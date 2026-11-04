import { computed } from 'vue'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { steerAssistantRun } from '@/services/assistantApi.js'
import { chooseRestoredResource } from '@/services/sessionResourceLifecycle.js'
import { confirmResourcePreviewLeave } from '@/services/resourcePreviewLeaveGuard.js'
import { restoredConversationPolicy } from '@/components/socialHistoryReadOnly.js'
import { resolveRestoredAgentMode } from '@/components/agentPlatform/restoreModePolicy.js'
import { restoreSession } from '@/api/session'

export function resolveDirectThroughRun(state, agentMode) {
  if (agentMode !== 'assistant') return null
  const runs = (state?.backgroundDelegation?.runs || []).filter(
    run => run && run.run_id && run.kind === 'child' && (run.status === 'running' || !run.status)
  )
  if (runs.length !== 1 || state.directThroughSuppressedRunId === runs[0].run_id) return null
  return runs[0]
}

export function hasRestorableLocalState(sessionState) {
  if (!sessionState) return false
  return (Array.isArray(sessionState.messages) && sessionState.messages.length > 0) ||
    !!sessionState.isAnalyzing || !!sessionState.isComplete || !!sessionState.finalAnswer
}

export function useConversationActions(store, { getState = null, preserveCurrentMode = false, onSettled = () => {} } = {}) {
  const resourceStore = useSessionResourceStore()
  let restoreRequestToken = 0
  // getState：调用方指定的目标会话状态（浮窗传 assistant 状态）；
  // 缺省为全局当前状态（全页工作区行为不变）。
  const targetState = computed(getState || (() => store.currentState))
  const currentConversationPolicy = computed(() => restoredConversationPolicy(
    targetState.value?.conversationAccess || {}
  ))

  const handleSend = async payload => {
    if (currentConversationPolicy.value.readOnly) return false
    const query = payload.query
    const agentMode = payload.agentMode || store.agentMode
    const directRun = resolveDirectThroughRun(targetState.value, agentMode)
    if (directRun) {
      try {
        await steerAssistantRun(directRun.run_id, targetState.value.sessionId, query)
        if (typeof payload.onAccepted === 'function') payload.onAccepted()
        await onSettled()
        return true
      } catch (error) {
        console.warn('[assistant] direct-through steer failed, fallback to normal send:', error)
      }
    }
    const options = {
      knowledgeBaseIds: payload.knowledgeBaseIds || [],
      agentMode,
      // 江苏默认档位为自动档（7634ffa2 同批决策）：未显式选档时不降级到 flash。
      modelTier: payload.modelTier || 'auto',
      skillIds: payload.skillIds || [],
      contextRefs: payload.contextRefs || [],
      activeContexts: Array.isArray(payload.activeContexts) ? payload.activeContexts : null,
      messageAttachments: payload.messageAttachments || [],
      pageContext: payload.pageContext || null,
      preserveCurrentMode,
      onAccepted: payload.onAccepted
    }
    try {
      await store.analyze(query, options)
      return true
    } finally {
      await onSettled()
    }
  }

  const doRestoreSession = async (sessionId, options = {}) => {
    const { messageLimit = 100 } = options
    const requestToken = ++restoreRequestToken
    try {
      const [restoreResult] = await Promise.all([
        restoreSession(sessionId, { messageLimit }),
        resourceStore.loadCatalog(sessionId)
      ])
      if (requestToken !== restoreRequestToken) return { success: false, cancelled: true, error: '会话已切换' }
      if (!restoreResult) return { success: false, error: '恢复失败：API返回为空' }
      const sessionData = restoreResult.session || restoreResult
      const rawMessages = sessionData.conversation_history || []
      const restoredBoard = sessionData.metadata?.drawio_board || sessionData.drawio_board || null
      const activeRun = sessionData.active_run || null
      const hasActiveRun = !!(activeRun && (activeRun.stream_id || activeRun === true))
      if (rawMessages.length === 0 && !restoredBoard?.board_id && !hasActiveRun) {
        throw new Error('该历史会话没有可恢复的消息，消息持久化可能失败')
      }
      const seenFinalIds = new Set()
      const messages = rawMessages.filter(message => {
        const type = (message.type || '').toLowerCase()
        if (!['final', 'assistant'].includes(type) || !message.id) return true
        if (seenFinalIds.has(message.id)) return false
        seenFinalIds.add(message.id)
        return true
      })
      const restoredMode = resolveRestoredAgentMode(sessionData, sessionId, store.currentMode)
      store.switchMode(restoredMode)
      store.reset()
      store.setSessionId(sessionId, restoredMode)
      store.currentState.conversationAccess = {
        source: sessionData.source || 'web',
        read_only_on_web: sessionData.read_only_on_web === true
      }
      store.setMessages(messages)
      store.currentState.pendingInteraction = sessionData.metadata?.pending_interaction || null
      if (restoredMode === 'board' && restoredBoard?.board_id &&
          typeof store.ensureDrawioBoardState === 'function' && typeof store.loadDrawioBoardVersions === 'function') {
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
      if (hasActiveRun) {
        store.reattachActiveRun(sessionId, { mode: restoredMode }).catch(error => {
          console.warn('[会话恢复] 接回运行中任务失败:', error)
        })
      }
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
      if (requestToken !== restoreRequestToken) return { success: false, cancelled: true, error: '会话已切换' }
      console.error('[会话恢复] 恢复会话时出错:', error)
      if (hasRestorableLocalState(store.sessionStates?.[sessionId])) {
        store._activateSession(sessionId)
        return { success: true, session: store.sessionStates[sessionId], local: true, degraded: true, error: error.message }
      }
      return { success: false, error: error.message }
    }
  }

  const activateLocalSessionIfAvailable = async sessionId => {
    const localSessionState = store.sessionStates?.[sessionId]
    if (!hasRestorableLocalState(localSessionState)) return false
    restoreRequestToken += 1
    store._activateSession(sessionId, localSessionState.mode)
    resourceStore.activateSession(sessionId)
    void resourceStore.loadCatalog(sessionId).then(() => chooseRestoredResource(resourceStore, sessionId))
    return true
  }

  const restore = async sessionId => {
    if (resourceStore.activeSessionId && resourceStore.activeSessionId !== sessionId) {
      if (!await confirmResourcePreviewLeave()) return false
    }
    if (await activateLocalSessionIfAvailable(sessionId)) return true
    const result = await doRestoreSession(sessionId, { messageLimit: 100, restoreOfficeDocs: true })
    if (!result.success) console.error('[会话恢复] 恢复会话失败:', result.error)
    return result.success
  }

  return { handleSend, restore, doRestoreSession, currentConversationPolicy }
}
