<template>
  <section ref="panelRef" class="workflow-panel" aria-label="工作流运行视图">
    <header class="workflow-header">
      <button v-if="selectedNode" class="back-action" type="button" @click="closeNodeInspection"><span aria-hidden="true">←</span> 执行列表</button>
      <div v-else><p class="eyebrow">Agent 协同运行</p><h2>工作流</h2></div>
      <button class="icon-action" type="button" title="刷新" aria-label="刷新" :disabled="loading || nodeHistoryLoading" @click="selectedNode ? refreshNodeHistory() : refresh()">↻</button>
    </header>

    <article v-if="selectedNode" class="subagent-review" aria-label="子 Agent 对话审查">
      <header class="review-heading">
        <p class="eyebrow">子 Agent 对话</p><h2>{{ nodeTitle(selectedNode) }}</h2><p>{{ nodeGoal(selectedNode) }}</p>
        <div class="review-meta"><span class="status-dot" :class="`status-${statusMeta(inspectionStatus).key}`"></span><strong>{{ statusMeta(inspectionStatus).label }}</strong><span>{{ modeLabel(nodeHistory?.child_mode || selectedNode.payload?.target_mode) }}</span><span>{{ nodeDuration(selectedNode.task_id) }}</span></div>
      </header>
      <div v-if="nodeHistoryLoading && !nodeHistory" class="detail-state">正在读取子 Agent 对话...</div>
      <div v-if="nodeHistoryError" class="state error" role="alert">{{ nodeHistoryError }}</div>
      <template v-if="nodeHistory">
        <section class="subagent-chat" aria-live="polite">
          <div class="conversation-list">
            <article v-for="message in nodeUserMessages" :key="message.id" class="conversation-message role-user">
              <div class="message-author"><strong>任务</strong><time v-if="message.timestamp">{{ formatTime(message.timestamp) }}</time></div>
              <div class="message-content">{{ messageContent(message.content) }}</div>
            </article>

            <article class="process-message" :class="{ running: isInspectionRunning }">
              <header class="process-heading">
                <span class="agent-mark">A</span>
                <span class="process-title"><strong>{{ modeLabel(nodeHistory.child_mode) }} 子 Agent</strong><small>{{ isInspectionRunning ? '正在工作' : '执行记录' }}</small></span>
                <span v-if="isInspectionRunning" class="live-indicator"><i></i>实时</span>
              </header>
              <div class="progress-line">
                <span v-if="isInspectionRunning" class="progress-spinner" aria-hidden="true"></span>
                <span v-else class="progress-complete" aria-hidden="true">✓</span>
                <strong>{{ nodeHistory.progress?.label || (isInspectionRunning ? '正在分析任务' : '分析已结束') }}</strong>
              </div>
              <ol v-if="toolActivities.length" class="tool-activity-list">
                <li v-for="item in toolActivities" :key="item.key" :class="`activity-${item.status}`">
                  <span class="activity-icon" aria-hidden="true">{{ item.status === 'running' ? '·' : item.status === 'failed' ? '×' : '✓' }}</span>
                  <span class="activity-main"><strong>{{ item.toolName }}</strong><small>{{ toolActivityStatus(item) }}</small></span>
                  <time v-if="item.timestamp">{{ formatTime(item.timestamp) }}</time>
                </li>
              </ol>
              <p v-else class="process-empty">{{ isInspectionRunning ? '正在理解任务并规划下一步...' : '本次分析未调用外部工具。' }}</p>
              <footer v-if="nodeHistory.progress?.tool_calls" class="process-summary">已调用 {{ nodeHistory.progress.tool_calls }} 个工具，完成 {{ nodeHistory.progress.tool_results }} 个</footer>
              <button v-if="nodeHistory.has_more" type="button" class="more-button" @click="loadMoreNodeHistory">加载更早记录</button>
            </article>

            <article v-for="message in nodeAssistantMessages" :key="message.id" class="conversation-message role-assistant">
              <div class="message-author"><strong>{{ modeLabel(nodeHistory.child_mode) }} 子 Agent</strong><time v-if="message.timestamp">{{ formatTime(message.timestamp) }}</time></div>
              <div class="message-content">{{ messageContent(message.content) }}</div>
            </article>
          </div>
        </section>
        <section v-if="nodeDependencies(selectedNode).length || nodeArtifacts(selectedNode).length" class="review-section">
          <div class="section-heading"><h3>数据血缘</h3><span>输入与产物</span></div>
          <div class="lineage-list"><span v-for="item in nodeDependencies(selectedNode)" :key="'input-' + item">输入：{{ item }}</span><span v-for="item in nodeArtifacts(selectedNode)" :key="'output-' + item">产物：{{ item }}</span></div>
        </section>
      </template>
    </article>

    <template v-else>
      <div v-if="error" class="state error" role="alert">{{ error }}</div>
      <div v-else-if="loading && workflows.length === 0" class="state">正在加载工作流...</div>
      <div v-else-if="workflows.length === 0" class="state empty"><strong>当前会话还没有工作流</strong><span>报告模式或专家模式开始协同分析后，运行状态会显示在这里。</span></div>
      <template v-else>
        <div class="workflow-list" role="listbox" aria-label="工作流列表">
          <button v-for="item in workflows" :key="item.workflow_id" type="button" class="workflow-item" :class="{ selected: selectedId === item.workflow_id }" role="option" :aria-selected="selectedId === item.workflow_id" @click="selectWorkflow(item.workflow_id)">
            <span class="status-dot" :class="`status-${statusMeta(item.status).key}`" aria-hidden="true"></span><span class="workflow-item-main"><strong>{{ shortId(item.workflow_id) }}</strong><small>{{ statusMeta(item.status).label }} · {{ nodeCount(item.snapshot) }} 个节点</small></span><span v-if="item.active" class="live-badge">运行中</span>
          </button>
        </div>
        <div v-if="detailLoading" class="detail-state">正在加载工作流详情...</div>
        <article v-else-if="selectedWorkflow" class="workflow-detail">
          <header class="detail-header"><div><p class="eyebrow">{{ selectedWorkflow.workflow_id }}</p><h3>{{ statusMeta(selectedStatus).label }}</h3></div><div class="detail-actions"><button v-if="canCancel" type="button" class="button danger" @click="cancel">取消</button><button v-if="canResume" type="button" class="button" @click="resume">恢复</button></div></header>
          <section class="detail-section">
            <div class="section-heading"><h4>执行顺序</h4><span>{{ liveLabel }}</span></div>
            <div class="workflow-stage-list" aria-label="工作流节点执行顺序">
              <section v-for="(stage, stageIndex) in nodeStages" :key="stageIndex" class="workflow-stage">
                <header class="stage-heading"><span>阶段 {{ stageIndex + 1 }}</span><small>{{ stage.length > 1 ? `并行 ${stage.length} 个节点` : '顺序执行' }}</small></header>
                <div class="stage-nodes">
                  <button v-for="(node, nodeIndex) in stage" :key="node.task_id" type="button" class="workflow-node-row" :class="`node-${statusMeta(node.status).key}`" @click="selectNode(node.task_id)">
                    <span class="step-index">{{ stageIndex + 1 }}{{ stage.length > 1 ? String.fromCharCode(65 + nodeIndex) : '' }}</span>
                    <span class="node-main"><span class="node-title"><span class="node-status" aria-hidden="true"></span><strong>{{ nodeTitle(node) }}</strong><small>{{ modeLabel(node.payload?.target_mode) }}</small></span><span class="node-summary">{{ nodeGoal(node) }}</span><span class="node-dependencies">{{ dependencyLabel(node) }}</span></span>
                    <span class="node-result"><strong>{{ statusMeta(node.status).label }}</strong><small>{{ nodeDuration(node.task_id) }}</small></span><span class="row-chevron" aria-hidden="true">›</span>
                  </button>
                </div>
              </section>
            </div>
          </section>
          <section v-if="failedNodes.length" class="detail-section errors-section"><h4>失败节点</h4><p v-for="node in failedNodes" :key="node.task_id">{{ nodeTitle(node) }}：{{ node.error || '节点执行失败' }}</p></section>
        </article>
      </template>
    </template>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { cancelSessionWorkflow, followSessionWorkflow, getSessionWorkflow, getSessionWorkflowEvents, getSessionWorkflowNodeHistory, listSessionWorkflows, resumeSessionWorkflow } from '@/services/workflowApi.js'

