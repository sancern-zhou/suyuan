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
          <div><span>等待上游</span><strong>{{ nodeStats.blocked }}</strong></div>
          <div><span>已复用</span><strong>{{ nodeStats.reused }}</strong></div>
        </div>

        <section class="detail-section">
          <div class="section-heading"><h4>执行图</h4><span>{{ liveLabel }}</span></div>
          <div class="dag-canvas" aria-label="工作流节点执行图">
            <svg class="dag-edges" :viewBox="`0 0 ${dagCanvas.width} ${dagCanvas.height}`" role="img" aria-label="节点依赖关系">
              <defs>
                <marker id="workflow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
                </marker>
              </defs>
              <path v-for="edge in dagEdges" :key="edge.key" class="dag-edge" :class="`edge-${edge.status}`" :d="edge.path" marker-end="url(#workflow-arrow)" />
            </svg>
            <div class="dag-grid" :style="{ width: dagCanvas.width + 'px', height: dagCanvas.height + 'px', gridTemplateColumns: `repeat(${dagColumns.length}, 220px)` }">
              <div v-for="(column, columnIndex) in dagColumns" :key="columnIndex" class="dag-column">
                <div class="dag-column-label">阶段 {{ columnIndex + 1 }}<span>{{ column.length }} 个节点</span></div>
                <div v-for="node in column" :key="node.task_id" class="dag-node" :class="`node-${statusMeta(node.status).key}`">
              <button class="node-toggle" type="button" :aria-expanded="selectedNodeId === node.task_id" @click="selectNode(node.task_id)">
                <span class="node-title"><span class="node-status" aria-hidden="true"></span><strong>{{ nodeTitle(node) }}</strong></span>
                <span class="node-flags"><small v-if="node.cached || node.reused">已复用</small><small v-if="node.attempt > 1">第 {{ node.attempt }} 次尝试</small></span>
                <small v-if="node.dependencies?.length">依赖：{{ node.dependencies.map(shortId).join('、') }}</small>
                <small v-else>入口节点</small>
                <span class="node-status-label">{{ statusMeta(node.status).label }} · {{ nodeDuration(node.task_id) }}</span>
              </button>
              <div v-if="selectedNodeId === node.task_id" class="node-detail">
                <p v-if="nodeHistoryLoading && !nodeHistory">正在读取节点历史...</p>
                <p v-if="nodeHistoryError" class="history-error">{{ nodeHistoryError }}</p>
                <template v-if="nodeHistory">
                  <p class="node-meta">{{ modeLabel(nodeHistory.child_mode) }} · {{ nodeHistory.child_session_id || '尚无子会话' }}</p>
                  <h5>执行记录</h5>
                  <ol v-if="nodeTimeline.length" class="event-list">
                    <li v-for="item in nodeTimeline" :key="item.key">
                      <span class="event-time">{{ formatTime(item.timestamp) }}</span><span>{{ item.label }}</span>
                    </li>
                  </ol>
                  <p v-else class="history-empty">暂无执行记录</p>
                  <template v-if="nodeHistory.execution_history?.length">
                    <h5>工具轨迹</h5>
                    <ol class="event-list">
                      <li v-for="item in nodeHistory.execution_history" :key="item.sequence">
                        <span class="event-time">{{ item.timestamp ? formatTime(item.timestamp) : '#' + item.sequence }}</span><span>{{ toolEventLabel(item) }}</span>
                      </li>
                    </ol>
                    <button v-if="nodeHistory.has_more" type="button" class="more-button" @click="loadMoreNodeHistory">加载更多记录</button>
                  </template>
                  <template v-if="nodeHistory.answer">
                    <h5>子 Agent 结果</h5><div class="node-answer">{{ nodeHistory.answer }}</div>
                  </template>
                  <template v-if="nodeDependencies(node).length || nodeArtifacts(node).length">
                    <h5>数据血缘</h5>
                    <div v-if="nodeDependencies(node).length" class="lineage-list"><span v-for="item in nodeDependencies(node)" :key="item">输入：{{ item }}</span></div>
                    <div v-if="nodeArtifacts(node).length" class="lineage-list"><span v-for="item in nodeArtifacts(node)" :key="item">产物：{{ item }}</span></div>
                  </template>
                </template>
              </div>
            </div>
              </div>
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
  getSessionWorkflowNodeHistory,
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
const selectedNodeId = ref('')
const nodeHistory = ref(null)
const nodeHistoryLoading = ref(false)
const nodeHistoryError = ref('')
let snapshotTimer = null

