<template>
  <section class="model-trajectory-panel" aria-label="模型调用轨迹">
    <header>
      <div><h3>模型调用轨迹</h3><p>{{ totalCount }} 次调用 · 已加载 {{ totalTokens.toLocaleString() }} Token <span v-if="models">· {{ models }}</span></p></div>
      <div class="toolbar">
        <button type="button" :disabled="loading" @click="refresh">刷新</button>
        <button type="button" @click="setAll(!allExpanded)">{{ allExpanded ? '全部收起' : '全部展开' }}</button>
        <button type="button" @click="$emit('show-execution')">执行记录</button>
      </div>
      <div class="search-bar">
        <input v-model="query" type="search" aria-label="搜索模型调用轨迹" placeholder="搜索提示词、思考或工具内容" />
        <span>{{ matches.length ? activeMatch + 1 : 0 }}/{{ matches.length }}</span>
        <button type="button" :disabled="!matches.length" @click="moveMatch(-1)">上一处</button>
        <button type="button" :disabled="!matches.length" @click="moveMatch(1)">下一处</button>
      </div>
      <div class="expansion-controls" aria-label="按类型展开">
        <button v-for="(label, kind) in kinds" :key="kind" type="button" :aria-pressed="expandedKinds.has(kind)" @click="toggleKind(kind)">{{ label }}</button>
      </div>
      <p v-if="error" role="alert" class="failed">{{ error }}</p>
    </header>
    <div ref="scrollHost" class="model-timeline" @scroll.passive="updateViewport">
      <button v-if="hasMore" type="button" :disabled="loading" @click="loadOlder">加载更早的模型调用</button>
      <p v-if="!cards.length">{{ loading ? '正在加载模型轨迹…' : '暂无模型调用记录。完整轨迹从功能启用后的请求开始记录，可切换执行记录查看历史会话。' }}</p>
      <div :style="{ height: `${topSpace}px` }" aria-hidden="true"></div>
      <article v-for="card in visibleCards" :key="card.request_id" :ref="element => measureCard(element, card.request_id)" class="model-call-card" :data-call-id="card.request_id">
        <div class="call-summary">
          <span class="call-index">{{ cards.indexOf(card) + 1 }}</span>
          <strong>{{ sourceLabel(card.source) }}</strong>
          <span :class="{ failed: card.status === 'failed' }">{{ statusLabel(card) }}</span>
          <span>{{ card.model }}</span>
          <span>{{ card.duration_ms == null ? '执行中' : `${(card.duration_ms / 1000).toFixed(1)}秒` }}</span>
        </div>
        <div class="call-metadata">
          <time>{{ formatTime(card.started_at) }}</time>
          <span v-if="card.response?.usage && Object.keys(card.response.usage).length">输入 {{ trajectoryUsage(card).input }} · 输出 {{ trajectoryUsage(card).output }} · 缓存 {{ trajectoryUsage(card).cached }} Token</span>
          <span v-else>未返回 Token 用量</span>
          <span v-if="card.source === 'subagent'">子会话：{{ card.session_id }}</span>
        </div>
        <template v-for="section in ['input', 'output']" :key="section">
          <div v-if="card.rows.some(row => (row.section || 'input') === section)" class="call-section">
            <h4>{{ section === 'input' ? '输入' : '输出' }}</h4>
            <div v-for="row in card.rows.filter(row => (row.section || 'input') === section)" :key="row.id" class="trajectory-row" :class="{ 'search-active': activeRowId === row.id }">
              <button type="button" class="row-summary" :aria-expanded="rowExpanded(row)" @click="toggleRow(row)">
                <span class="role-label">{{ kinds[row.kind] || row.role }}</span><span>{{ row.title || preview(row.text) }}</span><span>{{ rowExpanded(row) ? '−' : '+' }}</span>
              </button>
              <pre v-if="rowExpanded(row)" :data-row-id="row.id"><template v-for="(part, index) in highlighted(row.text)" :key="index"><mark v-if="part.match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></pre>
            </div>
          </div>
        </template>
        <pre v-if="card.error" class="failed">{{ formatTrajectoryValue(card.error) }}</pre>
      </article>
      <div :style="{ height: `${bottomSpace}px` }" aria-hidden="true"></div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getModelTrajectory } from '@/api/session.js'
