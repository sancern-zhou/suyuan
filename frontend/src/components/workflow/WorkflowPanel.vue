<template>
  <section class="workflow-panel" aria-label="工作流运行视图">
    <header class="workflow-header">
      <div>
        <p class="eyebrow">Agent 协同运行</p>
        <h2>工作流</h2>
      </div>
      <button class="icon-action" type="button" title="刷新工作流" aria-label="刷新工作流" :disabled="loading" @click="refresh">
        ↻
      </button>
    </header>

    <div v-if="error" class="state error" role="alert">{{ error }}</div>
    <div v-else-if="loading && workflows.length === 0" class="state">正在加载工作流...</div>
    <div v-else-if="workflows.length === 0" class="state empty">
      <strong>当前会话还没有工作流</strong>
      <span>报告模式或专家模式开始协同分析后，运行状态会显示在这里。</span>
    </div>

    <template v-else>
      <div class="workflow-list" role="listbox" aria-label="工作流列表">
        <button
          v-for="item in workflows"
          :key="item.workflow_id"
          type="button"
          class="workflow-item"
          :class="{ selected: selectedId === item.workflow_id }"
          role="option"
          :aria-selected="selectedId === item.workflow_id"
          @click="selectWorkflow(item.workflow_id)"
        >
          <span class="status-dot" :class="`status-${statusMeta(item.status).key}`" aria-hidden="true"></span>
          <span class="workflow-item-main">
            <strong>{{ shortId(item.workflow_id) }}</strong>
            <small>{{ statusMeta(item.status).label }} · {{ nodeCount(item.snapshot) }} 个节点</small>
          </span>
          <span v-if="item.active" class="live-badge">运行中</span>
        </button>
      </div>

      <div v-if="detailLoading" class="detail-state">正在加载工作流详情...</div>
      <article v-else-if="selectedWorkflow" class="workflow-detail">
        <header class="detail-header">
          <div>
            <p class="eyebrow">{{ selectedWorkflow.workflow_id }}</p>
            <h3>{{ statusMeta(selectedStatus).label }}</h3>
          </div>
          <div class="detail-actions">
            <button v-if="canCancel" type="button" class="button danger" @click="cancel">取消</button>
            <button v-if="canResume" type="button" class="button" @click="resume">恢复</button>
          </div>
        </header>

        <div class="summary-grid">
          <div><span>节点</span><strong>{{ nodeStats.total }}</strong></div>
          <div><span>已完成</span><strong>{{ nodeStats.succeeded }}</strong></div>
          <div><span>执行中</span><strong>{{ nodeStats.running }}</strong></div>
          <div><span>失败</span><strong>{{ nodeStats.failed }}</strong></div>
        </div>

        <section class="detail-section">
          <div class="section-heading"><h4>执行图</h4><span>{{ liveLabel }}</span></div>
          <div class="dag" aria-label="工作流节点执行图">
            <div v-for="node in nodes" :key="node.task_id" class="dag-node" :class="`node-${statusMeta(node.status).key}`">
              <div class="node-title"><span class="node-status" aria-hidden="true"></span><strong>{{ nodeTitle(node) }}</strong></div>
              <small v-if="node.dependencies?.length">依赖：{{ node.dependencies.map(shortId).join('、') }}</small>
              <small v-else>入口节点</small>
              <span class="node-status-label">{{ statusMeta(node.status).label }}</span>
            </div>
          </div>
        </section>

        <section v-if="events.length" class="detail-section">
          <div class="section-heading"><h4>运行事件</h4><span>最近 {{ Math.min(events.length, 20) }} 条</span></div>
          <ol class="event-list">
            <li v-for="event in recentEvents" :key="eventKey(event)">
              <span class="event-time">{{ formatTime(event.created_at || event.timestamp) }}</span>
              <span>{{ eventLabel(event) }}</span>
            </li>
          </ol>
        </section>

        <section v-if="failedNodes.length" class="detail-section errors-section">
          <h4>失败节点</h4>
          <p v-for="node in failedNodes" :key="node.task_id">{{ nodeTitle(node) }}：{{ node.error || '节点执行失败' }}</p>
        </section>
      </article>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  cancelSessionWorkflow,
  followSessionWorkflow,
  getSessionWorkflow,
  getSessionWorkflowEvents,
  listSessionWorkflows,
  resumeSessionWorkflow
} from '@/services/workflowApi.js'

