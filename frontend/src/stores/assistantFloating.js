import { computed, nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/auth/authStore.js'
import { defineStore } from 'pinia'
import { accountGeneration, accountStateKey, onAccountChanged } from '@/auth/accountSession.js'
import { projectConfig } from '@/config/projectConfig.js'
import {
  listAssistantConversations,
  listAssistantNotifications,
  readAssistantConversation,
  readAssistantNotification,
  syncAssistantConversation
} from '@/services/assistantApi.js'
import { mergeAssistantSnapshot } from '@/components/reactAnalysis/assistantConversationSync.js'
import { useReactStore } from './reactStore.js'
import { useSessionResourceStore } from './sessionResourceStore.js'
import { isAssistantFloatingRoute, floatingBadgeCount, nextUnreadFocus } from '@/components/assistantFloating/assistantFloatingPolicy.js'

const ENABLED = projectConfig.hasFeature('assistant_floating') && projectConfig.agentModeIds.includes('assistant')

export const useAssistantFloatingStore = defineStore('assistantFloating', () => {
  const react = useReactStore()
  const resources = useSessionResourceStore()
  const open = ref(false)
  const route = useRoute()
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const visible = computed(() => isAssistantFloatingRoute(route, isAuthenticated.value, ENABLED))
  const fullPageActive = ref(false)
  const conversations = ref([])
  const notifications = ref([])
  const notificationUnread = ref(0)
  const position = ref({ x: 24, y: 112 })
  let timer = null
  let running = false
  let revision
  let lastReadSequence = -1
  let lastSessionId = null
  let lastEpoch = -1
  // 点开浮窗后待执行的一次性"聚焦未读会话"标记：会话列表就绪后消费。
  let focusPending = false

  const state = computed(() => {
    const id = react.activeSessionByMode.assistant
    return (id && react.sessionStates[id]) || react.modeStates.assistant
  })
  const unread = computed(() => floatingBadgeCount(conversations.value))
  const enabled = computed(() => visible.value)

  function activate() {
    const id = react.activeSessionByMode.assistant
    if (id && react.sessionStates[id]) react._activateSession(id, 'assistant')
    else react.switchMode('assistant')
    return state.value
  }

  function openPanel() {
    if (fullPageActive.value) return false
    // 不切换全局 currentMode：浮窗直接读写 assistant 会话状态，
    // 在问数/知识等其他模式对话页上展开时，底层页面保持原模式。
    open.value = true
    focusPending = true
    void markAllNotificationsRead().catch(() => {})
    // 会话列表可能已就绪（轮询周期内点开），先立即尝试聚焦未读会话，
    // 未就绪时等 refresh 拿到列表后再聚焦。
    focusUnreadConversation()
    void refresh()
    return true
  }
  function closePanel() { open.value = false }
  function setFullPageActive(value) {
    fullPageActive.value = !!value
    if (value) open.value = false
  }
  function newConversation() {
    react.resetModeConversation('assistant')
    revision = undefined
    lastReadSequence = -1
    lastSessionId = null
  }
  function switchAssistantSession(sessionId) {
    if (!sessionId) return null
    const target = react._ensureSessionState(sessionId, 'assistant')
    react.activeSessionByMode.assistant = sessionId
    revision = undefined
    lastSessionId = null
    lastReadSequence = -1
    lastEpoch = -1
    return target
  }

  // 角标统计的是全部会话的未读总和，而已读上报只作用于当前会话：
  // 未读落在别的会话（如后台委派在旧会话跑完、或当前是新建的空会话）时，
  // 点开浮窗看不到新消息、角标也无法清除。这里把助手上下文切到最近的
  // 未读会话，让角标与浮窗内容对得上。正在分析或有输入草稿时不抢焦点。
  function focusUnreadConversation() {
    const current = state.value
    if (current?.isAnalyzing || String(current?.currentMessage || '').trim()) return
    const target = nextUnreadFocus(conversations.value, current?.sessionId)
    if (target) switchAssistantSession(target.session_id)
  }

  function loadPosition() {
    try {
      const key = accountStateKey(projectConfig.project.id, 'assistant-floating-position')
      const saved = key && JSON.parse(localStorage.getItem(key) || 'null')
      if (Number.isFinite(saved?.x) && Number.isFinite(saved?.y)) position.value = saved
    } catch { /* 位置损坏时使用默认右下角 */ }
  }
  function savePosition(value) {
    position.value = value
    const key = accountStateKey(projectConfig.project.id, 'assistant-floating-position')
    if (key) localStorage.setItem(key, JSON.stringify(value))
  }

  async function refresh() {
    if (!visible.value || running || document.hidden) return
    running = true
    const epoch = accountGeneration()
    try {
      const [conversationResult, notificationResult] = await Promise.all([
        listAssistantConversations(), listAssistantNotifications()
      ])
      if (epoch !== accountGeneration()) return
      conversations.value = conversationResult.sessions || []
      notifications.value = notificationResult.notifications || []
      notificationUnread.value = notificationResult.unread_count || 0
      // 点开浮窗时的一次性聚焦：会话列表到位后若未读不在当前会话，切换过去。
      if (focusPending && open.value && !fullPageActive.value) {
        focusPending = false
        focusUnreadConversation()
      }
      const current = state.value
      if (!current?.sessionId) return
      if (current.sessionId !== lastSessionId || epoch !== lastEpoch) {
        lastSessionId = current.sessionId
        lastEpoch = epoch
        revision = undefined
        lastReadSequence = -1
      }
      if (current.isAnalyzing) return
      const sessionId = current.sessionId
      const messages = current.messages
      const snapshot = await syncAssistantConversation(sessionId, revision)
      if (epoch !== accountGeneration() || state.value !== current || current.isAnalyzing || current.messages !== messages) return
      current.pendingInteraction = snapshot.pending_interaction || null
      if (Array.isArray(snapshot.background_runs)) {
        current.backgroundDelegation = snapshot.background_runs.length
          ? { phase: 'running', runs: snapshot.background_runs }
          : current.backgroundDelegation?.phase === 'running' ? null : current.backgroundDelegation
      }
      if (!snapshot.unchanged) {
        mergeAssistantSnapshot(current, snapshot)
        revision = snapshot.revision
        await nextTick()
        if (epoch !== accountGeneration() || state.value !== current || current.isAnalyzing) return
        if (snapshot.through_sequence >= 0 && (open.value || fullPageActive.value) && !document.hidden) {
          await readAssistantConversation(sessionId, snapshot.through_sequence)
          lastReadSequence = snapshot.through_sequence
          conversations.value = conversations.value.map(row => row.session_id === sessionId ? { ...row, unread_count: 0 } : row)
        }
        void resources.loadCatalog(sessionId).catch(() => {})
      } else {
        if (lastReadSequence < 0) revision = undefined
        // unchanged 快照仍可能带着未读：新消息在浮窗关闭期间已被轮询合并
        // （revision 推进、read 被"面板打开"守卫拦下），重开浮窗时 sync 返回
        // unchanged，若不按会话行补报已读，角标会一直滞留。
        const row = conversations.value.find(item => item.session_id === sessionId)
        if (row && (Number(row.unread_count) || 0) > 0 && (row.last_sequence ?? -1) >= 0 &&
            (open.value || fullPageActive.value) && !document.hidden) {
          await readAssistantConversation(sessionId, row.last_sequence)
          lastReadSequence = row.last_sequence
          conversations.value = conversations.value.map(item => item.session_id === sessionId ? { ...item, unread_count: 0 } : item)
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') revision = undefined
    } finally { running = false }
  }

  async function markAllNotificationsRead() {
    const pending = notifications.value.filter(item => !item.read_at)
    if (!pending.length) return
    await Promise.all(pending.map(item => readAssistantNotification(item.message_id)))
    const now = new Date().toISOString()
    notifications.value = notifications.value.map(item => item.read_at ? item : { ...item, read_at: now })
    notificationUnread.value = 0
  }

  watch(visible, value => {
    if (!value) {
      clearInterval(timer)
      timer = null
      conversations.value = []
      notifications.value = []
      notificationUnread.value = 0
      revision = undefined
      lastSessionId = null
      return
    }
    loadPosition()
    void refresh()
    if (!timer) timer = setInterval(refresh, 5000)
  })
  watch(open, value => { if (value) void refresh() })
  onAccountChanged(() => {
    open.value = false
    conversations.value = []
    notifications.value = []
    notificationUnread.value = 0
    revision = undefined
    lastSessionId = null
    lastEpoch = -1
  })
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', refresh)

  return {
    enabled, open, visible, fullPageActive, conversations, notifications, notificationUnread, position,
    state, unread, activate, openPanel, closePanel, setFullPageActive, newConversation, switchAssistantSession,
    savePosition, refresh, markAllNotificationsRead
  }
})