import { formatTrajectoryValue } from './executionTrajectory.js'
import { mergeModelRecords, modelTrajectoryCards, trajectoryUsage } from './modelTrajectory.js'
const props = defineProps({ sessionId: { type: String, required: true }, messages: { type: Array, default: () => [] } })
defineEmits(['show-execution'])
const records = ref([]), totalCount = ref(0), hasMore = ref(false), cursor = ref(null)
const loading = ref(false), error = ref(''), query = ref(''), activeMatch = ref(0)
const expandedKinds = ref(new Set()), overrides = ref(new Map())
const kinds = { system: '系统', user: '用户', assistant: '助手', thinking: '思考', tool: '工具', tools: '工具定义' }
const cards = computed(() => modelTrajectoryCards(records.value))
const totalTokens = computed(() => records.value.reduce((sum, record) => sum + trajectoryUsage(record).total, 0))
const models = computed(() => [...new Set(records.value.map(record => record.model))].join('、'))
const allExpanded = computed(() => Object.keys(kinds).every(kind => expandedKinds.value.has(kind)))
const matches = computed(() => {
  const search = query.value.trim().toLowerCase()
  if (!search) return []
  return cards.value.flatMap((card, callIndex) => card.rows.filter(row => row.text.toLowerCase().includes(search)).map(row => ({ rowId: row.id, callIndex })))
})
const activeRowId = computed(() => matches.value[activeMatch.value]?.rowId)
const rowExpanded = row => activeRowId.value === row.id || (overrides.value.get(row.id) ?? expandedKinds.value.has(row.kind))
function toggleRow(row) { const next = new Map(overrides.value); next.set(row.id, !rowExpanded(row)); overrides.value = next }
function toggleKind(kind) { const next = new Set(expandedKinds.value); next.has(kind) ? next.delete(kind) : next.add(kind); expandedKinds.value = next; overrides.value = new Map() }
function setAll(value) { expandedKinds.value = new Set(value ? Object.keys(kinds) : []); overrides.value = new Map() }
function highlighted(text) {
  const search = query.value.trim()
  if (!search) return [{ text }]
  const parts = [], lower = text.toLowerCase(), needle = search.toLowerCase()
  let offset = 0, index
  while ((index = lower.indexOf(needle, offset)) !== -1) {
    parts.push({ text: text.slice(offset, index) }, { text: text.slice(index, index + search.length), match: true })
    offset = index + search.length
  }
  parts.push({ text: text.slice(offset) })
  return parts
}
const preview = text => text.replace(/\s+/g, ' ').slice(0, 110)
const formatTime = value => new Date(value).toLocaleString('zh-CN', { hour12: false })
const sourceLabel = source => ({ main: '主 Agent', subagent: '子 Agent', compact: '上下文压缩', sidecar: '辅助调用' })[source] || source
const statusLabel = card => ({ running: '调用中', failed: '失败', cancelled: '已取消' })[card.status] || card.response?.stop_reason || '已完成'

// Virtualize calls with measured heights; details remain independently expandable.
const scrollHost = ref(null), viewportTop = ref(0), viewportHeight = ref(600), heights = ref(new Map())
const offsets = computed(() => { let top = 0; return cards.value.map(card => { const start = top; top += heights.value.get(card.request_id) || 240; return { start, end: top } }) })
const range = computed(() => {
  const start = Math.max(0, offsets.value.findIndex(offset => offset.end >= viewportTop.value) - 2)
  let end = offsets.value.findIndex(offset => offset.start > viewportTop.value + viewportHeight.value)
  if (end < 0) end = cards.value.length
  return { start, end: Math.min(cards.value.length, end + 3) }
})
const visibleCards = computed(() => cards.value.slice(range.value.start, range.value.end))
const topSpace = computed(() => offsets.value[range.value.start]?.start || 0)
const bottomSpace = computed(() => (offsets.value.at(-1)?.end || 0) - (offsets.value[range.value.end - 1]?.end || 0))
function updateViewport() { viewportTop.value = scrollHost.value?.scrollTop || 0; viewportHeight.value = scrollHost.value?.clientHeight || 600 }
let observer, timer, generation = 0
const elements = new Map()
function measureCard(element, id) {
  const previous = elements.get(id)
  if (previous === element) return
  if (previous) observer?.unobserve(previous)
  if (element) { element.dataset.measureId = id; elements.set(id, element); observer?.observe(element) }
  else elements.delete(id)
}
async function revealMatch() {
  const match = matches.value[activeMatch.value]
  if (!match || !scrollHost.value) return
  scrollHost.value.scrollTop = offsets.value[match.callIndex]?.start || 0
  updateViewport()
  await nextTick()
  const target = [...scrollHost.value.querySelectorAll('[data-row-id]')].find(element => element.dataset.rowId === match.rowId)
  target?.scrollIntoView({ block: 'nearest' })
}
function moveMatch(direction) { activeMatch.value = (activeMatch.value + direction + matches.value.length) % matches.value.length; revealMatch() }
watch(query, () => { activeMatch.value = 0; revealMatch() })