const props = defineProps({ sessionId: { type: String, default: '' } })
const workflows = ref([])
const selectedId = ref('')
const selectedWorkflow = ref(null)
const events = ref([])
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const streamController = ref(null)
const emptyRefreshTimer = ref(null)

const statusMap = {
  queued: { key: 'pending', label: '排队中' },
  pending: { key: 'pending', label: '等待执行' },
  running: { key: 'running', label: '执行中' },
  succeeded: { key: 'success', label: '已完成' },
  success: { key: 'success', label: '已完成' },
  failed: { key: 'failed', label: '失败' },
  cancelled: { key: 'cancelled', label: '已取消' }
}

const statusMeta = status => statusMap[String(status || '').toLowerCase()] || { key: 'unknown', label: '未知' }
const shortId = value => String(value || '').replace(/^workflow[-_:]?/, '').slice(0, 32)
const nodeCount = snapshot => Object.keys(snapshot?.graph || snapshot?.definition?.nodes || {}).length
const selectedStatus = computed(() => selectedWorkflow.value?.job_status || selectedWorkflow.value?.snapshot?.status || 'unknown')
const nodes = computed(() => {
  const snapshot = selectedWorkflow.value?.snapshot || {}
  const graph = snapshot.graph || {}
  const definitions = snapshot.definition?.nodes || []
  const definitionMap = new Map(definitions.map(node => [node.task_id, node]))
  return Object.entries(graph).map(([taskId, node]) => ({
    ...definitionMap.get(taskId),
    ...node,
    error: snapshot.node_errors?.[taskId]
  }))
})
const nodeStats = computed(() => nodes.value.reduce((stats, node) => {
  stats.total += 1
  const key = statusMeta(node.status).key
  if (key === 'success') stats.succeeded += 1
  if (key === 'running') stats.running += 1
  if (key === 'failed') stats.failed += 1
  return stats
}, { total: 0, succeeded: 0, running: 0, failed: 0 }))
const failedNodes = computed(() => nodes.value.filter(node => statusMeta(node.status).key === 'failed'))
const canCancel = computed(() => ['queued', 'running'].includes(String(selectedStatus.value)))
const canResume = computed(() => ['failed', 'running', 'queued'].includes(String(selectedStatus.value)))
const recentEvents = computed(() => events.value.slice(-20).reverse())
const liveLabel = computed(() => selectedWorkflow.value?.active ? '实时更新中' : '已结束')

function nodeTitle(node) {
  return node.payload?.goal || node.task_id || '未命名节点'
}

function eventKey(event) {
  return event.event_id || `${event.sequence || ''}-${event.type || ''}-${event.created_at || ''}`
}

function eventLabel(event) {
  if (event.type === 'runtime' && event.event) return event.event.message || `${event.event.type || '节点事件'}：${event.event.task_id || ''}`
  const labels = { 'workflow.queued': '工作流已排队', 'workflow.running': '工作流开始执行', 'workflow.terminal': `工作流${statusMeta(event.status).label}` }
  return labels[event.type] || event.message || event.type || '工作流状态更新'
}