const statusMap = {
  queued: { key: 'pending', label: '排队中' },
  pending: { key: 'pending', label: '等待执行' },
  running: { key: 'running', label: '执行中' },
  succeeded: { key: 'success', label: '已完成' },
  success: { key: 'success', label: '已完成' },
  failed: { key: 'failed', label: '失败' },
  blocked: { key: 'blocked', label: '等待上游' },
  retrying: { key: 'retrying', label: '重试中' },
  cached: { key: 'cached', label: '已复用' },
  reused: { key: 'cached', label: '已复用' },
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
    error: snapshot.node_errors?.[taskId],
    lineage: snapshot.node_lineage?.[taskId]
  }))
})
const dagColumns = computed(() => {
  const remaining = new Map(nodes.value.map(node => [node.task_id, node]))
  const placed = new Set()
  const columns = []
  while (remaining.size) {
    const ready = [...remaining.values()].filter(node =>
      (node.dependencies || []).every(dependency => placed.has(dependency) || !remaining.has(dependency))
    )
    const column = ready.length ? ready : [...remaining.values()]
    columns.push(column)
    column.forEach(node => { placed.add(node.task_id); remaining.delete(node.task_id) })
  }
  return columns
})
const dagCanvas = computed(() => ({
  width: Math.max(220, dagColumns.value.length * 252),
  height: Math.max(180, Math.max(...dagColumns.value.map(column => column.length), 1) * 132 + 54)
}))
const dagEdges = computed(() => {
  const positions = new Map()
  dagColumns.value.forEach((column, columnIndex) => {
    column.forEach((node, rowIndex) => {
      positions.set(node.task_id, { x: columnIndex * 252, y: rowIndex * 132 + 42 })
    })
  })
  return nodes.value.flatMap(node => (node.dependencies || []).flatMap(dependency => {
    const from = positions.get(dependency)
    const to = positions.get(node.task_id)
    if (!from || !to) return []
    const startX = from.x + 220
    const endX = to.x
    const midX = startX + Math.max(18, (endX - startX) / 2)
    return [{
      key: dependency + '->' + node.task_id,
      status: statusMeta(node.status).key,
      path: `M ${startX} ${from.y + 46} C ${midX} ${from.y + 46}, ${midX} ${to.y + 46}, ${endX} ${to.y + 46}`
    }]
  }))
})
const nodeStats = computed(() => nodes.value.reduce((stats, node) => {
  stats.total += 1
  const key = statusMeta(node.status).key
  if (key === 'success') stats.succeeded += 1
  if (key === 'running') stats.running += 1
  if (key === 'failed') stats.failed += 1
  if (key === 'blocked' || key === 'pending') stats.blocked += 1
  if (key === 'cached') stats.reused += 1
  return stats
}, { total: 0, succeeded: 0, running: 0, failed: 0, blocked: 0, reused: 0 }))
const failedNodes = computed(() => nodes.value.filter(node => statusMeta(node.status).key === 'failed'))
const canCancel = computed(() => ['queued', 'running'].includes(String(selectedStatus.value)))
const canResume = computed(() => ['failed', 'running', 'queued'].includes(String(selectedStatus.value)))
const recentEvents = computed(() => events.value.slice(-20).reverse())
const liveLabel = computed(() => selectedWorkflow.value?.active ? '实时更新中' : '已结束')

function nodeDependencies(node) {
  const lineage = node?.lineage || selectedWorkflow.value?.snapshot?.node_lineage?.[node?.task_id] || {}
  return (node?.dependencies || lineage?.dependencies || []).map(shortId)
}

function nodeArtifacts(node) {
  const result = selectedWorkflow.value?.snapshot?.node_results?.[node?.task_id]
  const data = result?.data || result || {}
  const paths = [
    ...(data.file_paths || []),
    ...(data.report_file_paths || []),
    ...(data.artifacts || []).map(item => item?.path || item?.locator?.path || item?.name).filter(Boolean)
  ]
  return [...new Set(paths.map(String))].slice(0, 6)
}
const lifecycleLabels = {
  'task.created': '任务已创建',
  'task.running': '开始执行',
  'task.succeeded': '执行完成',
  'task.failed': '执行失败',
  'task.cancelled': '任务已取消',
  'task.child_turn_completed': '子 Agent 完成一轮分析',
  'task.lineage_attached': '已关联上游结果',
  'task.contract_bound': '已绑定结果协议',
  'task.resources_imported': '已导入数据资源'
}
const nodeTimeline = computed(() => {
  if (!nodeHistory.value) return []
  const entries = [
    ...(nodeHistory.value.node_events || []).map(item => ({ ...item, source: 'node' })),
    ...(nodeHistory.value.child_events || []).map(item => ({ ...item, source: 'child' }))
  ]
  return entries.sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')))
    .map(item => ({
      key: item.source + '-' + item.sequence,
      timestamp: item.timestamp,
      label: (item.source === 'node' ? '节点' : '子 Agent') + '：' + (lifecycleLabels[item.type] || item.type) + '（' + statusMeta(item.status).label + '）'
    }))
})

