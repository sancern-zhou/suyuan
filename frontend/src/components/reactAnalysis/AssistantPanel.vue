<template>
  <aside class="assistant-panel" aria-label="我的助理">
    <header class="assistant-header">
      <h2>我的助理</h2>
      <button type="button" class="icon-button" title="关闭助理面板" aria-label="关闭助理面板" @click="emit('close')"><X :size="18" aria-hidden="true" /></button>
    </header>
    <nav class="assistant-tabs" aria-label="助理视图">
      <button v-for="entry in tabs" :key="entry.id" type="button" :aria-pressed="tab === entry.id" @click="selectTab(entry.id)">{{ entry.label }}</button>
      <button type="button" class="refresh icon-button" title="刷新" aria-label="刷新" :disabled="loading || busy" @click="load()"><RefreshCw :size="16" aria-hidden="true" /></button>
    </nav>
    <div v-if="error" class="assistant-error" role="alert">{{ error }}</div>
    <p v-if="notice" class="assistant-notice" role="status">{{ notice }}</p>
    <div class="assistant-body" :aria-busy="loading">
      <p v-if="loading && !items.length">正在加载…</p>
      <p v-else-if="!items.length" class="empty">{{ emptyText[tab] }}</p>
      <template v-if="tab === 'tasks'">
        <article v-for="item in items" :key="item.task_id" class="assistant-item">
          <div class="item-heading"><h3>{{ item.goal }}</h3><span class="item-state">{{ taskLabels[item.status] || item.status }}</span></div>
          <p v-if="item.next_step" class="next-step">{{ item.next_step }}</p>
          <p v-if="item.result_summary">{{ item.result_summary }}</p>
          <div class="item-actions">
            <button type="button" :disabled="busy" @click="showDetail(item)">详情</button>
            <template v-if="!terminal(item)">
              <button type="button" :disabled="disabled" @click="edit(item, 'feedback')">补充反馈</button>
              <button v-if="['blocked', 'waiting_input'].includes(item.status)" type="button" :disabled="disabled" @click="taskAction(item, 'resume')">恢复推进</button>
              <button type="button" :disabled="disabled" @click="edit(item, 'complete')">确认完成</button>
              <button type="button" :disabled="disabled" @click="taskAction(item, 'stop_followups')">停止跟进</button>
              <button type="button" :disabled="disabled" @click="taskAction(item, 'cancel')">取消事项</button>
            </template>
          </div>
          <div v-if="detail?.task_id === item.task_id" class="item-detail">
            <strong>完成条件</strong><p>{{ detail.completion_criteria }}</p>
            <ol><li v-for="entry in detail.events" :key="entry.event_id"><time>{{ time(entry.created_at) }}</time><p>{{ entry.user_message || entry.changes?.next_step || '事项进展已更新' }}</p></li></ol>
            <button type="button" :disabled="disabled" @click="continueTask(item)">继续讨论</button>
          </div>
          <form v-if="editing?.id === item.task_id" class="feedback-form" @submit.prevent="taskAction(item, editing.action, text)">
            <label :for="`feedback-${item.task_id}`">{{ editing.action === 'complete' ? '完成依据' : '现场反馈' }}</label>
            <textarea :id="`feedback-${item.task_id}`" v-model="text" required maxlength="20000" rows="4"></textarea>
            <div class="item-actions"><button type="submit" :disabled="disabled || !text.trim()">{{ editing.action === 'complete' ? '确认完成' : '保存反馈' }}</button><button type="button" @click="editing = null">取消</button></div>
          </form>
        </article>
      </template>
      <template v-else-if="tab === 'suggestions'">
        <article v-for="item in items" :key="item.suggestion_id" class="assistant-item">
          <div class="item-heading"><h3>{{ item.goal }}</h3><span class="item-state">{{ suggestionLabels[item.state] }}</span></div>
          <p>{{ item.reason }}</p><p class="suggested-prompt">{{ item.suggested_prompt }}</p>
          <ul v-if="item.missing_inputs?.length"><li v-for="input in item.missing_inputs" :key="input">待补充：{{ input }}</li></ul>
          <div class="item-actions">
            <template v-if="item.state === 'pending'">
              <button type="button" :disabled="disabled" @click="decide(item, 'accept')">采纳</button>
              <button type="button" :disabled="disabled" @click="decide(item, 'dismiss')">忽略</button>
            </template>
            <button v-if="item.state === 'accepted'" type="button" :disabled="disabled" @click="continueSuggestion(item)">继续讨论</button>
          </div>
        </article>
      </template>
      <template v-else>
        <article v-for="item in items" :key="item.message_id" class="assistant-item"><time>{{ time(item.created_at) }}</time><p>{{ item.content }}</p><button type="button" :disabled="busy" @click="openNotification(item)">查看事项</button></article>
      </template>
      <button v-if="hasMore" type="button" class="load-more" :disabled="loading || busy" @click="load(true)">加载更多</button>
    </div>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RefreshCw, X } from 'lucide-vue-next'
