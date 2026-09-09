<template>
  <section class="smart-event-center">
    <header class="panel-header">
      <div>
        <p class="eyebrow">JIANGSU SMART EVENTS</p>
        <h2>智能事件中心</h2>
        <p class="description">告警事件统一列表展示，点击“详情”进入事件详情页面。</p>
      </div>
      <div class="header-actions">
        <button type="button" :disabled="loading" @click="loadEvents">刷新</button>
        <button type="button" class="close" @click="$emit('close')">关闭</button>
      </div>
    </header>

    <section v-if="viewMode === 'list'" class="event-list-page" aria-label="智能事件列表">
      <div class="list-toolbar">
        <div class="filter-row">
          <select v-model="statusFilter" aria-label="状态筛选">
            <option value="">全部状态</option>
            <option v-for="value in statusOptions" :key="value" :value="value">{{ value }}</option>
          </select>
          <select v-model="typeFilter" aria-label="事件类型筛选">
            <option value="">全部事件类型</option>
            <option v-for="value in typeOptions" :key="value" :value="value">{{ value }}</option>
          </select>
          <input v-model="keyword" type="search" placeholder="按事件编号、站点、名称检索" @keyup.enter="loadEvents" />
        </div>
        <span>共 {{ filteredEvents.length }} 条</span>
      </div>
      <div class="list-metrics">
        <div><span>事件总数</span><strong>{{ events.length }}</strong></div>
        <div><span>待 AI 研判</span><strong>{{ pendingCount }}</strong></div>
        <div><span>站点数</span><strong>{{ stationCount }}</strong></div>
        <div><span>最近同步</span><strong>{{ lastSyncTime }}</strong></div>
      </div>
      <div v-if="loading" class="state">正在加载事件...</div>
      <div v-else-if="error" class="state error">{{ error }}</div>
      <div v-else-if="!filteredEvents.length" class="state">暂无符合条件的智能事件</div>
      <div v-else class="event-table-wrap">
        <table class="event-table">
          <thead><tr><th>状态</th><th>事件名称</th><th>线索标签</th><th>AI事件类型</th><th>数据影响</th><th>等级</th><th>站点</th><th>时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="event in filteredEvents" :key="event.event_id" @click="openDetail(event.event_id)">
              <td><span class="table-chip" :class="statusClass(event)">{{ event.event_status || '待研判' }}</span></td>
              <td><div class="event-name"><strong>{{ event.event_name || event.initial_event_name || '待研判事件' }}</strong><small>{{ event.event_id }}</small></div></td>
              <td>{{ event.primary_clue_tag || event.source_alarm_rule_type || '告警事件' }}</td>
              <td>{{ event.ai_event_type || event.event_type || '待研判' }}</td>
              <td>{{ event.ai_data_impact || '待确认' }}</td>
              <td>{{ event.ai_suggested_level || '待研判' }}</td>
              <td>{{ event.site_name || event.site_id || '未知站点' }}</td>
              <td>{{ formatTime(event.event_start_time) }}</td>
              <td><button type="button" class="detail-button" @click.stop="openDetail(event.event_id)">详情</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-else class="event-detail" aria-label="智能事件详情">
        <div class="detail-toolbar"><button type="button" class="back-button" @click="backToList">← 返回事件列表</button></div>
        <div v-if="detailLoading" class="state">正在加载详情...</div>
        <section v-else-if="workspaceMode === 'compare'" class="compare-view" aria-label="事件对比">
          <header class="detail-header">
            <div><p class="eyebrow">EVENT COMPARISON</p><h3>事件对比</h3><p>由 Agent 调度的事件横向比较</p></div>
          </header>
          <article v-for="event in compareEvents" :key="event.event_id" class="compare-card">
            <strong>{{ event.event_name || event.initial_event_name }}</strong>
            <span>{{ event.site_name || event.site_id }} · {{ event.primary_clue_tag || event.event_type }}</span>
            <em>{{ event.event_status || '未研判' }}</em>
          </article>
        </section>
        <section v-else-if="workspaceMode === 'history' && selectedEvent" class="history-view" aria-label="事件操作历史">
          <header class="detail-header">
            <div><p class="eyebrow">OPERATION HISTORY</p><h3>操作历史</h3><p>{{ selectedEvent.event_name || selectedEvent.initial_event_name }}</p></div>
          </header>
          <div v-if="!operationRecords.length" class="state">暂无操作记录</div>
          <ol v-else class="history-list"><li v-for="(record, index) in operationRecords" :key="`${record.created_at || index}`"><strong>{{ record.action || record.operation || '事件操作' }}</strong><span>{{ record.message || record.summary || record.status || '已记录' }}</span><small>{{ formatTime(record.created_at || record.updated_at) }}</small></li></ol>
        </section>
        <div v-else-if="!selectedEvent" class="state">选择一个事件查看固定详情</div>
        <template v-else>
          <header class="detail-header">
            <div>
              <p class="eyebrow">EVENT DETAIL</p>
              <h3>{{ selectedEvent.event_name || selectedEvent.initial_event_name }}</h3>
              <p>{{ selectedEvent.site_name || selectedEvent.site_id }} · {{ selectedEvent.event_type }}</p>
            </div>
            <span class="status-badge">{{ selectedEvent.event_status || '未研判' }}</span>
          </header>
          <dl class="facts">
            <div><dt>发生时间</dt><dd>{{ formatTime(selectedEvent.event_start_time) }}</dd></div>
            <div><dt>主要线索</dt><dd>{{ selectedEvent.primary_clue_tag || '待识别' }}</dd></div>
            <div><dt>AI事件类型</dt><dd>{{ selectedEvent.ai_event_type || '待研判' }}</dd></div>
            <div><dt>原始告警状态</dt><dd>{{ selectedEvent.source_alarm_state || '未知' }}</dd></div>
            <div><dt>数据影响</dt><dd>{{ selectedEvent.ai_data_impact || '待确认' }}</dd></div>
            <div><dt>建议等级</dt><dd>{{ selectedEvent.ai_suggested_level || '待研判' }}</dd></div>
          </dl>
          <section class="judgment" aria-label="AI研判结果">
            <div class="section-title"><strong>AI 研判结果</strong><span>{{ judgment?.status || '尚未完成' }}</span></div>
            <p v-if="evidenceFocus" class="focus-note">当前证据焦点：{{ evidenceFocus }}</p>
            <p v-if="judgment?.final_response" class="final-response">{{ judgment.final_response }}</p>
            <p v-else class="muted">任务完成后，Agent 最终回复会持久化显示在这里。</p>
          </section>
          <section v-if="!selectedEvent.archived" class="confirmation" aria-label="人工确认">
            <div class="section-title"><strong>人工确认</strong><span>确认后才可归档</span></div>
            <div class="confirmation-grid">
              <input v-model="judgmentType" aria-label="最终事件类型" placeholder="最终事件类型" />
              <input v-model="judgmentLevel" aria-label="事件等级" placeholder="等级，例如 P1" />
            </div>
            <textarea v-model="judgmentNote" aria-label="研判说明" rows="3" placeholder="补充研判说明（可选）" />
            <div class="confirmation-actions">
              <button type="button" :disabled="confirmationBusy || !judgmentType.trim()" @click="saveJudgment">保存并确认</button>
              <button type="button" :disabled="confirmationBusy || !selectedEvent.manual_confirmation?.confirmed" @click="archiveSelectedEvent">归档事件</button>
              <span v-if="actionMessage" class="action-message">{{ actionMessage }}</span>
            </div>
          </section>
          <section class="task-section" aria-label="关联研判任务">
            <div class="section-title"><strong>关联任务</strong><span>{{ tasks.length }} 个</span></div>
            <button v-for="task in tasks" :key="task.task_id" type="button" class="task-card" @click="$emit('open-task', task)">
              <span><strong>{{ task.title || 'AI 研判任务' }}</strong><small>{{ task.status || '待执行' }}</small></span>
              <span class="task-arrow">进入任务 →</span>
            </button>
          </section>
        </template>
      </section>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import {
  archiveJiangsuSmartEvent,
  getJiangsuSmartEvent,
  listJiangsuSmartEventTasks,
  listJiangsuSmartEvents,
  submitJiangsuSmartEventJudgment,
} from '@/services/jiangsuSmartEventsApi.js'