function nodeDuration(taskId) {
  const rows = selectedWorkflow.value?.snapshot?.runtime?.events || []
  const own = rows.filter(item => item.task_id === taskId && item.timestamp)
  if (!own.length) return '未开始'
  const running = own.find(item => item.event_type === 'task.running') || own[0]
  const start = new Date(running.timestamp).getTime()
  const end = new Date(own.at(-1).timestamp).getTime()
  if (!Number.isFinite(start) || !Number.isFinite(end)) return '耗时未知'
  const elapsed = Math.max(0, Math.round((end - start) / 1000))
  return elapsed < 60 ? elapsed + ' 秒' : Math.floor(elapsed / 60) + ' 分 ' + elapsed % 60 + ' 秒'
}

function toolEventLabel(item) {
  if (item.type === 'agent_finish') return '子 Agent 已完成回答'
  if (item.type === 'tool_call') return '调用 ' + (item.tool_name || '工具')
  return (item.tool_name || '工具') + (item.success ? ' 执行成功' : ' 执行失败')
}

async function selectNode(taskId) {
  if (selectedNodeId.value === taskId) { selectedNodeId.value = ''; return }
  selectedNodeId.value = taskId
  nodeHistory.value = null
  nodeHistoryError.value = ''
  nodeHistoryLoading.value = true
  const workflowId = selectedId.value
  try {
    const history = await getSessionWorkflowNodeHistory(props.sessionId, workflowId, taskId)
    if (selectedId.value === workflowId && selectedNodeId.value === taskId) nodeHistory.value = history
  } catch (err) {
    if (selectedId.value === workflowId && selectedNodeId.value === taskId) nodeHistoryError.value = err?.message || '节点历史加载失败'
  } finally {
    if (selectedId.value === workflowId && selectedNodeId.value === taskId) nodeHistoryLoading.value = false
  }
}

async function loadMoreNodeHistory() {
  if (!nodeHistory.value?.has_more || nodeHistoryLoading.value) return
  nodeHistoryLoading.value = true
  try {
    const previous = nodeHistory.value
    const after = previous.execution_history.at(-1)?.sequence || 0
    const next = await getSessionWorkflowNodeHistory(props.sessionId, selectedId.value, selectedNodeId.value, { after })
    nodeHistory.value = { ...next, execution_history: [...previous.execution_history, ...next.execution_history] }
  } catch (err) {
    nodeHistoryError.value = err?.message || '更多节点记录加载失败'
  } finally { nodeHistoryLoading.value = false }
}

const MODE_LABELS = {
  query: '问数',
  query_monitoring: '监测问数',
  query_forecast: '预报问数',
  expert: '专家分析',
  expert_meteorology: '气象专家',
  expert_analysis: '常规分析专家',
  report: '报告',
  chart: '图表',
  knowledge: '知识'
}

function modeLabel(mode) {
  if (!mode) return '子 Agent'
  return MODE_LABELS[mode] || mode
}

function nodeTitle(node) {
  return node.payload?.goal || node.task_id || '未命名节点'
}

function eventKey(event) {
  return event.event_id || `${event.sequence || ''}-${event.type || ''}-${event.created_at || ''}`
}

