<template></template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import { accountGeneration } from '@/auth/accountSession.js'
import { listAssistantConversations, syncAssistantConversation, readAssistantConversation } from '@/services/assistantApi.js'
import { mergeAssistantSnapshot } from './assistantConversationSync.js'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'

const props = defineProps({ state: { type: Object, required: true }, mode: String, active: Boolean })
const emit = defineEmits(['sessions'])
const resources = useSessionResourceStore()
let timer, running = false, disposed = false
let lastState, lastSessionId, lastRevision, lastReadSequence = -1, lastEpoch

async function refresh() {
  if (running || document.hidden || disposed) return
  running = true
  const epoch = accountGeneration()
  try {
    const sessions = await listAssistantConversations()
    if (disposed || epoch !== accountGeneration()) return
    emit('sessions', sessions.sessions || [])
    const state = props.state
    if (!props.active || !state.sessionId || props.mode !== 'assistant' || state.isAnalyzing) return
    if (state !== lastState || state.sessionId !== lastSessionId || epoch !== lastEpoch) {
      lastState = state; lastSessionId = state.sessionId; lastEpoch = epoch; lastRevision = undefined; lastReadSequence = -1
    }
    const id = state.sessionId, messages = state.messages
    const snapshot = await syncAssistantConversation(id, lastRevision)
    if (disposed || !props.active || document.hidden || epoch !== accountGeneration() || props.state !== state ||
        state.sessionId !== id || state.isAnalyzing || state.messages !== messages) return
    state.pendingInteraction = snapshot.pending_interaction || null
    state.backgroundDelegation = (Array.isArray(snapshot.background_runs) && snapshot.background_runs.length)
      ? { phase: 'running', runs: snapshot.background_runs }
      : state.backgroundDelegation && state.backgroundDelegation.phase === 'running'
        ? null
        : state.backgroundDelegation
    if (!snapshot.unchanged) {
      mergeAssistantSnapshot(state, snapshot)
      lastRevision = snapshot.revision
      await nextTick()
      if (disposed || !props.active || document.hidden || epoch !== accountGeneration() || props.state !== state || state.isAnalyzing) return
      if (snapshot.through_sequence >= 0) {
        await readAssistantConversation(id, snapshot.through_sequence)
        lastReadSequence = snapshot.through_sequence
        emit('sessions', (sessions.sessions || []).map(row => row.session_id === id ? { ...row, unread_count: 0 } : row))
      }
      void resources.loadCatalog(id).catch(() => {})
    } else {
      if (lastReadSequence < 0) lastRevision = undefined
      // unchanged 快照仍可能带着未读（新消息在被轮询合并过、read 被
      // 可见性/激活守卫拦下），按会话行补报已读，避免角标滞留。
      const row = (sessions.sessions || []).find(item => item.session_id === id)
      if (row && (Number(row.unread_count) || 0) > 0 && (row.last_sequence ?? -1) >= 0) {
        await readAssistantConversation(id, row.last_sequence)
        lastReadSequence = row.last_sequence
        emit('sessions', (sessions.sessions || []).map(item => item.session_id === id ? { ...item, unread_count: 0 } : item))
      }
    }
  } catch { lastRevision = undefined }
  finally { running = false }
}
watch(() => [props.state.sessionId, props.state.isAnalyzing, props.active], refresh)
onMounted(() => { refresh(); timer = setInterval(refresh, 5000); document.addEventListener('visibilitychange', refresh) })
onBeforeUnmount(() => { disposed = true; clearInterval(timer); document.removeEventListener('visibilitychange', refresh) })
</script>