async function fetchRecords(before = null) {
  if (!props.sessionId || loading.value) return
  const current = generation
  loading.value = true
  try {
    const result = await getModelTrajectory(props.sessionId, before)
    if (current !== generation) return
    records.value = mergeModelRecords(records.value, result.records || [])
    totalCount.value = result.total_count || records.value.length
    // Refresh preserves the oldest loaded page and its cursor.
    if (before || !cursor.value) { cursor.value = result.oldest_request_id; hasMore.value = Boolean(result.has_more) }
    error.value = ''
  } catch (cause) { if (current === generation) error.value = `模型轨迹加载失败：${cause.message}` }
  finally { if (current === generation) loading.value = false }
}
const refresh = () => fetchRecords()
const loadOlder = () => fetchRecords(cursor.value)
watch(() => props.sessionId, () => {
  generation++; records.value = []; cursor.value = null; hasMore.value = false; totalCount.value = 0
  loading.value = false; query.value = ''; activeMatch.value = 0; overrides.value = new Map(); expandedKinds.value = new Set(); heights.value = new Map()
  refresh()
}, { immediate: true })
onMounted(() => {
  observer = new ResizeObserver(entries => {
    const next = new Map(heights.value)
    for (const entry of entries) next.set(entry.target.dataset.measureId, entry.target.getBoundingClientRect().height)
    heights.value = next
    updateViewport()
  })
  for (const element of elements.values()) observer.observe(element)
  updateViewport()
  timer = window.setInterval(refresh, 3000)
})
onBeforeUnmount(() => { generation++; observer?.disconnect(); window.clearInterval(timer) })
</script>

<style scoped>
.model-trajectory-panel { display: flex; flex-direction: column; min-height: 0; color: var(--text-1); background: var(--bg-primary, #fff); }
header { flex-shrink: 0; padding: 12px; border-bottom: 1px solid var(--border-2, #e2e8f0); }
h3 { margin: 0; font-size: 14px; } h4 { margin: 0; padding: 6px 10px; font-size: 12px; color: var(--text-3); }
p, time, .call-metadata { font-size: 11px; color: var(--text-3); }
.toolbar, .search-bar, .expansion-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
button { cursor: pointer; border: 1px solid var(--border-2, #e2e8f0); border-radius: 5px; background: transparent; color: inherit; padding: 4px 7px; font-size: 11px; }
button[aria-pressed='true'] { background: var(--bg-muted, #eef2f6); }
input { flex: 1; min-width: 120px; border: 1px solid var(--border-2, #e2e8f0); border-radius: 5px; padding: 6px; color: inherit; background: transparent; }
.model-timeline { flex: 1; min-height: 0; overflow-y: scroll; overflow-x: hidden; scrollbar-gutter: stable; scrollbar-width: auto; scrollbar-color: var(--scrollbar-thumb, #bac6da) var(--bg-muted, #f8fafc); overscroll-behavior: contain; }
.model-timeline::-webkit-scrollbar { width: 10px; }
.model-timeline::-webkit-scrollbar-track { background: var(--bg-muted, #f8fafc); }
.model-timeline::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb, #bac6da); border: 2px solid var(--bg-muted, #f8fafc); border-radius: 5px; }
.model-call-card { padding: 0 10px 12px; border-bottom: 1px solid var(--border-2, #e2e8f0); }
.call-summary { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 8px 0; font-size: 11px; position: sticky; top: 0; background: var(--bg-primary, #fff); z-index: 1; }
.call-summary strong { flex: 1; }.call-index { font-variant-numeric: tabular-nums; color: var(--text-3); }
.call-metadata { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.call-section { border: 1px solid var(--border-2, #e2e8f0); border-radius: 7px; margin: 8px 0; overflow: hidden; }
.trajectory-row { border-top: 1px solid var(--border-2, #e2e8f0); }.trajectory-row:nth-child(even) { background: var(--bg-muted, #f8fafc); }
.row-summary { display: grid; grid-template-columns: 58px minmax(0, 1fr) 12px; gap: 8px; text-align: left; width: 100%; border: 0; border-radius: 0; padding: 8px; }.row-summary > span:nth-child(2) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.role-label { color: var(--text-3); }.search-active { outline: 1px solid var(--primary-color, #2878ff); }
pre { margin: 0; padding: 10px; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.6; }
mark { background: #ffe59a; color: #312a10; }.failed { color: #c62828; }
</style>