function eventLabel(event) {
  if (event.event_type) return event.event_type + '：' + (event.task_id || '')
  if (event.type === 'runtime' && event.event) return event.event.message || (event.event.event_type || '节点事件') + '：' + (event.event.task_id || '')
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
  if (selectedId.value !== workflowId) { selectedNodeId.value = ''; nodeHistory.value = null }
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
  if (snapshotTimer) clearTimeout(snapshotTimer)
  snapshotTimer = null
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
        if (event.type === 'runtime' && !snapshotTimer) {
          snapshotTimer = setTimeout(async () => {
            snapshotTimer = null
            if (selectedId.value !== workflowId || controller.signal.aborted) return
            try {
              selectedWorkflow.value = await getSessionWorkflow(props.sessionId, workflowId)
              if (selectedNodeId.value) {
                const taskId = selectedNodeId.value
                const history = await getSessionWorkflowNodeHistory(props.sessionId, workflowId, taskId)
                if (selectedId.value === workflowId && selectedNodeId.value === taskId) nodeHistory.value = history
              }
            } catch { /* Stream remains active. */ }
          }, 500)
        }
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
  selectedNodeId.value = ''
  nodeHistory.value = null
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
.dag-canvas { position: relative; margin-top: 8px; overflow: auto; padding: 4px 4px 12px; border: 1px solid #e1e8f0; border-radius: 8px; background: #f5f8fb; }
.dag-grid { position: relative; z-index: 1; display: grid; grid-auto-flow: column; gap: 32px; padding: 0 8px 8px; }
.dag-edges { position: absolute; z-index: 0; top: 0; left: 0; min-width: 100%; min-height: 100%; overflow: visible; color: #9eafc1; pointer-events: none; }
.dag-edge { fill: none; stroke: currentColor; stroke-width: 1.6; opacity: .85; }
.dag-edge.edge-running { color: #2778c9; stroke-width: 2.2; }
.dag-edge.edge-failed { color: #d04444; }
.dag-column { display: grid; align-content: start; gap: 12px; min-width: 220px; }
.dag-column-label { display: flex; justify-content: space-between; margin: 0 2px 2px; color: #7b899a; font-size: 10px; font-weight: 700; text-transform: uppercase; }
.dag-column-label span { font-weight: 400; text-transform: none; }
.dag-node { min-height: 92px; padding: 9px 10px; border: 1px solid #dfe7ef; border-left: 3px solid #94a3b8; border-radius: 6px; background: #fff; box-shadow: 0 2px 5px rgba(36, 50, 71, .04); }
.dag-node.node-success { border-left-color: #1f9d69; }
.dag-node.node-running { border-left-color: #2778c9; }
.dag-node.node-failed { border-left-color: #d04444; }
.dag-node.node-blocked { border-left-color: #c58a1c; }
.dag-node.node-retrying { border-left-color: #8b5cf6; }
.dag-node.node-cached { border-left-color: #0f8b8d; }
.node-toggle { display: block; width: 100%; padding: 0; border: 0; background: none; color: inherit; text-align: left; cursor: pointer; }
.node-toggle:focus-visible { outline: 2px solid #2778c9; outline-offset: 3px; }
.node-detail { margin: 10px 0 0 16px; padding: 10px; border-top: 1px solid #e7edf4; color: #526173; font-size: 11px; overflow-wrap: anywhere; }
.node-detail h5 { margin: 12px 0 6px; font-size: 11px; color: #31445b; }
.node-meta, .history-empty { color: #8290a0; }
.history-error { color: #b42318; }
.node-answer { max-height: 240px; overflow: auto; white-space: pre-wrap; line-height: 1.5; }
.lineage-list { display: grid; gap: 4px; color: #526173; }
.lineage-list span { overflow-wrap: anywhere; }
.more-button { margin-top: 8px; padding: 4px 8px; border: 1px solid #cbd8e5; border-radius: 5px; background: #fff; color: #315b84; cursor: pointer; }
.node-title { display: flex; align-items: center; gap: 8px; }
.node-title strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.node-flags { display: flex; gap: 5px; margin: 5px 0 0 16px; }
.node-flags small { display: inline-block; margin: 0; padding: 2px 5px; border-radius: 3px; background: #e8f5f4; color: #0f7173; font-size: 9px; }
.node-flags small + small { background: #f1ebff; color: #6d42b5; }
.dag-node small { display: block; margin: 5px 0 0 16px; overflow: hidden; color: #7b899a; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.node-status-label { display: block; margin: 5px 0 0 16px; color: #617184; font-size: 10px; }
.event-list { display: grid; gap: 7px; margin: 8px 0 0; padding: 0; list-style: none; }
.event-list li { display: flex; gap: 9px; color: #526173; font-size: 11px; }
.event-time { flex: 0 0 58px; color: #8a98a8; font-variant-numeric: tabular-nums; }
.errors-section { padding: 10px; border: 1px solid #f1d2d2; border-radius: 7px; background: #fff8f8; color: #a33b3b; font-size: 11px; }
.errors-section p { margin: 6px 0 0; }
@media (max-width: 640px) { .summary-grid { grid-template-columns: repeat(2, 1fr); } .workflow-detail { padding: 12px; } }
</style>
