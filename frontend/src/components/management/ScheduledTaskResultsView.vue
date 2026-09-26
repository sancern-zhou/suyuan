<template>
  <section class="task-results-view">
    <div v-if="error && results.length === 0" class="state error">
      <p>{{ error }}</p>
      <button type="button" @click="reload">重试</button>
    </div>

    <template v-else>
      <div class="results-toolbar">
        <label class="toolbar-field">
          <span>开始日期</span>
          <input v-model="filters.startDate" type="date" @change="applyFilters" />
        </label>
        <label class="toolbar-field">
          <span>结束日期</span>
          <input v-model="filters.endDate" type="date" @change="applyFilters" />
        </label>
        <label v-if="stationOptions.length" class="toolbar-field">
          <span>站点</span>
          <select v-model="filters.stationId" @change="applyFilters">
            <option value="">全部站点</option>
            <option v-for="station in stationOptions" :key="station.station_id" :value="station.station_id">
              {{ station.station_name || station.station_id }}
            </option>
          </select>
        </label>
        <label v-if="pollutantOptions.length" class="toolbar-field">
          <span>污染物</span>
          <select v-model="filters.pollutant" @change="applyFilters">
            <option value="">全部污染物</option>
            <option v-for="pollutant in pollutantOptions" :key="pollutant" :value="pollutant">
              {{ pollutant }}
            </option>
          </select>
        </label>
        <button type="button" class="toolbar-btn" @click="resetFilters">重置</button>
        <button type="button" class="toolbar-btn primary" :disabled="loading" @click="reload">
          {{ loading ? '加载中...' : '查询' }}
        </button>
      </div>

      <div v-if="loading" class="state">正在加载执行结果...</div>
      <div v-else-if="results.length === 0" class="state">暂无符合条件的执行结果</div>

      <div v-else class="results-body">
        <div class="record-table-wrap">
          <table class="record-table">
            <thead>
              <tr>
                <th class="col-time">时间</th>
                <th class="col-status">状态</th>
                <th class="col-city">城市</th>
                <th class="col-station">站点</th>
                <th class="col-pollutant">污染物</th>
                <th class="col-brief">结论</th>
                <th class="col-assets">产物</th>
                <th class="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="record in results"
                :key="record.execution_id"
              >
                <td class="col-time">{{ formatRowTime(record) }}</td>
                <td class="col-status">
                  <span :class="['status', `status-${statusMeta(record.status).key}`]">
                    {{ statusMeta(record.status).label }}
                  </span>
                </td>
                <td class="col-city">{{ record.city || '—' }}</td>
                <td class="col-station" :title="record.station_name || record.station_id || ''">
                  {{ record.station_name || record.station_id || '—' }}
                </td>
                <td class="col-pollutant">{{ record.pollutant || '—' }}</td>
                <td class="col-brief" :title="record.conclusion || ''">
                  {{ record.conclusion ? briefText(record.conclusion, 60) : '—' }}
                </td>
                <td class="col-assets">
                  <template v-if="(record.image_paths || []).length || (record.document_paths || []).length">
                    <span v-if="(record.image_paths || []).length" class="badge">图 {{ record.image_paths.length }}</span>
                    <span v-if="(record.document_paths || []).length" class="badge">文 {{ record.document_paths.length }}</span>
                  </template>
                  <template v-else>—</template>
                </td>
                <td class="col-actions" @click.stop>
                  <button
                    v-if="record.has_report"
                    type="button"
                    class="row-action"
                    title="在线查看报告"
                    @click="viewReport(record)"
                  >查看报告</button>
                  <button
                    v-if="record.has_broadcast"
                    type="button"
                    class="row-action"
                    title="查看广播内容"
                    @click="viewBroadcast(record)"
                  >查看广播内容</button>
                  <button
                    v-if="canOpenSession(record)"
                    type="button"
                    class="row-action primary"
                    title="进入 Agent 会话"
                    @click="enterSession(record)"
                  >进入会话</button>
                  <span v-if="!record.has_report && !record.has_broadcast && !canOpenSession(record)">—</span>
                </td>
              </tr>
            </tbody>
          </table>
          <nav v-if="pagination.totalPages > 1" class="pagination" aria-label="执行结果分页">
            <button type="button" :disabled="loading || pagination.page <= 1" @click="changePage(pagination.page - 1)">上一页</button>
            <span>第 {{ pagination.page }} / {{ pagination.totalPages }} 页，共 {{ pagination.total }} 条</span>
            <button type="button" :disabled="loading || pagination.page >= pagination.totalPages" @click="changePage(pagination.page + 1)">下一页</button>
          </nav>
        </div>
      </div>
    </template>

    <!-- 报告渲染弹窗 -->
    <div v-if="reportVisible" class="report-backdrop" @click.self="closeReport">
      <div class="report-panel">
        <div class="report-header">
          <h4>{{ reportTitle }}</h4>
          <div class="report-header-actions">
            <div v-if="formats.length" class="download-menu">
              <button type="button" class="toolbar-btn" @click="downloadMenuVisible = !downloadMenuVisible">
                ⬇ 下载文档
              </button>
              <div v-if="downloadMenuVisible" class="download-items">
                <a
                  v-for="fmt in formats"
                  :key="fmt.format"
                  class="download-item"
                  :href="fmt.url"
                  :download="fmt.filename"
                  @click="downloadMenuVisible = false"
                >
                  <span>{{ fmt.label }}</span>
                  <small>{{ sizeLabel(fmt.size_bytes) }}</small>
                </a>
              </div>
            </div>
            <button type="button" class="toolbar-btn" @click="closeReport">关闭</button>
          </div>
        </div>
        <iframe
          v-if="reportUrl"
          :src="reportUrl"
          class="report-frame"
          sandbox="allow-scripts"
          referrerpolicy="no-referrer"
          title="报告预览"
        ></iframe>
      </div>
    </div>
    <div v-if="broadcastVisible" class="report-backdrop" @click.self="closeBroadcast">
      <div class="broadcast-panel">
        <div class="report-header">
          <h4>广播内容</h4>
          <button type="button" class="toolbar-btn" @click="closeBroadcast">关闭</button>
        </div>
        <div class="broadcast-content">
          <p class="broadcast-message">{{ broadcastRecord?.broadcast_message || '暂无广播正文' }}</p>
          <div v-if="broadcastImages.length" class="broadcast-images">
            <img v-for="image in broadcastImages" :key="image" :src="image" alt="广播图片" />
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { gatewayUrl } from '@/auth/http.js'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'
import { executionStatusMeta } from './scheduledTaskActions.js'