const props = defineProps({ sessionId: { type: String, default: '' } })
const workflows = ref([]); const selectedId = ref(''); const selectedWorkflow = ref(null); const events = ref([])
const loading = ref(false); const detailLoading = ref(false); const error = ref(''); const streamController = ref(null); const emptyRefreshTimer = ref(null)
const selectedNodeId = ref(''); const nodeHistory = ref(null); const nodeHistoryLoading = ref(false); const nodeHistoryError = ref('')
const panelRef = ref(null)
let snapshotTimer = null
let nodePollTimer = null

const statusMap = { queued: { key: 'pending', label: '排队中' }, pending: { key: 'pending', label: '等待执行' }, running: { key: 'running', label: '执行中' }, succeeded: { key: 'success', label: '已完成' }, success: { key: 'success', label: '已完成' }, failed: { key: 'failed', label: '失败' }, blocked: { key: 'blocked', label: '等待上游' }, retrying: { key: 'retrying', label: '重试中' }, cached: { key: 'cached', label: '已复用' }, reused: { key: 'cached', label: '已复用' }, cancelled: { key: 'cancelled', label: '已取消' } }
const modeLabels = { query: '问数', query_monitoring: '监测查询', query_forecast: '预报查询', expert: '专家分析', expert_meteorology: '气象专家', expert_analysis: '常规分析专家', report: '报告', chart: '图表', knowledge: '知识' }
const statusMeta = status => statusMap[String(status || '').toLowerCase()] || { key: 'unknown', label: '未知' }
const shortId = value => String(value || '').replace(/^workflow[-_:]?/, '').slice(0, 32)
const nodeCount = snapshot => Object.keys(snapshot?.graph || snapshot?.definition?.nodes || {}).length
const selectedStatus = computed(() => selectedWorkflow.value?.job_status || selectedWorkflow.value?.snapshot?.status || 'unknown')
const nodes = computed(() => {
  const snapshot = selectedWorkflow.value?.snapshot || {}; const graph = snapshot.graph || {}; const definitions = snapshot.definition?.nodes || []; const definitionMap = new Map(definitions.map(node => [node.task_id, node]))
  return Object.entries(graph).map(([taskId, node]) => ({ ...definitionMap.get(taskId), ...node, task_id: taskId, error: snapshot.node_errors?.[taskId], lineage: snapshot.node_lineage?.[taskId] }))
})
const selectedNode = computed(() => nodes.value.find(node => node.task_id === selectedNodeId.value) || null)
const nodeStages = computed(() => {
  const remaining = new Map(nodes.value.map(node => [node.task_id, node])); const placed = new Set(); const stages = []
  while (remaining.size) { const ready = [...remaining.values()].filter(node => (node.dependencies || []).every(dependency => placed.has(dependency) || !remaining.has(dependency))); const stage = ready.length ? ready : [...remaining.values()]; stages.push(stage); stage.forEach(node => { placed.add(node.task_id); remaining.delete(node.task_id) }) }
  return stages
})
const failedNodes = computed(() => nodes.value.filter(node => statusMeta(node.status).key === 'failed'))
const canCancel = computed(() => ['queued', 'running'].includes(String(selectedStatus.value))); const canResume = computed(() => ['failed', 'running', 'queued'].includes(String(selectedStatus.value)))
const liveLabel = computed(() => selectedWorkflow.value?.active ? '实时更新中' : '已结束')
const nodeConversation = computed(() => nodeHistory.value?.conversation || [])
const nodeUserMessages = computed(() => {
  const messages = nodeConversation.value.filter(message => message.role === 'user')
  return messages.length ? messages : [{ id: `${selectedNodeId.value}:task`, role: 'user', content: nodeGoal(selectedNode.value) }]
})
const nodeAssistantMessages = computed(() => nodeConversation.value.filter(message => message.role === 'assistant'))
const inspectionStatus = computed(() => nodeHistory.value?.status || selectedNode.value?.status || 'unknown')
const isInspectionRunning = computed(() => ['pending', 'running', 'retrying'].includes(statusMeta(inspectionStatus.value).key))
const toolActivities = computed(() => {
  const activities = []
  for (const event of nodeHistory.value?.execution_history || []) {
    if (event.type === 'tool_call') {
      activities.push({ key: event.id || `call-${event.sequence}`, toolName: event.tool_name || '工具', status: 'running', timestamp: event.timestamp })
      continue
    }
    if (event.type !== 'tool_result') continue
    const pending = [...activities].reverse().find(item => item.toolName === (event.tool_name || '工具') && item.status === 'running')
    if (pending) {
      pending.status = event.success === false ? 'failed' : 'done'
      pending.timestamp = event.timestamp || pending.timestamp
    } else {
      activities.push({ key: event.id || `result-${event.sequence}`, toolName: event.tool_name || '工具', status: event.success === false ? 'failed' : 'done', timestamp: event.timestamp })
    }
  }
  return activities
})