import { accountGeneration, onAccountChanged } from '@/auth/accountSession.js'
import { changeAssistantTask, decideAssistantSuggestion, getAssistantTask, listAssistantItems } from '@/services/assistantApi.js'

const props = defineProps({ isAnalyzing: Boolean, readOnly: Boolean })
const emit = defineEmits(['close', 'continue'])
const tabs = [{ id: 'tasks', label: '事项' }, { id: 'suggestions', label: '建议' }, { id: 'notifications', label: '提醒' }]
const emptyText = { tasks: '暂无持续事项', suggestions: '暂无使用建议', notifications: '暂无提醒记录' }
const taskLabels = { ready: '待推进', waiting_input: '等待补充或验收', blocked: '暂时阻塞', completed: '已完成', cancelled: '已取消' }
const suggestionLabels = { pending: '待选择', accepted: '已采纳', dismissed: '已忽略' }
const tab = ref('tasks'), items = ref([]), loading = ref(false), busy = ref(false), hasMore = ref(false)
const error = ref(''), notice = ref(''), detail = ref(null), editing = ref(null), text = ref('')
let sequence = 0
let refreshTimer
const disabled = computed(() => busy.value || loading.value || props.isAnalyzing || props.readOnly)
const terminal = item => ['completed', 'cancelled'].includes(item.status)
const time = value => value ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString() : ''
const unsubscribe = onAccountChanged(() => { sequence++; items.value = []; detail.value = null; editing.value = null; emit('close') })
onBeforeUnmount(() => { sequence++; unsubscribe(); clearInterval(refreshTimer) })

async function load(append = false) {
  const seq = ++sequence
  const view = tab.value
  loading.value = true
  error.value = ''
  try {
    const response = await listAssistantItems(view, append ? items.value.length : 0)
    if (seq !== sequence) return
    const rows = response[view] || []
    items.value = append ? [...items.value, ...rows] : rows
    hasMore.value = rows.length === 20
  } catch (failure) {
    if (seq === sequence && failure.name !== 'AbortError') error.value = failure.message
  } finally { if (seq === sequence) loading.value = false }
}
function selectTab(value) { if (busy.value) return; tab.value = value; items.value = []; detail.value = null; editing.value = null; notice.value = ''; load() }
function edit(item, action) { editing.value = { id: item.task_id, action }; text.value = ''; notice.value = '' }
async function operate(action) {
  if (disabled.value) return
  busy.value = true
  error.value = ''; notice.value = ''
  const epoch = accountGeneration()
  try { await action() } catch (failure) { if (epoch === accountGeneration() && failure.name !== 'AbortError') error.value = failure.message }
  finally { if (epoch === accountGeneration()) busy.value = false }
}
async function showDetail(item) {
  if (busy.value) return
  const epoch = accountGeneration()
  busy.value = true
  try { const response = await getAssistantTask(item.task_id); if (epoch === accountGeneration()) detail.value = response.task }
  catch (failure) { if (epoch === accountGeneration() && failure.name !== 'AbortError') error.value = failure.message }
  finally { if (epoch === accountGeneration()) busy.value = false }
}
async function taskAction(item, action, value = '') {
  await operate(async () => {
    await changeAssistantTask(item, action, value)
    editing.value = null; detail.value = null
    notice.value = action === 'feedback' ? '反馈已保存' : '事项已更新'
    await load()
  })
}
async function decide(item, action) {
  await operate(async () => {
    await decideAssistantSuggestion(item, action)
    notice.value = action === 'accept' ? '已采纳，尚未开始执行' : '已忽略此建议'
    await load()
  })
}
function continueSuggestion(item) {
  emit('continue', { sessionId: item.source_session_id, query: `继续讨论我已采纳的建议：${item.goal}\n${item.suggested_prompt}` })
  emit('close')
}
function continueTask(item) {
  emit('continue', { sessionId: item.source_session_id, query: `继续推进事项 ${item.task_id}：${item.goal}。请先查询当前状态和已有证据。` })
  emit('close')
}
async function openNotification(item) {
  tab.value = 'tasks'; items.value = []; detail.value = null; editing.value = null
  await load()
  await showDetail(item)
  if (detail.value && !items.value.some(row => row.task_id === detail.value.task_id)) items.value.unshift(detail.value)
}
watch(() => props.isAnalyzing, (running, previous) => { if (previous && !running && !busy.value) load() })
onMounted(() => {
  load()
  refreshTimer = setInterval(() => {
    if (!document.hidden && !busy.value && !loading.value && !editing.value && items.value.length <= 20) load()
  }, 30000)
})
</script>