const props = defineProps({
  task: { type: Object, default: null },
  pageSize: { type: Number, default: 20 }
})

const emit = defineEmits(['restore-execution-session'])

const store = useScheduledTasksStore()

function todayStr() {
  const now = new Date()
  const pad = part => String(part).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const filters = reactive({
  startDate: todayStr(),
  endDate: todayStr(),
  stationId: '',
  pollutant: ''
})
const stations = ref([])
const pollutants = ref([])
const results = ref([])
const loading = ref(false)
const error = ref('')
const pagination = ref({ page: 1, pageSize: props.pageSize, total: 0, totalPages: 0 })
const reportVisible = ref(false)
const reportRecord = ref(null)
const formats = ref([])
const formatsLoading = ref(false)
const downloadMenuVisible = ref(false)
const broadcastVisible = ref(false)
const broadcastRecord = ref(null)
let requestToken = 0

const isWorkflowTask = computed(() => props.task?.execution_mode === 'workflow')
const stationOptions = computed(() => stations.value)
const pollutantOptions = computed(() => pollutants.value)

const statusMeta = status => executionStatusMeta(status)

const canOpenSession = record => (
  !isWorkflowTask.value
  && record?.conversation_available !== false
  && typeof record?.session_id === 'string'
  && record.session_id.trim().length > 0
)

const reportUrl = computed(() => {
  const record = reportRecord.value
  if (!record?.has_report || !record?.preview_ticket) return ''
  return gatewayUrl(
    `/api/scheduled-tasks/results/${encodeURIComponent(record.execution_id)}`
    + `/report/_t/${encodeURIComponent(record.preview_ticket)}/report.html`
  )
})

const reportTitle = computed(() => {
  const record = reportRecord.value
  if (!record) return '报告'
  const taskName = record.task_name || props.task?.name || '分析任务'
  const time = formatRowTime(record)
  return time === '—' ? taskName : `${time} ${taskName}`
})

function briefText(text, max = 80) {
  const value = String(text).replace(/\s+/g, ' ').trim()
  return value.length > max ? `${value.slice(0, max)}…` : value
}

const formatRowTime = (record) => {
  const date = record?.started_at || record?.completed_at
    ? new Date(record.started_at || record.completed_at)
    : null
  if (!date || Number.isNaN(date.getTime())) return '—'
  const pad = part => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function loadFormats(record) {
  formats.value = []
  formatsLoading.value = true
  try {
    const items = await store.fetchTaskReportFormats(record.execution_id)
    formats.value = items.map(item => ({ ...item, url: gatewayUrl(item.url) }))
  } catch (failure) {
    console.error('[ScheduledTaskResultsView] Failed to load report formats:', failure)
    formats.value = []
  } finally {
    formatsLoading.value = false
  }
}

function viewReport(record) {
  if (!record?.has_report) return
  reportRecord.value = record
  reportVisible.value = true
  downloadMenuVisible.value = false
  loadFormats(record)
}

function sizeLabel(bytes) {
  const value = Number(bytes || 0)
  if (!value) return ''
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function closeReport() {
  reportVisible.value = false
  downloadMenuVisible.value = false
}

const broadcastImages = computed(() => (
  (broadcastRecord.value?.broadcast_image_urls || []).map(url => gatewayUrl(url))
))

function viewBroadcast(record) {
  if (!record?.has_broadcast) return
  broadcastRecord.value = record
  broadcastVisible.value = true
}

function closeBroadcast() {
  broadcastVisible.value = false
  broadcastRecord.value = null
}

function enterSession(record) {
  if (!canOpenSession(record)) return
  emit('restore-execution-session', record.session_id)
}

const loadFacets = async () => {
  const taskId = props.task?.task_id || ''
  try {
    const facets = await store.fetchTaskResultFacets(taskId)
    stations.value = facets.stations
    pollutants.value = facets.pollutants
  } catch (failure) {
    console.error('[ScheduledTaskResultsView] Failed to load facets:', failure)
    stations.value = []
    pollutants.value = []
  }
}

const load = async (page = pagination.value.page) => {
  const taskId = props.task?.task_id
  if (!taskId) {
    results.value = []
    pagination.value = { page: 1, pageSize: props.pageSize, total: 0, totalPages: 0 }
    return
  }
  const token = ++requestToken
  loading.value = true
  error.value = ''
  try {
    const result = await store.fetchTaskResults({
      taskId,
      page,
      pageSize: pagination.value.pageSize,
      startDate: filters.startDate,
      endDate: filters.endDate,
      stationId: filters.stationId,
      pollutant: filters.pollutant
    })
    if (token !== requestToken) return
    results.value = result.results
    pagination.value = {
      page: result.page,
      pageSize: result.pageSize,
      total: result.total,
      totalPages: result.totalPages
    }
  } catch (failure) {
    if (token !== requestToken) return
    console.error(`[ScheduledTaskResultsView] Failed to fetch results for task ${taskId}:`, failure)
    error.value = '执行结果加载失败，请重试'
  } finally {
    if (token === requestToken) loading.value = false
  }
}

function applyFilters() {
  load(1)
}

function resetFilters() {
  filters.startDate = todayStr()
  filters.endDate = todayStr()
  filters.stationId = ''
  filters.pollutant = ''
  load(1)
}

function changePage(page) {
  if (page < 1 || page > pagination.value.totalPages || page === pagination.value.page) return
  load(page)
}

function reload() {
  load(pagination.value.page || 1)
}

watch(() => props.task?.task_id, () => {
  filters.startDate = todayStr()
  filters.endDate = todayStr()
  filters.stationId = ''
  filters.pollutant = ''
  pagination.value = { page: 1, pageSize: props.pageSize, total: 0, totalPages: 0 }
  loadFacets()
  load(1)
}, { immediate: true })

defineExpose({ reload })
</script>

<style scoped>
.task-results-view { display: flex; flex-direction: column; gap: 14px; height: 100%; }
.results-toolbar { display: flex; align-items: flex-end; justify-content: space-between; gap: 10px 12px; flex-wrap: wrap; }
.toolbar-field { display: grid; gap: 4px; font-size: 12px; color: var(--text-2); flex: 1 1 130px; min-width: 120px; }
.toolbar-field input, .toolbar-field select { width: 100%; box-sizing: border-box; min-height: 30px; padding: 4px 8px; border: 1px solid var(--border-2); border-radius: 6px; background: var(--bg-container); color: var(--text-1); font-size: 12px; }
.toolbar-btn { flex: 0 0 auto; min-height: 30px; padding: 4px 14px; border: 1px solid var(--border-2); border-radius: 6px; background: var(--bg-container); color: var(--text-1); cursor: pointer; font-size: 12px; }
.toolbar-btn:hover:not(:disabled) { border-color: var(--color-primary); color: var(--color-primary); }
.toolbar-btn.primary { background: var(--color-primary); border-color: var(--color-primary); color: #fff; }
.toolbar-btn:disabled { opacity: .55; cursor: not-allowed; }
.results-body { min-width: 0; }
.record-table-wrap { min-width: 0; border: 1px solid var(--border-2); border-radius: 8px; background: var(--bg-container); overflow-x: auto; }
.record-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.record-table th { padding: 8px 10px; text-align: left; background: var(--bg-muted); color: var(--text-2); font-weight: 600; white-space: nowrap; }
.record-table td { padding: 8px 10px; border-top: 1px solid var(--border-2); color: var(--text-1); vertical-align: middle; }
.record-table tbody tr { cursor: default; }
.record-table tbody tr:hover { background: var(--color-primary-bg); }
.col-time { white-space: nowrap; color: var(--text-1); }
.col-status, .col-city, .col-pollutant { white-space: nowrap; }
.col-station { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-brief { max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); }
.col-assets, .col-actions { white-space: nowrap; }
.col-assets { min-width: 72px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #eef5ff; color: #275a9a; font-size: 11px; }
.badge + .badge { margin-left: 4px; }
.row-action { padding: 4px 10px; border: 1px solid var(--color-primary); border-radius: 6px; background: var(--bg-container); color: var(--color-primary); cursor: pointer; font-size: 12px; }
.row-action:hover { background: var(--color-primary-bg); }
.row-action.primary { background: var(--color-primary); color: #fff; }
.row-action.primary:hover { opacity: .92; }
.row-action + .row-action { margin-left: 6px; }
.status { font-size: 12px; font-weight: 600; }
.status-success { color: #16803c; }
.status-failed, .status-timeout, .status-cancelled { color: var(--color-danger); }
.status-running { color: var(--color-primary); }
.status-pending, .status-unknown { color: var(--text-2); }
.pagination { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 12px; margin-top: 16px; color: var(--text-2); font-size: 12px; }
.pagination button { min-width: 68px; padding: 5px 10px; border: 1px solid var(--border-2); border-radius: 6px; background: var(--bg-container); color: var(--text-1); cursor: pointer; }
.pagination button:disabled { opacity: .45; cursor: not-allowed; }
.report-backdrop { position: fixed; inset: 0; z-index: 1200; display: grid; place-items: center; background: rgba(15, 23, 42, .55); }
.report-panel { display: grid; grid-template-rows: auto minmax(0, 1fr); width: min(1080px, 92vw); height: min(85vh, 900px); border-radius: 10px; background: var(--bg-container); overflow: hidden; }
.report-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; border-bottom: 1px solid var(--border-2); }
.report-header h4 { margin: 0; font-size: 14px; color: var(--text-1); }
.report-header-actions { display: flex; gap: 8px; align-items: center; }
.download-menu { position: relative; }
.download-items { position: absolute; right: 0; top: calc(100% + 6px); z-index: 10; display: grid; min-width: 180px; padding: 6px; border: 1px solid var(--border-2); border-radius: 8px; background: var(--bg-container); box-shadow: 0 8px 24px rgba(15, 23, 42, .12); }
.download-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 10px; border-radius: 6px; color: var(--text-1); text-decoration: none; font-size: 12px; }
.download-item:hover { background: var(--color-primary-bg); color: var(--color-primary); }
.download-item small { color: var(--text-2); }
.report-frame { width: 100%; height: 100%; border: 0; background: #fff; }
.broadcast-panel { width: min(760px, calc(100vw - 32px)); max-height: min(760px, calc(100vh - 48px)); overflow: auto; background: var(--bg-container); border-radius: 8px; box-shadow: 0 18px 60px rgba(15, 23, 42, .24); }
.broadcast-content { padding: 22px; }
.broadcast-message { white-space: pre-wrap; line-height: 1.7; color: var(--text-1); margin: 0 0 18px; }
.broadcast-images { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.broadcast-images img { width: 100%; max-height: 420px; object-fit: contain; border: 1px solid var(--border-2); border-radius: 6px; background: var(--bg-muted); }
.state { padding: 36px 16px; color: var(--text-2); text-align: center; }
.state.error { color: var(--color-danger); }
.state button { margin-top: 8px; padding: 4px 12px; border: 1px solid var(--border-2); border-radius: 6px; background: var(--bg-container); cursor: pointer; }
</style>
