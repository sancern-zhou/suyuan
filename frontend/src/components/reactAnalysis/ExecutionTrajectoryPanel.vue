<template>
  <div class="trajectory-host">
  <ModelTrajectoryPanel v-if="!showExecution" :session-id="sessionId" :messages="messages" @show-execution="showExecution = true" />
  <section v-else class="trajectory-panel" aria-label="会话执行记录">
    <header>
      <div><h3>调用轨迹</h3><p>{{ entries.length }} 条记录 · {{ toolCount }} 个工具调用</p></div>
      <button type="button" :disabled="loading" @click="refresh">{{ loading ? '加载中…' : '刷新' }}</button>
      <button type="button" @click="expanded = !expanded">{{ expanded ? '全部收起' : '全部展开' }}</button>
      <button type="button" @click="showExecution = false">模型调用</button>
    </header>
    <input v-model="query" type="search" placeholder="搜索工具、参数或结果" aria-label="搜索调用轨迹" />
    <p v-if="error" class="trajectory-error" role="alert">{{ error }}</p>
    <button v-if="hasMore" type="button" :disabled="loading" @click="loadOlder">加载更早的轨迹</button>
    <p v-if="!filteredEntries.length && !loading">{{ query ? '没有匹配的记录' : '暂无调用记录' }}</p>
    <div class="trajectory-timeline">
      <details v-for="entry in filteredEntries" :key="`${sessionId}:${entry.id}`" :open="expanded || !!query">
        <summary>
          <span class="entry-kind">{{ ['tool_use', 'tool_result'].includes(entry.type) ? '工具' : entry.title }}</span>
          <span class="entry-title">{{ entry.title }}</span>
          <span :class="{ failed: entry.status === '失败' }">{{ entry.status }}</span>
          <time>{{ formatTime(entry.timestamp) }}</time>
        </summary>
        <div class="entry-detail">
          <p v-if="entry.callId" class="call-id">调用 ID：{{ entry.callId }}</p>
          <template v-if="entry.input !== undefined"><h4>调用参数</h4><pre>{{ formatTrajectoryValue(entry.input) }}</pre></template>
          <template v-if="entry.result !== undefined"><h4>返回结果</h4><pre>{{ formatTrajectoryValue(entry.result) }}</pre></template>
          <template v-if="entry.content && !['tool_use', 'tool_result'].includes(entry.type)"><pre>{{ formatTrajectoryValue(entry.content) }}</pre></template>
          <p v-if="entry.completedAt">结束时间：{{ formatTime(entry.completedAt) }}</p>
        </div>
      </details>
    </div>
  </section>
  </div>
</template>

<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { getSessionMessages } from '@/api/session.js'
import { buildTrajectoryEntries, formatTrajectoryValue, mergeTrajectoryMessages } from './executionTrajectory.js'
import ModelTrajectoryPanel from './ModelTrajectoryPanel.vue'

const props = defineProps({ sessionId: { type: String, default: '' }, messages: { type: Array, default: () => [] } })
const saved = ref([])
const showExecution = ref(false)
const query = ref('')
const expanded = ref(false)
const loading = ref(false)
const error = ref('')
const hasMore = ref(false)
const oldestSequence = ref(null)
let requestVersion = 0
const entries = computed(() => buildTrajectoryEntries(mergeTrajectoryMessages(saved.value, props.messages)))
const toolCount = computed(() => entries.value.filter(entry => ['tool_use', 'tool_result'].includes(entry.type)).length)
const filteredEntries = computed(() => {
  const search = query.value.trim().toLowerCase()
  return search ? entries.value.filter(entry => formatTrajectoryValue(entry).toLowerCase().includes(search)) : entries.value
})
const formatTime = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : ''

async function fetchPage(before = null) {
  if (!props.sessionId || loading.value) return
  const version = ++requestVersion
  const sessionId = props.sessionId
  loading.value = true
  error.value = ''
  try {
    const result = await getSessionMessages(sessionId, before, 100)
    if (version !== requestVersion) return
    saved.value = before == null ? result.messages || [] : mergeTrajectoryMessages(result.messages || [], saved.value)
    hasMore.value = Boolean(result.has_more)
    oldestSequence.value = result.oldest_sequence
  } catch (cause) {
    if (version === requestVersion) error.value = `轨迹加载失败：${cause.message}`
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
const refresh = () => fetchPage()
const loadOlder = () => fetchPage(oldestSequence.value)
watch(() => props.sessionId, () => {
  requestVersion++
  showExecution.value = false
  saved.value = []
  query.value = ''
  expanded.value = false
  hasMore.value = false
  oldestSequence.value = null
  loading.value = false
  error.value = ''
}, { immediate: true })
watch(showExecution, visible => { if (visible) refresh() })
onBeforeUnmount(() => { requestVersion++ })
</script>

<style scoped>
.trajectory-host { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.trajectory-host > * { flex: 1; min-height: 0; }
.trajectory-panel { min-height: 0; overflow: auto; padding: 16px; color: var(--text-1); background: var(--bg-primary, #fff); }
header { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
header > div { flex: 1; }
h3 { margin: 0; font-size: 15px; }
p, time, .call-id { color: var(--text-3); font-size: 12px; }
button { cursor: pointer; border: 1px solid var(--border-2, #e2e8f0); border-radius: 6px; background: transparent; color: var(--text-2); padding: 5px 8px; }
input { box-sizing: border-box; width: 100%; margin: 12px 0; padding: 8px; border: 1px solid var(--border-2, #e2e8f0); border-radius: 6px; background: transparent; color: inherit; }
details { border-left: 2px solid var(--border-2, #e2e8f0); padding: 10px 0 10px 12px; }
summary { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px; cursor: pointer; font-size: 12px; }
.entry-kind { color: var(--text-3); }
.entry-title { flex: 1; word-break: break-word; font-weight: 600; }
.entry-detail { padding-top: 8px; }
h4 { font-size: 12px; margin: 8px 0; }
pre { font-size: 12px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 500px; overflow: auto; background: var(--bg-muted, #f8fafc); padding: 10px; border-radius: 6px; }
.failed, .trajectory-error { color: #c62828; }
</style>