function modeLabel(mode) { return mode ? (modeLabels[mode] || mode) : '通用' }
function nodeTitle(node) { return String(node?.payload?.title || node?.title || node?.phase || node?.payload?.phase || node?.task_id || '未命名节点').replace(/[-_]+/g, ' ') }
function nodeGoal(node) { return String(node?.payload?.goal || node?.goal || '未提供任务说明') }
function nodeDependencies(node) { const lineage = node?.lineage || selectedWorkflow.value?.snapshot?.node_lineage?.[node?.task_id] || {}; return (node?.dependencies || lineage?.dependencies || []).map(id => nodeTitle(nodes.value.find(item => item.task_id === id) || { task_id: shortId(id) })) }
function nodeArtifacts(node) { const result = selectedWorkflow.value?.snapshot?.node_results?.[node?.task_id]; const data = result?.data || result || {}; return [...new Set([...(data.file_paths || []), ...(data.report_file_paths || []), ...(data.artifacts || []).map(item => item?.path || item?.locator?.path || item?.name).filter(Boolean)].map(String))].slice(0, 6) }
function dependencyLabel(node) { const dependencies = nodeDependencies(node); return dependencies.length ? '上游：' + dependencies.join('、') : '入口节点' }
function nodeDuration(taskId) { const own = (selectedWorkflow.value?.snapshot?.runtime?.events || []).filter(item => item.task_id === taskId && item.timestamp); if (!own.length) return '未开始'; const start = new Date((own.find(item => item.event_type === 'task.running') || own[0]).timestamp).getTime(); const end = new Date(own.at(-1).timestamp).getTime(); if (!Number.isFinite(start) || !Number.isFinite(end)) return '耗时未知'; const elapsed = Math.max(0, Math.round((end - start) / 1000)); return elapsed < 60 ? elapsed + ' 秒' : Math.floor(elapsed / 60) + ' 分 ' + elapsed % 60 + ' 秒' }
function messageContent(content) { if (typeof content === 'string') return content; if (Array.isArray(content)) return content.filter(item => item?.type === 'text' || typeof item === 'string').map(item => typeof item === 'string' ? item : item.text || '').join('\n'); return content && typeof content === 'object' ? String(content.text || content.content || '') : String(content || '') }
function toolActivityStatus(item) { return item.status === 'running' ? '调用中' : item.status === 'failed' ? '执行失败' : '已完成' }
function formatTime(value) { if (!value) return '--'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '--' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }

async function selectNode(taskId) { selectedNodeId.value = taskId; nodeHistory.value = null; nodeHistoryError.value = ''; await nextTick(); if (panelRef.value) panelRef.value.scrollTop = 0; await refreshNodeHistory() }
function stopNodePolling() { if (nodePollTimer !== null) { window.clearInterval(nodePollTimer); nodePollTimer = null } }
function syncNodePolling() {
  stopNodePolling()
  if (selectedNodeId.value && isInspectionRunning.value) nodePollTimer = window.setInterval(refreshNodeHistory, 1200)
}
function closeNodeInspection() { stopNodePolling(); selectedNodeId.value = ''; nodeHistory.value = null; nodeHistoryError.value = '' }
async function refreshNodeHistory() {
  if (!selectedNodeId.value || nodeHistoryLoading.value) return
  const panel = panelRef.value
  const shouldFollow = !nodeHistory.value || (panel && panel.scrollHeight - panel.scrollTop - panel.clientHeight < 80)
  nodeHistoryLoading.value = true
  const workflowId = selectedId.value; const taskId = selectedNodeId.value
  try {
    const history = await getSessionWorkflowNodeHistory(props.sessionId, workflowId, taskId)
    if (selectedId.value === workflowId && selectedNodeId.value === taskId) {
      nodeHistory.value = history
      nodeHistoryError.value = ''
      if (shouldFollow) await nextTick(() => { if (panelRef.value) panelRef.value.scrollTop = panelRef.value.scrollHeight })
    }
  } catch (err) {
    if (selectedId.value === workflowId && selectedNodeId.value === taskId) nodeHistoryError.value = err?.message || '子 Agent 对话加载失败'
  } finally {
    if (selectedId.value === workflowId && selectedNodeId.value === taskId) nodeHistoryLoading.value = false
  }
}
async function loadMoreNodeHistory() { if (!nodeHistory.value?.has_more || nodeHistoryLoading.value) return; nodeHistoryLoading.value = true; try { const previous = nodeHistory.value; const after = previous.execution_history.at(-1)?.sequence || 0; const next = await getSessionWorkflowNodeHistory(props.sessionId, selectedId.value, selectedNodeId.value, { after }); nodeHistory.value = { ...next, execution_history: [...previous.execution_history, ...next.execution_history] } } catch (err) { nodeHistoryError.value = err?.message || '更多节点记录加载失败' } finally { nodeHistoryLoading.value = false } }
function stopEmptyRefresh() { if (emptyRefreshTimer.value !== null) { window.clearInterval(emptyRefreshTimer.value); emptyRefreshTimer.value = null } }
function startEmptyRefresh() { if (emptyRefreshTimer.value === null) emptyRefreshTimer.value = window.setInterval(() => { if (!loading.value && props.sessionId) refresh() }, 2000) }
async function refresh() { if (!props.sessionId || loading.value) return; loading.value = true; error.value = ''; try { const payload = await listSessionWorkflows(props.sessionId); workflows.value = Array.isArray(payload?.workflows) ? payload.workflows : []; if (selectedId.value && workflows.value.some(item => item.workflow_id === selectedId.value)) { stopEmptyRefresh(); await selectWorkflow(selectedId.value, false) } else if (workflows.value.length) { stopEmptyRefresh(); await selectWorkflow((workflows.value.find(item => item.active) || workflows.value[0]).workflow_id, false) } else { selectedId.value = ''; selectedWorkflow.value = null; stopStream(); startEmptyRefresh() } } catch (err) { error.value = err?.message || '工作流列表加载失败' } finally { loading.value = false } }
async function selectWorkflow(workflowId, reload = true) { if (selectedId.value !== workflowId) closeNodeInspection(); selectedId.value = workflowId; detailLoading.value = true; error.value = ''; stopStream(); try { const item = workflows.value.find(row => row.workflow_id === workflowId); const detail = reload ? await getSessionWorkflow(props.sessionId, workflowId) : { ...item, snapshot: item?.snapshot || {} }; selectedWorkflow.value = detail; const eventPayload = await getSessionWorkflowEvents(props.sessionId, workflowId); events.value = Array.isArray(eventPayload?.events) ? eventPayload.events : []; if (detail.active || ['queued', 'running'].includes(String(detail.job_status || detail.snapshot?.status))) startStream(workflowId, events.value.at(-1)?.event_id || '0-0') } catch (err) { error.value = err?.message || '工作流详情加载失败' } finally { detailLoading.value = false } }
function stopStream() { if (snapshotTimer) clearTimeout(snapshotTimer); snapshotTimer = null; streamController.value?.abort(); streamController.value = null }
async function startStream(workflowId, afterEventId = '0-0') { const controller = new AbortController(); streamController.value = controller; try { await followSessionWorkflow(props.sessionId, workflowId, { afterEventId, signal: controller.signal, onEvent: event => { events.value.push(event); if (event.type === 'runtime' && !snapshotTimer) snapshotTimer = setTimeout(async () => { snapshotTimer = null; if (selectedId.value !== workflowId || controller.signal.aborted) return; try { selectedWorkflow.value = await getSessionWorkflow(props.sessionId, workflowId); if (selectedNodeId.value) await refreshNodeHistory() } catch { /* Stream remains active. */ } }, 500); if (event.type === 'workflow.terminal') selectedWorkflow.value = { ...selectedWorkflow.value, active: false, job_status: event.status, snapshot: { ...selectedWorkflow.value?.snapshot, status: event.status } } } }); if (!controller.signal.aborted && selectedWorkflow.value?.active) await selectWorkflow(workflowId) } catch (err) { if (err?.name !== 'AbortError') error.value = err?.message || '工作流事件流已断开' } }
async function cancel() { await runAction(() => cancelSessionWorkflow(props.sessionId, selectedId.value), '工作流取消失败') }
async function resume() { await runAction(() => resumeSessionWorkflow(props.sessionId, selectedId.value), '工作流恢复失败') }
async function runAction(action, fallback) { try { await action(); await refresh() } catch (err) { error.value = err?.message || fallback } }
watch(() => props.sessionId, () => { stopStream(); stopEmptyRefresh(); workflows.value = []; selectedId.value = ''; selectedWorkflow.value = null; events.value = []; closeNodeInspection(); if (props.sessionId) refresh() })
watch(() => [selectedNodeId.value, inspectionStatus.value], syncNodePolling, { immediate: true })
onMounted(() => { if (props.sessionId) refresh() }); onBeforeUnmount(() => { stopStream(); stopEmptyRefresh(); stopNodePolling() })
</script>

