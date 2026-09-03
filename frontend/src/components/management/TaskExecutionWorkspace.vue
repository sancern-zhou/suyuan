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
    <div v-else class="record-groups">
      <section v-for="group in groupedExecutions" :key="group.date" class="record-group">
        <h3>{{ group.label }}</h3>
        <div class="record-list">
          <button
            v-for="record in group.records"
            :key="record.execution_id"
            type="button"
            class="record-card"
            :disabled="!record.session_id"
            :title="record.session_id ? '打开本次分析详情' : '该记录未生成可查看的会话'"
            @click="restore(record)"
          >
            <div class="record-main">
              <strong>{{ formatExecutionTitle(record) }}</strong>
              <span :class="['status', `status-${statusMeta(record.status).key}`]">{{ statusMeta(record.status).label }}</span>
            </div>
            <div class="record-meta">
              <span>{{ record.status || 'pending' }}</span>
              <span v-if="record.duration_seconds">耗时 {{ formatDuration(record.duration_seconds) }}</span>
            </div>
            <div class="artifacts">
              <span v-for="artifact in record.artifacts" :key="artifact" class="artifact-chip">📄 {{ artifact }}</span>
              <span v-if="record.artifacts.length === 0" class="no-artifact">暂无文件产物</span>
            </div>
          </button>
        </div>
      </section>
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

const props = defineProps({ task: { type: Object, default: null } })
const emit = defineEmits(['close', 'restore-execution-session'])
const store = useScheduledTasksStore()
const executions = ref([])
const loading = ref(false)
const error = ref('')
const pagination = ref({ page: 1, pageSize: 10, total: 0, totalPages: 0 })

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
  artifacts: Array.isArray(execution.artifacts) ? execution.artifacts : []
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
.record-list { display: grid; gap: 10px; }
.record-card { display: block; width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; padding: 15px 17px; text-align: left; cursor: pointer; }
.record-card:hover:not(:disabled) { border-color: #90caf9; background: #f8fbff; }
.record-card:disabled { opacity: .65; cursor: not-allowed; }
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
.pagination { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 14px; margin-top: 20px; color: #64748b; font-size: 13px; }
.pagination button { min-width: 72px; padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #334155; cursor: pointer; }
.pagination button:disabled { opacity: .45; cursor: not-allowed; }
@media (max-width: 700px) { .task-workspace { padding: 18px; }.status { margin-left: 0; } }
</style>
