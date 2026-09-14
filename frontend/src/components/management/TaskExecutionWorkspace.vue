<template>
  <section class="task-workspace">
    <header class="workspace-header">
      <div>
        <h2>{{ task?.workspace_entry?.title || task?.name || '告警溯源' }}</h2>
        <p class="workspace-description">按执行日期查看分析记录和文件产物</p>
      </div>
    </header>

    <div v-if="loading" class="state">正在加载分析记录...</div>
    <div v-else-if="error" class="state error">{{ error }}</div>
    <div v-else-if="normalizedExecutions.length === 0" class="state">暂无分析记录</div>
    <div v-else class="workspace-body">
      <div class="record-groups">
        <section v-for="group in groupedExecutions" :key="group.date" class="record-group">
          <h3>{{ group.label }}</h3>
          <div class="record-list">
            <article
            v-for="record in group.records"
            :key="record.execution_id"
            class="record-card"
            :class="{ selected: selectedRecord?.execution_id === record.execution_id }"
            @click="selectRecord(record)"
          >
              <div class="record-main">
                <strong>{{ formatExecutionTitle(record) }}</strong>
                <span :class="['status', `status-${statusMeta(record.status).key}`]">{{ statusMeta(record.status).label }}</span>
              </div>
              <div class="record-meta">
                <span>{{ record.status || 'pending' }}</span>
                <span v-if="record.duration_seconds">耗时 {{ formatDuration(record.duration_seconds) }}</span>
                <span v-if="isWorkflowRecord(record)">工作流结果</span>
                <span v-else-if="canOpenConversation(record)">可打开对话</span>
              </div>
              <div class="artifacts">
                <span v-for="artifact in record.artifacts" :key="artifact" class="artifact-chip">文件 {{ artifact }}</span>
                <span v-if="record.artifacts.length === 0" class="no-artifact">暂无文件产物</span>
              </div>
            </article>
          </div>
        </section>
      </div>
      <aside v-if="selectedRecord" class="record-detail" aria-live="polite">
        <div class="detail-header">
          <div>
            <p class="detail-eyebrow">{{ isWorkflowRecord(selectedRecord) ? '工作流执行结果' : 'Agent 执行结果' }}</p>
            <h3>{{ formatExecutionTitle(selectedRecord) }}</h3>
          </div>
          <button v-if="canOpenConversation(selectedRecord)" type="button" class="detail-action" @click="restore(selectedRecord)">打开对话</button>
        </div>
        <div class="detail-meta">
          <span :class="['status', `status-${statusMeta(selectedRecord.status).key}`]">{{ statusMeta(selectedRecord.status).label }}</span>
          <span v-if="selectedRecord.completed_at">完成于 {{ formatDateTime(selectedRecord.completed_at) }}</span>
          <span v-if="selectedRecord.duration_seconds">耗时 {{ formatDuration(selectedRecord.duration_seconds) }}</span>
        </div>
        <div v-if="selectedRecord.error_message" class="detail-error">{{ selectedRecord.error_message }}</div>
        <section class="result-section">
          <h4>最终返回</h4>
          <div v-if="selectedRecord.result_message" class="result-message">{{ selectedRecord.result_message }}</div>
          <p v-else class="detail-empty">该执行没有保存可展示的返回正文。</p>
        </section>
        <section class="result-section">
          <h4>文件产物 <span>{{ selectedRecord.artifacts.length }}</span></h4>
          <div v-if="selectedRecord.artifacts.length" class="detail-artifacts">
            <span v-for="artifact in selectedRecord.artifacts" :key="artifact" class="artifact-chip">{{ artifact }}</span>
          </div>
          <p v-else class="detail-empty">本次执行没有文件产物。</p>
        </section>
        <section v-if="selectedRecord.artifactUrls.length" class="result-section">
          <h4>图片预览</h4>
          <div class="artifact-previews">
            <a v-for="(url, index) in selectedRecord.artifactUrls" :key="url" :href="url" target="_blank" rel="noopener" class="artifact-preview">
              <img :src="url" :alt="selectedRecord.artifacts[index] || `附件 ${index + 1}`" loading="lazy" />
              <span>{{ selectedRecord.artifacts[index] || `附件 ${index + 1}` }}</span>
            </a>
          </div>
        </section>
      </aside>
      <nav v-if="pagination.totalPages > 1" class="pagination" aria-label="执行记录分页">
        <button type="button" :disabled="loading || pagination.page <= 1" @click="changePage(pagination.page - 1)">
          上一页
        </button>
        <span>第 {{ pagination.page }} / {{ pagination.totalPages }} 页，共 {{ pagination.total }} 条</span>
        <button type="button" :disabled="loading || pagination.page >= pagination.totalPages" @click="changePage(pagination.page + 1)">
          下一页
        </button>
      </nav>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'
