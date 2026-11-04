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
import { isAssistantFloatingRoute, floatingBadgeCount } from '@/components/assistantFloating/assistantFloatingPolicy.js'

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
    void markAllNotificationsRead().catch(() => {})
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
      } else if (lastReadSequence < 0) revision = undefined
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