function formatTime(value) {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '--' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function nodeSnapshotFromWorkflow(item) {
  return item?.snapshot || {}
}

function stopEmptyRefresh() {
  if (emptyRefreshTimer.value !== null) {
    window.clearInterval(emptyRefreshTimer.value)
    emptyRefreshTimer.value = null
  }
}

function startEmptyRefresh() {
  if (emptyRefreshTimer.value !== null) return
  emptyRefreshTimer.value = window.setInterval(() => {
    if (!loading.value && props.sessionId) refresh()
  }, 2000)
}

async function refresh() {
  if (!props.sessionId || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const payload = await listSessionWorkflows(props.sessionId)
    workflows.value = Array.isArray(payload?.workflows) ? payload.workflows : []
    if (selectedId.value && workflows.value.some(item => item.workflow_id === selectedId.value)) {
      stopEmptyRefresh()
      await selectWorkflow(selectedId.value, false)
    } else if (workflows.value.length) {
      stopEmptyRefresh()
      const preferred = workflows.value.find(item => item.active) || workflows.value[0]
      await selectWorkflow(preferred.workflow_id, false)
    } else {
      selectedId.value = ''
      selectedWorkflow.value = null
      stopStream()
      startEmptyRefresh()
    }
  } catch (err) {
    error.value = err?.message || '工作流列表加载失败'
  } finally {
    loading.value = false
  }
}

async function selectWorkflow(workflowId, reload = true) {
  selectedId.value = workflowId
  detailLoading.value = true
  error.value = ''
  stopStream()
  try {
    const detail = reload
      ? await getSessionWorkflow(props.sessionId, workflowId)
      : { ...(workflows.value.find(item => item.workflow_id === workflowId) || {}), snapshot: nodeSnapshotFromWorkflow(workflows.value.find(item => item.workflow_id === workflowId)) }
    selectedWorkflow.value = detail
    const eventPayload = await getSessionWorkflowEvents(props.sessionId, workflowId)
    events.value = Array.isArray(eventPayload?.events) ? eventPayload.events : []
    if (detail.active || ['queued', 'running'].includes(String(detail.job_status || detail.snapshot?.status))) {
      startStream(workflowId, events.value.at(-1)?.event_id || '0-0')
    }
  } catch (err) {
    error.value = err?.message || '工作流详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function stopStream() {
  streamController.value?.abort()
  streamController.value = null
}

async function startStream(workflowId, afterEventId = '0-0') {
  const controller = new AbortController()
  streamController.value = controller
  try {
    await followSessionWorkflow(props.sessionId, workflowId, {
      afterEventId,
      signal: controller.signal,
      onEvent: event => {
        events.value.push(event)
        if (event.type === 'workflow.terminal') {
          selectedWorkflow.value = { ...selectedWorkflow.value, active: false, job_status: event.status, snapshot: { ...selectedWorkflow.value?.snapshot, status: event.status } }
        }
      }
    })
    if (!controller.signal.aborted && selectedWorkflow.value?.active) {
      await selectWorkflow(workflowId)
    }
  } catch (err) {
    if (err?.name !== 'AbortError') error.value = err?.message || '工作流事件流已断开'
  }
}

async function cancel() {
  await runAction(() => cancelSessionWorkflow(props.sessionId, selectedId.value), '工作流取消失败')
}

async function resume() {
  await runAction(() => resumeSessionWorkflow(props.sessionId, selectedId.value), '工作流恢复失败')
}

async function runAction(action, fallback) {
  try {
    await action()
    await refresh()
  } catch (err) {
    error.value = err?.message || fallback
  }
}

watch(() => props.sessionId, () => {
  stopStream()
  stopEmptyRefresh()
  workflows.value = []
  selectedId.value = ''
  selectedWorkflow.value = null
  events.value = []
  if (props.sessionId) refresh()
})

onMounted(() => { if (props.sessionId) refresh() })
onBeforeUnmount(() => {
  stopStream()
  stopEmptyRefresh()
})
</script>

<style scoped>
.workflow-panel { height: 100%; overflow: auto; background: #f8fafc; color: #243247; }
.workflow-header, .detail-header, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.workflow-header { padding: 18px 18px 12px; border-bottom: 1px solid #e5ebf2; background: #fff; }
.workflow-header h2, .detail-header h3, .section-heading h4 { margin: 0; }
.workflow-header h2 { font-size: 20px; }
.eyebrow { margin: 0 0 4px; color: #75849a; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.icon-action { width: 32px; height: 32px; border: 1px solid #dbe4ee; border-radius: 7px; background: #fff; color: #315b84; font-size: 20px; cursor: pointer; }
.icon-action:disabled { opacity: .5; cursor: wait; }
.state, .detail-state { padding: 30px 18px; color: #6c7b8e; text-align: center; }
.state.error { color: #b42318; }
.empty { display: grid; gap: 6px; }
.empty strong { color: #36485e; }
.workflow-list { display: grid; gap: 6px; padding: 12px; border-bottom: 1px solid #e5ebf2; }
.workflow-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px; border: 1px solid transparent; border-radius: 8px; background: #fff; color: inherit; text-align: left; cursor: pointer; }
.workflow-item:hover, .workflow-item.selected { border-color: #bcd5ee; background: #f2f7fc; }
.status-dot, .node-status { display: inline-block; flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }
.status-success, .node-success .node-status { background: #1f9d69; }
.status-running, .node-running .node-status { background: #2778c9; box-shadow: 0 0 0 3px #dceeff; }
.status-pending, .node-pending .node-status { background: #94a3b8; }
.status-failed, .node-failed .node-status { background: #d04444; }
.status-cancelled, .node-cancelled .node-status { background: #7b8794; }
.workflow-item-main { display: grid; gap: 3px; min-width: 0; flex: 1; }
.workflow-item-main strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.workflow-item-main small { color: #7b899a; font-size: 11px; }
.live-badge { padding: 2px 6px; border-radius: 4px; background: #e4f1ff; color: #2169a8; font-size: 10px; }
.workflow-detail { padding: 16px; }
.detail-header h3 { font-size: 17px; }
.detail-actions { display: flex; gap: 6px; }
.button { min-height: 30px; padding: 5px 10px; border: 1px solid #cbd8e5; border-radius: 6px; background: #fff; color: #315b84; cursor: pointer; }
.button.danger { border-color: #efc2c2; color: #b42318; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin: 16px 0; }
.summary-grid div { display: grid; gap: 3px; padding: 9px; border: 1px solid #e1e8f0; border-radius: 7px; background: #fff; }
.summary-grid span { color: #7b899a; font-size: 11px; }
.summary-grid strong { font-size: 16px; }
.detail-section { margin-top: 18px; }
.section-heading h4, .detail-section > h4 { font-size: 13px; }
.section-heading span { color: #8290a0; font-size: 11px; }
.dag { display: grid; gap: 8px; margin-top: 8px; }
.dag-node { padding: 9px 10px; border: 1px solid #dfe7ef; border-left: 3px solid #94a3b8; border-radius: 6px; background: #fff; }
.dag-node.node-success { border-left-color: #1f9d69; }
.dag-node.node-running { border-left-color: #2778c9; }
.dag-node.node-failed { border-left-color: #d04444; }
.node-title { display: flex; align-items: center; gap: 8px; }
.node-title strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.dag-node small { display: block; margin: 5px 0 0 16px; overflow: hidden; color: #7b899a; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.node-status-label { display: block; margin: 5px 0 0 16px; color: #617184; font-size: 10px; }
.event-list { display: grid; gap: 7px; margin: 8px 0 0; padding: 0; list-style: none; }
.event-list li { display: flex; gap: 9px; color: #526173; font-size: 11px; }
.event-time { flex: 0 0 58px; color: #8a98a8; font-variant-numeric: tabular-nums; }
.errors-section { padding: 10px; border: 1px solid #f1d2d2; border-radius: 7px; background: #fff8f8; color: #a33b3b; font-size: 11px; }
.errors-section p { margin: 6px 0 0; }
@media (max-width: 640px) { .summary-grid { grid-template-columns: repeat(2, 1fr); } .workflow-detail { padding: 12px; } }
</style>