import { gatewayUrl } from '@/auth/http.js'

const props = defineProps({ task: { type: Object, default: null } })
const emit = defineEmits(['close', 'restore-execution-session'])
const store = useScheduledTasksStore()
const executions = ref([])
const loading = ref(false)
const error = ref('')
const pagination = ref({ page: 1, pageSize: 10, total: 0, totalPages: 0 })
const selectedRecord = ref(null)

const statusMap = {
  success: { key: 'success', label: '成功' },
  failed: { key: 'failed', label: '失败' },
  running: { key: 'running', label: '执行中' },
  pending: { key: 'pending', label: '等待执行' },
  timeout: { key: 'failed', label: '超时' },
  cancelled: { key: 'failed', label: '已取消' }
}

const normalizedExecutions = computed(() => executions.value.map(execution => ({
  ...execution,
  artifacts: Array.isArray(execution.artifacts) ? execution.artifacts : [],
  artifactUrls: Array.isArray(execution.artifact_urls) ? execution.artifact_urls.map(gatewayUrl) : []
})))
const groupedExecutions = computed(() => {
  const groups = new Map()
  for (const record of normalizedExecutions.value) {
    const date = record.started_at ? new Date(record.started_at) : null
    const key = date && !Number.isNaN(date.getTime())
      ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
      : 'unknown'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(record)
  }
  return [...groups.entries()].map(([date, records]) => ({
    date,
    label: date === 'unknown' ? '日期未知' : date,
    records
  }))
})
const statusMeta = status => statusMap[status] || { key: 'unknown', label: '未知' }
const formatExecutionTitle = (record) => {
  const taskName = record?.task_name || props.task?.name || '分析任务'
  const date = record?.started_at ? new Date(record.started_at) : null
  if (!date || Number.isNaN(date.getTime())) return taskName

  const pad = part => String(part).padStart(2, '0')
  const executionTime = [
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  ].join(' ')
  return `${executionTime} ${taskName}`
}
const formatDuration = seconds => seconds < 60 ? `${Math.round(seconds)}秒` : `${Math.floor(seconds / 60)}分${Math.round(seconds % 60)}秒`
const isWorkflowRecord = record => record?.conversation_available === false || props.task?.execution_mode === 'workflow'
const canOpenConversation = record => record?.conversation_available !== false && Boolean(record?.session_id) && !isWorkflowRecord(record)
const formatDateTime = value => {
  const date = value ? new Date(value) : null
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString('zh-CN', { hour12: false }) : '时间未知'
}
const selectRecord = record => { selectedRecord.value = record }
const restore = record => { if (record.session_id) emit('restore-execution-session', record.session_id) }

const load = async (page = 1) => {
  const taskId = props.task?.task_id
  if (!taskId) {
    executions.value = []
    error.value = ''
    pagination.value = { page: 1, pageSize: 10, total: 0, totalPages: 0 }
    return
  }

  loading.value = true
  error.value = ''
  try {
    const result = await store.fetchTaskExecutions(taskId, {
      page,
      pageSize: pagination.value.pageSize
    })
    executions.value = result.executions
    selectedRecord.value = null
    pagination.value = {
      page: result.page,
      pageSize: result.pageSize,
      total: result.total,
      totalPages: result.totalPages
    }
  } catch (err) {
    console.error(`Failed to fetch executions for scheduled task ${taskId}:`, err)
    error.value = '分析记录加载失败，请重试'
  } finally {
    loading.value = false
  }
}

const changePage = page => {
  if (page < 1 || page > pagination.value.totalPages || page === pagination.value.page) return
  load(page)
}