const props = defineProps({
  initialEventId: { type: String, default: '' },
  workspaceCommand: { type: Object, default: null }
})
const emit = defineEmits(['close', 'open-task'])
const events = ref([])
const selectedId = ref(props.initialEventId || '')
const selectedEvent = ref(null)
const tasks = ref([])
const keyword = ref('')
const statusFilter = ref('')
const typeFilter = ref('')
const lastSync = ref(null)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const workspaceMode = ref('detail')
const compareEvents = ref([])
const evidenceFocus = ref('')
const judgmentType = ref('')
const judgmentLevel = ref('')
const judgmentNote = ref('')
const confirmationBusy = ref(false)
const actionMessage = ref('')
const viewMode = ref(props.initialEventId ? 'detail' : 'list')
const judgment = computed(() => selectedEvent.value?.ai_judgment || null)
const operationRecords = computed(() => Array.isArray(selectedEvent.value?.operation_records) ? selectedEvent.value.operation_records : [])
const statusOptions = computed(() => [...new Set(events.value.map(item => item.event_status).filter(Boolean))])
const typeOptions = computed(() => [...new Set(events.value.map(item => item.ai_event_type || item.event_type).filter(Boolean))])
const filteredEvents = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return events.value.filter(event => {
    const type = event.ai_event_type || event.event_type || ''
    const text = [event.event_id, event.event_name, event.initial_event_name, event.site_name, event.site_id, event.primary_clue_tag, event.source_alarm_rule_type].filter(Boolean).join(' ').toLowerCase()
    return (!statusFilter.value || event.event_status === statusFilter.value)
      && (!typeFilter.value || type === typeFilter.value)
      && (!query || text.includes(query))
  })
})
const pendingCount = computed(() => events.value.filter(item => !item.ai_judgment?.final_response).length)
const stationCount = computed(() => new Set(events.value.map(item => item.site_id || item.site_name).filter(Boolean)).size)
const lastSyncTime = computed(() => formatTime(lastSync.value))