<style scoped>
.assistant-panel { position: fixed; z-index: 90; top: 16px; right: 16px; bottom: 16px; width: min(440px, calc(100vw - 32px)); display: flex; flex-direction: column; background: var(--bg-1, #fff); color: var(--text-1, #20262e); border: 1px solid var(--border-2, #dce1e7); border-radius: 8px; box-shadow: 0 8px 32px #0002; overflow: hidden; }
.assistant-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border-2, #dce1e7); }
h2 { margin: 0; font-size: 17px; } h3 { margin: 0; font-size: 14px; line-height: 1.6; overflow-wrap: anywhere; }
button { cursor: pointer; background: transparent; color: inherit; border: 1px solid var(--border-2, #dce1e7); border-radius: 4px; padding: 5px 9px; font: inherit; font-size: 12px; } button:disabled { opacity: .5; cursor: default; } button:focus-visible, textarea:focus-visible { outline: 2px solid #2878ff; outline-offset: 2px; }
.icon-button { display: inline-flex; align-items: center; justify-content: center; border: 0; width: 32px; height: 32px; padding: 0; }
.assistant-tabs { display: flex; gap: 6px; padding: 10px 18px; } .assistant-tabs button[aria-pressed="true"] { background: #e8f1ff; color: #195eae; border-color: #87b2e9; } .refresh { margin-left: auto; }
.assistant-body { overflow: auto; padding: 0 18px 18px; min-height: 0; flex: 1; } .assistant-item { padding: 16px 0; border-bottom: 1px solid var(--border-2, #dce1e7); font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.item-heading { display: flex; gap: 12px; justify-content: space-between; align-items: flex-start; } .item-state { color: var(--text-3, #637181); flex-shrink: 0; font-size: 11px; }
p { white-space: pre-wrap; margin: 8px 0; } .next-step, .suggested-prompt { color: var(--text-2, #465466); } .item-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.item-detail { margin-top: 14px; } .item-detail ol { padding-left: 18px; max-height: 240px; overflow: auto; } time { font-size: 11px; color: var(--text-3, #637181); } .feedback-form { display: grid; gap: 6px; margin-top: 12px; } textarea { box-sizing: border-box; width: 100%; resize: vertical; border: 1px solid var(--border-2, #dce1e7); border-radius: 4px; background: var(--bg-1, #fff); color: inherit; font: inherit; padding: 8px; }
.assistant-error, .assistant-notice { padding: 8px 18px; font-size: 12px; overflow-wrap: anywhere; } .assistant-error { color: #b42318; } .assistant-notice { color: #237249; } .empty { color: var(--text-3, #637181); margin-top: 24px; } .load-more { width: 100%; margin-top: 16px; }
@media (max-width: 600px) { .assistant-panel { top: 8px; bottom: 8px; right: 8px; width: calc(100vw - 16px); } }
</style>