watch(() => props.task?.task_id, () => load(1), { immediate: true })
</script>

<style scoped>
.task-workspace { height: 100%; overflow: auto; padding: 28px; background: #f7f9fc; }
.workspace-header { display: flex; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.eyebrow { margin: 0; color: #1976d2; font-size: 13px; }
h2 { margin: 4px 0; font-size: 22px; color: #17223b; }
.workspace-description { margin: 0; color: #64748b; }
.workspace-body { display: grid; grid-template-columns: minmax(360px, .85fr) minmax(420px, 1.15fr); gap: 20px; align-items: start; }
.record-list { display: grid; gap: 10px; }
.record-card { display: block; width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; padding: 15px 17px; text-align: left; cursor: pointer; }
.record-card:hover, .record-card.selected { border-color: #90caf9; background: #f8fbff; }
.record-main, .record-meta, .artifacts { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.record-main strong { min-width: 100px; color: #17223b; font-size: 16px; }
.record-meta, .no-artifact { color: #64748b; font-size: 13px; }
.status { margin-left: auto; font-size: 13px; font-weight: 600; }
.status-success { color: #16803c; }.status-failed { color: #c2413b; }.status-running { color: #1976d2; }.status-pending, .status-unknown { color: #64748b; }
.record-group + .record-group { margin-top: 22px; }
.record-group h3 { margin: 0 0 9px; color: #334155; font-size: 15px; }
.record-meta { margin-top: 8px; }
.artifacts { margin-top: 11px; }
.artifact-chip { padding: 4px 8px; border-radius: 4px; background: #eef5ff; color: #275a9a; font-size: 12px; }
.state { padding: 48px; color: #64748b; text-align: center; }.state.error { color: #c2413b; }
.record-detail { position: sticky; top: 0; min-height: 360px; border: 1px solid #dbe4ef; border-radius: 8px; background: #fff; padding: 20px; box-shadow: 0 8px 24px rgba(30, 64, 95, .06); }
.detail-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; border-bottom: 1px solid #edf2f7; padding-bottom: 14px; }
.detail-eyebrow { margin: 0 0 5px; color: #1976d2; font-size: 12px; font-weight: 700; }
.detail-header h3 { margin: 0; color: #17223b; font-size: 17px; line-height: 1.4; }
.detail-action { flex: none; border: 1px solid #90caf9; border-radius: 6px; background: #f8fbff; color: #1769aa; padding: 7px 10px; cursor: pointer; }
.detail-meta { display: flex; flex-wrap: wrap; gap: 12px; margin: 13px 0; color: #64748b; font-size: 13px; }
.result-section { margin-top: 18px; }.result-section h4 { display: flex; justify-content: space-between; margin: 0 0 9px; color: #334155; font-size: 14px; }.result-section h4 span { color: #94a3b8; font-weight: 400; }
.result-message { white-space: pre-wrap; max-height: 460px; overflow: auto; border: 1px solid #edf2f7; border-radius: 6px; background: #fbfdff; padding: 14px; color: #1e293b; font-size: 14px; line-height: 1.75; }
.detail-artifacts { display: flex; flex-wrap: wrap; gap: 8px; }.detail-empty { margin: 0; color: #94a3b8; font-size: 13px; }.detail-error { border-left: 3px solid #dc6b63; background: #fff6f5; padding: 10px 12px; color: #b42318; font-size: 13px; line-height: 1.5; }
.artifact-previews { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }.artifact-preview { display: block; overflow: hidden; border: 1px solid #dbe4ef; border-radius: 6px; color: #475569; text-decoration: none; }.artifact-preview img { display: block; width: 100%; max-height: 180px; object-fit: contain; background: #f8fafc; }.artifact-preview span { display: block; overflow: hidden; padding: 6px 8px; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.pagination { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 14px; margin-top: 20px; color: #64748b; font-size: 13px; }
.pagination button { min-width: 72px; padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #334155; cursor: pointer; }
.pagination button:disabled { opacity: .45; cursor: not-allowed; }
@media (max-width: 980px) { .workspace-body { grid-template-columns: 1fr; }.record-detail { position: static; } }
@media (max-width: 700px) { .task-workspace { padding: 18px; }.status { margin-left: 0; } }
</style>