const statusClass = event => {
  const status = String(event?.event_status || '')
  if (status.includes('完成') || status.includes('归档')) return 'success'
  if (status.includes('处理中') || status.includes('研判')) return 'warning'
  return 'pending'
}

const formatTime = value => {
  if (!value) return '时间未知'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

const selectEvent = async eventId => {
  selectedId.value = eventId
  detailLoading.value = true
  try {
    const [detail, taskPayload] = await Promise.all([
      getJiangsuSmartEvent(eventId, { refresh: false }),
      listJiangsuSmartEventTasks({ event_id: eventId })
    ])
    selectedEvent.value = detail.event || null
    tasks.value = taskPayload.tasks || []
    judgmentType.value = selectedEvent.value?.manual_confirmation?.event_type || selectedEvent.value?.ai_event_type || ''
    judgmentLevel.value = selectedEvent.value?.manual_confirmation?.level || selectedEvent.value?.ai_suggested_level || ''
    judgmentNote.value = selectedEvent.value?.manual_confirmation?.diagnosis_note || ''
    actionMessage.value = ''
    workspaceMode.value = 'detail'
  } catch (err) {
    error.value = err?.message || '事件详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

const openDetail = async eventId => {
  viewMode.value = 'detail'
  await selectEvent(eventId)
}

const backToList = () => {
  viewMode.value = 'list'
  workspaceMode.value = 'detail'
  error.value = ''
}

const saveJudgment = async () => {
  if (!selectedEvent.value || !judgmentType.value.trim()) return
  confirmationBusy.value = true
  actionMessage.value = ''
  try {
    const payload = await submitJiangsuSmartEventJudgment(selectedEvent.value.event_id, {
      event_type: judgmentType.value.trim(),
      level: judgmentLevel.value.trim() || null,
      diagnosis_note: judgmentNote.value.trim() || null,
      confirmed: true,
    })
    selectedEvent.value = payload.event || selectedEvent.value
    actionMessage.value = '已保存并确认'
  } catch (err) {
    actionMessage.value = err?.message || '确认失败'
  } finally {
    confirmationBusy.value = false
  }
}

const archiveSelectedEvent = async () => {
  if (!selectedEvent.value?.manual_confirmation?.confirmed) return
  confirmationBusy.value = true
  actionMessage.value = ''
  try {
    const payload = await archiveJiangsuSmartEvent(selectedEvent.value.event_id)
    selectedEvent.value = payload.event || selectedEvent.value
    actionMessage.value = '事件已归档并锁定'
  } catch (err) {
    actionMessage.value = err?.message || '归档失败'
  } finally {
    confirmationBusy.value = false
  }
}

const compare = async eventIds => {
  viewMode.value = 'detail'
  detailLoading.value = true
  try {
    const payloads = await Promise.all(eventIds.map(id => getJiangsuSmartEvent(id, { refresh: false })))
    compareEvents.value = payloads.map(payload => payload.event).filter(Boolean)
    workspaceMode.value = 'compare'
  } catch (err) {
    error.value = err?.message || '事件对比加载失败'
  } finally {
    detailLoading.value = false
  }
}

const loadEvents = async () => {
  loading.value = true
  error.value = ''
  try {
    const payload = await listJiangsuSmartEvents({ refresh: true })
    events.value = payload.events || []
    lastSync.value = payload.source_metadata?.last_sync?.synced_at || null
    const command = props.workspaceCommand
    if (command?.type === 'compare_events' && Array.isArray(command.event_ids)) {
      await compare(command.event_ids.map(String).filter(Boolean))
    } else if (command?.type === 'show_operation_history' && command.event_id) {
      workspaceMode.value = 'history'
      await openDetail(String(command.event_id))
      workspaceMode.value = 'history'
    } else if (command?.type === 'focus_evidence' && command.event_id) {
      evidenceFocus.value = command.focus || 'evidence'
      await openDetail(String(command.event_id))
    }
  } catch (err) {
    error.value = err?.message || '智能事件加载失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.initialEventId, value => { if (value && value !== selectedId.value) openDetail(value) })
watch(() => props.workspaceCommand, command => {
  if (!command) return
  if (command.type === 'open_event_detail' && command.event_id) openDetail(String(command.event_id))
  if (command.type === 'focus_evidence' && command.event_id) {
    evidenceFocus.value = command.focus || 'evidence'
    openDetail(String(command.event_id))
  }
  if (command.type === 'compare_events' && Array.isArray(command.event_ids)) compare(command.event_ids.map(String).filter(Boolean))
  if (command.type === 'show_operation_history' && command.event_id) {
    openDetail(String(command.event_id)).then(() => { workspaceMode.value = 'history' })
  }
  if (command.type === 'open_task' && command.task_id) {
    listJiangsuSmartEventTasks({ limit: 1000 }).then(payload => {
      const task = (payload.tasks || []).find(item => item.task_id === command.task_id || item.scheduled_task_id === command.task_id)
      if (task) emit('open-task', task)
    })
  }
  if (command.type === 'show_event_list' || command.type === 'filter_event_list') {
    viewMode.value = 'list'
    keyword.value = command.filters?.keyword || command.query?.keyword || ''
    loadEvents()
  }
}, { deep: true })
loadEvents()
</script>

<style scoped>
.smart-event-center { height: 100%; overflow: auto; padding: 24px; background: #f4f7fb; color: #17324d; }
.panel-header, .detail-header, .section-title, .list-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.panel-header { margin-bottom: 16px; }.eyebrow { margin: 0 0 5px; color: #2f6bff; font-size: 10px; letter-spacing: .14em; }.panel-header h2, .detail-header h3 { margin: 0; }.description, .detail-header p, .muted { color: #66758a; font-size: 12px; }.header-actions { display: flex; gap: 8px; }.header-actions button, .back-button, .task-card { border: 1px solid #c9d5e3; border-radius: 8px; background: #fff; color: #2f6bff; cursor: pointer; padding: 8px 12px; }.header-actions .close { color: #526171; }
.event-list-page, .event-detail { min-width: 0; border: 1px solid #dfe7f1; border-radius: 12px; background: #fff; box-shadow: 0 1px 2px rgba(25, 42, 70, .04); }.event-list-page { overflow: hidden; }.list-toolbar { padding: 14px 16px; border-bottom: 1px solid #dfe7f1; color: #66758a; font-size: 12px; }.filter-row { display: flex; flex-wrap: wrap; gap: 10px; flex: 1; }.filter-row input, .filter-row select { height: 36px; min-width: 150px; border: 1px solid #c9d5e3; border-radius: 8px; padding: 0 10px; background: #fff; }.filter-row input { min-width: 240px; flex: 1; }.list-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 12px 16px; border-bottom: 1px solid #edf2f7; background: #fbfcfe; }.list-metrics div { display: grid; gap: 5px; padding: 10px 12px; border: 1px solid #dfe7f1; border-radius: 10px; background: #fff; }.list-metrics span { color: #66758a; font-size: 12px; }.list-metrics strong { font-size: 20px; }.event-table-wrap { overflow: auto; }.event-table { width: 100%; min-width: 980px; border-collapse: collapse; table-layout: fixed; }.event-table th, .event-table td { padding: 12px 10px; border-bottom: 1px solid #edf2f7; vertical-align: middle; text-align: left; word-break: break-word; }.event-table th { color: #66758a; background: #fbfcfe; font-size: 12px; }.event-table td { color: #223040; font-size: 13px; }.event-table tbody tr { cursor: pointer; }.event-table tbody tr:hover { background: #f5f9ff; }.event-table th:nth-child(1) { width: 100px; }.event-table th:nth-child(2) { width: 190px; }.event-table th:nth-child(3) { width: 150px; }.event-table th:nth-child(4) { width: 140px; }.event-table th:nth-child(5) { width: 100px; }.event-table th:nth-child(6) { width: 90px; }.event-table th:nth-child(7) { width: 140px; }.event-table th:nth-child(8) { width: 170px; }.event-table th:nth-child(9) { width: 76px; }.event-name { display: grid; gap: 4px; }.event-name strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.event-name small { color: #66758a; font-size: 11px; }.table-chip { display: inline-flex; align-items: center; padding: 4px 9px; border-radius: 999px; font-size: 12px; white-space: nowrap; }.table-chip.pending { color: #526171; background: #edf2f7; }.table-chip.warning { color: #e07a1e; background: #fff2e2; }.table-chip.success { color: #1f9d65; background: #eaf9f1; }.detail-button { border: 1px solid #2f6bff; border-radius: 7px; color: #2f6bff; background: #fff; padding: 5px 10px; cursor: pointer; }.state { padding: 45px 10px; color: #66758a; text-align: center; }.state.error { color: #bd554c; }
.event-detail { padding: 20px; }.detail-toolbar { margin-bottom: 14px; }.detail-header { align-items: flex-start; padding-bottom: 16px; border-bottom: 1px solid #edf2f2; }.detail-header h3 { max-width: 600px; font-size: 20px; }.status-badge { color: #e07a1e; padding: 5px 8px; border-radius: 10px; background: #fff2e2; font-size: 11px; }.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 16px 0; }.facts div { padding: 10px; border-radius: 7px; background: #f5f9f9; }.facts dt { color: #80949a; font-size: 10px; }.facts dd { margin: 4px 0 0; color: #34545d; font-size: 12px; }.judgment, .task-section { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf2f2; }.section-title { color: #42616a; font-size: 12px; }.section-title span { color: #82969c; font-size: 10px; }.final-response { white-space: pre-wrap; line-height: 1.7; color: #334f57; font-size: 13px; }.task-card { display: flex; align-items: center; justify-content: space-between; width: 100%; margin-top: 8px; text-align: left; }.task-card span:first-child { display: grid; gap: 4px; }.task-card small { color: #83969c; }.task-arrow { white-space: nowrap; font-size: 11px; }.confirmation { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf2f2; }.confirmation-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }.confirmation input, .confirmation textarea { width: 100%; box-sizing: border-box; border: 1px solid #d9e6e7; border-radius: 6px; padding: 8px 9px; font: inherit; font-size: 12px; }.confirmation textarea { margin-top: 8px; resize: vertical; }.confirmation-actions { display: flex; align-items: center; gap: 8px; margin-top: 8px; }.confirmation-actions button { border: 1px solid #acd5d4; border-radius: 6px; background: #effafa; color: #286e73; cursor: pointer; padding: 7px 10px; font-size: 11px; }.confirmation-actions button:disabled { cursor: not-allowed; opacity: .5; }.action-message { color: #5d7c82; font-size: 11px; }
@media (max-width: 860px) { .smart-event-center { padding: 14px; }.list-toolbar { align-items: stretch; flex-direction: column; }.list-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.facts { grid-template-columns: 1fr; } }
</style>
