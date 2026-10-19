<template>
  <aside v-if="unreadCount" class="assistant-replies" role="status" aria-live="polite">
    <Bell :size="16" aria-hidden="true" />
    <span>助手有 {{ unreadCount }} 条新消息</span>
    <button type="button" :disabled="state.isAnalyzing || opening" @click="open">查看</button>
  </aside>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Bell } from 'lucide-vue-next'
import { accountGeneration, onAccountChanged } from '@/auth/accountSession.js'
import { listAssistantReplies, readAssistantReply } from '@/services/assistantApi.js'
import { mergeAssistantReplies } from './assistantReplies.js'

const props = defineProps({ state: { type: Object, required: true } })
const emit = defineEmits(['open'])
const unreadCount = ref(0), replies = ref([]), opening = ref(false)
let timer, running = false, disposed = false
const unsubscribe = onAccountChanged(() => { unreadCount.value = 0; replies.value = [] })

async function refresh() {
  if (running || document.hidden || disposed) return
  running = true
  const epoch = accountGeneration()
  try {
    const response = await listAssistantReplies()
    if (disposed || epoch !== accountGeneration()) return
    replies.value = response.notifications || []
    unreadCount.value = response.unread_count || 0
    // Keep unread until the user opens the result; rendering does not prove reading.
    mergeAssistantReplies(props.state, replies.value)
  } catch { /* Transient failures leave the last known unread state intact. */ }
  finally { running = false }
}
async function open() {
  const reply = replies.value[0]
  if (!reply || props.state.isAnalyzing || opening.value) return
  opening.value = true
  try {
    const epoch = accountGeneration()
    const opened = await new Promise(resolve => emit('open', { sessionId: reply.source_session_id, resolve }))
    if (!opened || disposed || epoch !== accountGeneration()) return
    await readAssistantReply(reply.message_id)
    await refresh()
  } catch { /* Keep the unread receipt when opening or acknowledgement fails. */ }
  finally { opening.value = false }
}
watch(() => [props.state.sessionId, props.state.isAnalyzing], refresh)
onMounted(() => { refresh(); timer = setInterval(refresh, 10000); document.addEventListener('visibilitychange', refresh) })
onBeforeUnmount(() => { disposed = true; clearInterval(timer); unsubscribe(); document.removeEventListener('visibilitychange', refresh) })
</script>

<style scoped>
.assistant-replies { flex: 0 0 auto; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 10px 14px; border-bottom: 1px solid #a7c4d8; background: #f0f9ff; color: #164e63; font-size: 13px; }
button { border: 0; background: transparent; color: #0369a1; cursor: pointer; white-space: nowrap; }
button:disabled { opacity: .5; cursor: default; }
</style>