<style scoped>
.workflow-panel { height: 100%; overflow: auto; background: #f7f9fb; color: #243247; }
.workflow-header, .detail-header, .section-heading, .review-meta, .message-author { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.workflow-header { position: sticky; z-index: 3; top: 0; min-height: 65px; padding: 12px 18px; border-bottom: 1px solid #e3e8ee; background: #fff; }
.workflow-header h2, .detail-header h3, .section-heading h3, .section-heading h4, .review-heading h2 { margin: 0; }
.workflow-header h2 { font-size: 20px; }.eyebrow { margin: 0 0 4px; color: #75849a; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.icon-action { width: 32px; height: 32px; border: 1px solid #dbe4ee; border-radius: 7px; background: #fff; color: #315b84; font-size: 20px; cursor: pointer; }.icon-action:disabled { opacity: .5; cursor: wait; }
.back-action { display: inline-flex; align-items: center; gap: 7px; min-height: 34px; padding: 0 4px; border: 0; background: transparent; color: #315b84; font-weight: 650; cursor: pointer; }.back-action span { font-size: 20px; }
.state, .detail-state { padding: 30px 18px; color: #6c7b8e; text-align: center; }.state.error { color: #b42318; }.empty { display: grid; gap: 6px; }.empty strong { color: #36485e; }
.workflow-list { display: grid; gap: 6px; padding: 12px; border-bottom: 1px solid #e5ebf2; }.workflow-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px; border: 1px solid transparent; border-radius: 7px; background: #fff; color: inherit; text-align: left; cursor: pointer; }.workflow-item:hover, .workflow-item.selected { border-color: #bcd5ee; background: #f2f7fc; }
.status-dot, .node-status { display: inline-block; flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }.status-success, .node-success .node-status { background: #16845b; }.status-running, .node-running .node-status { background: #2778c9; box-shadow: 0 0 0 3px #dceeff; }.status-failed, .node-failed .node-status { background: #d04444; }.status-blocked, .node-blocked .node-status { background: #c58a1c; }.status-cancelled, .node-cancelled .node-status { background: #7b8794; }
.workflow-item-main { display: grid; gap: 3px; min-width: 0; flex: 1; }.workflow-item-main strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }.workflow-item-main small { color: #7b899a; font-size: 11px; }.live-badge { padding: 2px 6px; border-radius: 4px; background: #e4f1ff; color: #2169a8; font-size: 10px; }
.workflow-detail { padding: 16px; }.detail-header h3 { font-size: 17px; }.detail-actions { display: flex; gap: 6px; }.button, .more-button { min-height: 30px; padding: 5px 10px; border: 1px solid #cbd8e5; border-radius: 6px; background: #fff; color: #315b84; cursor: pointer; }.button.danger { border-color: #efc2c2; color: #b42318; }
.detail-section { margin-top: 20px; }.section-heading h3, .section-heading h4, .detail-section > h4 { font-size: 13px; }.section-heading span { color: #8290a0; font-size: 11px; }
.workflow-stage-list { margin-top: 9px; overflow: hidden; border: 1px solid #dfe6ed; border-radius: 7px; background: #fff; }.workflow-stage + .workflow-stage { border-top: 1px solid #dfe6ed; }.stage-heading { display: flex; align-items: center; justify-content: space-between; padding: 7px 11px; background: #edf2f6; color: #4d5f73; font-size: 11px; font-weight: 700; }.stage-heading small { color: #728196; font-size: 10px; font-weight: 500; }
.workflow-node-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto 12px; align-items: center; gap: 9px; width: 100%; min-height: 82px; padding: 11px; border: 0; border-left: 3px solid transparent; background: #fff; color: inherit; text-align: left; cursor: pointer; }.workflow-node-row + .workflow-node-row { border-top: 1px solid #edf1f5; }.workflow-node-row:hover { background: #f6f9fc; }.workflow-node-row:focus-visible { outline: 2px solid #2778c9; outline-offset: -2px; }.workflow-node-row.node-running { border-left-color: #2778c9; }.workflow-node-row.node-failed { border-left-color: #d04444; }.workflow-node-row.node-success { border-left-color: #16845b; }
.step-index { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%; background: #e9eef3; color: #53677c; font-size: 10px; font-weight: 700; }.node-main { display: grid; gap: 5px; min-width: 0; }.node-title { display: flex; align-items: center; gap: 7px; min-width: 0; }.node-title strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }.node-title small { flex: 0 0 auto; color: #728196; font-size: 9px; }.node-summary, .node-dependencies { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #68788a; font-size: 10px; }.node-dependencies { color: #8491a0; }.node-result { display: grid; gap: 4px; text-align: right; }.node-result strong { font-size: 10px; }.node-result small { color: #8491a0; font-size: 9px; white-space: nowrap; }.row-chevron { color: #8795a5; font-size: 20px; }
.errors-section { padding: 10px; border: 1px solid #f1d2d2; border-radius: 7px; background: #fff8f8; color: #a33b3b; font-size: 11px; }.errors-section p { margin: 6px 0 0; }
.subagent-review { padding-bottom: 24px; }.review-heading { padding: 20px 18px 17px; border-bottom: 1px solid #e3e8ee; background: #fff; }.review-heading h2 { font-size: 18px; }.review-heading > p:not(.eyebrow) { margin: 8px 0 0; color: #617184; font-size: 12px; line-height: 1.6; }.review-meta { justify-content: flex-start; flex-wrap: wrap; margin-top: 11px; color: #75849a; font-size: 10px; }.review-meta strong { color: #405269; }.review-section { padding: 18px; border-bottom: 1px solid #e3e8ee; }
.subagent-chat { padding: 18px; border-bottom: 1px solid #e3e8ee; background: #f7f9fb; }.conversation-list { display: grid; gap: 14px; }.conversation-message { max-width: 94%; padding: 12px; border: 1px solid #dfe6ed; border-radius: 7px; background: #fff; }.conversation-message.role-user { justify-self: end; width: calc(100% - 22px); background: #eef3f7; }.conversation-message.role-assistant { justify-self: start; }.message-author strong { color: #3d5066; font-size: 11px; }.message-author time { color: #8a98a8; font-size: 9px; }.message-content { margin-top: 8px; overflow-wrap: anywhere; color: #34485f; font-size: 12px; line-height: 1.65; white-space: pre-wrap; }
.process-message { overflow: hidden; border: 1px solid #d9e2ec; border-radius: 7px; background: #fff; }.process-message.running { border-color: #bad6ef; }.process-heading { display: flex; align-items: center; gap: 9px; padding: 10px 12px; border-bottom: 1px solid #e6ebf1; }.agent-mark { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: #284e72; color: #fff; font-size: 10px; font-weight: 700; }.process-title { display: grid; gap: 1px; min-width: 0; flex: 1; }.process-title strong { color: #34485f; font-size: 11px; }.process-title small { color: #8491a0; font-size: 9px; }.live-indicator { display: inline-flex; align-items: center; gap: 5px; color: #2778c9; font-size: 9px; }.live-indicator i { width: 6px; height: 6px; border-radius: 50%; background: #2778c9; animation: live-pulse 1.4s ease-in-out infinite; }.progress-line { display: flex; align-items: center; gap: 8px; padding: 11px 12px 7px; color: #405269; font-size: 11px; }.progress-spinner { width: 12px; height: 12px; border: 2px solid #cfe0f1; border-top-color: #2778c9; border-radius: 50%; animation: progress-spin .9s linear infinite; }.progress-complete { color: #16845b; font-weight: 700; }.tool-activity-list { margin: 3px 12px 9px 26px; padding: 0; border-left: 1px solid #dce4ec; list-style: none; }.tool-activity-list li { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; align-items: center; gap: 7px; min-height: 39px; margin-left: -10px; color: #526173; }.activity-icon { display: grid; place-items: center; width: 19px; height: 19px; border: 1px solid #cad6e2; border-radius: 50%; background: #fff; color: #16845b; font-size: 10px; font-weight: 700; }.activity-running .activity-icon { border-color: #9fc6e9; color: #2778c9; font-size: 16px; }.activity-failed .activity-icon { border-color: #efb8b8; color: #c63e3e; }.activity-main { display: grid; gap: 2px; min-width: 0; }.activity-main strong { overflow: hidden; color: #405269; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.activity-main small, .tool-activity-list time { color: #8491a0; font-size: 9px; }.tool-activity-list time { white-space: nowrap; }.process-empty { margin: 2px 12px 11px 40px; color: #78879a; font-size: 10px; }.process-summary { padding: 8px 12px; border-top: 1px solid #edf1f5; color: #738296; font-size: 9px; }.history-empty { margin: 12px 0 0; color: #8290a0; font-size: 11px; }.more-button { margin: 0 12px 10px; }.lineage-list { display: grid; gap: 6px; margin-top: 11px; color: #526173; font-size: 11px; }.lineage-list span { overflow-wrap: anywhere; }
@keyframes progress-spin { to { transform: rotate(360deg); } }
@keyframes live-pulse { 50% { opacity: .35; } }
@media (max-width: 640px) { .workflow-detail, .review-section, .subagent-chat { padding: 12px; }.workflow-node-row { grid-template-columns: 26px minmax(0, 1fr) 12px; }.node-result { display: none; }.review-heading { padding: 16px 12px; } }
@media (prefers-reduced-motion: reduce) { .live-indicator i, .progress-spinner { animation: none; } }
</style>
