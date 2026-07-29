<template>
  <section class="task-files">
    <header class="task-files-header">
      <div>
        <h3>文件产出</h3>
        <p>{{ task?.name || '定时任务' }}的执行结果</p>
      </div>
      <button type="button" class="icon-button" :disabled="loading" title="刷新文件产出" @click="load">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0 2 5.2M20 4v7h-7" /></svg>
      </button>
    </header>

    <p v-if="loading" class="state">正在加载文件产出...</p>
    <div v-else-if="error" class="state state-error">
      <p>{{ error }}</p>
      <button type="button" @click="load">重试</button>
    </div>
    <p v-else-if="!groups.length" class="state">暂无可下载的任务产出</p>

    <div v-else class="file-groups">
      <section v-for="group in groups" :key="group.executionId" class="file-group">
        <div class="group-header">
          <div>
            <span :class="['execution-status', `status-${group.status || 'unknown'}`]">
              {{ executionStatusLabel(group.status) }}
            </span>
            <time>{{ formatExecutionTime(group.startedAt) }}</time>
          </div>
          <button
            v-if="group.sessionId"
            type="button"
            class="session-button"
            title="查看本次执行会话"
            @click="$emit('restore-session', group.sessionId)"
          >
            查看会话
          </button>
        </div>

        <button
          v-for="file in group.files"
          :key="file.id"
          type="button"
          class="file-row"
          :disabled="downloadingId === file.id"
          @click="download(file)"
        >
          <span class="file-icon" aria-hidden="true">{{ file.format.slice(0, 3) }}</span>
          <span class="file-details">
            <strong>{{ file.label }}</strong>
            <small>{{ [file.format, formatTaskOutputSize(file.sizeBytes)].filter(Boolean).join(' · ') }}</small>
          </span>
          <span class="download-label">{{ downloadingId === file.id ? '下载中' : '下载' }}</span>
        </button>
      </section>
    </div>

    <p v-if="downloadError" class="state state-error">{{ downloadError }}</p>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'
import {
  buildTaskOutputGroups,
  executionStatusLabel,
  formatTaskOutputSize
} from './taskOutputFiles.js'

const props = defineProps({ task: { type: Object, default: null } })
defineEmits(['restore-session'])

const store = useScheduledTasksStore()
const groups = ref([])
const loading = ref(false)
const error = ref('')
const downloadError = ref('')
const downloadingId = ref('')

const formatExecutionTime = (value) => value
  ? new Date(value).toLocaleString('zh-CN', { hour12: false })
  : '执行批次'

async function load() {
  if (!props.task?.task_id) {
    groups.value = []
    return
  }

  loading.value = true
  error.value = ''
  downloadError.value = ''
  try {
    const executions = await store.fetchTaskExecutions(props.task.task_id, 50)
    const resourceEntries = await Promise.all(
      executions
        .filter((execution) => execution.session_id)
        .map(async (execution) => {
          const response = await authFetch(`/api/sessions/${encodeURIComponent(execution.session_id)}/resources`)
          if (!response.ok) throw new Error(`执行会话资源读取失败（HTTP ${response.status}）`)
          const payload = await response.json()
          return [execution.session_id, Array.isArray(payload.resources) ? payload.resources : []]
        })
    )
    groups.value = buildTaskOutputGroups(executions, Object.fromEntries(resourceEntries))
  } catch (loadError) {
    console.error('Failed to load scheduled task outputs:', loadError)
    error.value = loadError.message || '文件产出加载失败'
    groups.value = []
  } finally {
    loading.value = false
  }
}

async function download(file) {
  downloadingId.value = file.id
  downloadError.value = ''
  try {
    const response = await authFetch(file.url)
    if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`)
    const blobUrl = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = file.label
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(blobUrl)
  } catch (downloadFailure) {
    downloadError.value = downloadFailure.message || '文件下载失败'
  } finally {
    downloadingId.value = ''
  }
}

watch(() => props.task?.task_id, load, { immediate: true })
</script>

<style scoped>
.task-files { height: 100%; padding: 16px; overflow: auto; background: #fff; box-sizing: border-box; }
.task-files-header, .group-header, .file-row { display: flex; align-items: center; }
.task-files-header { justify-content: space-between; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid #edf1f7; }
h3 { margin: 0; color: #17223b; font-size: 16px; }
.task-files-header p { margin: 4px 0 0; color: #64748b; font-size: 12px; }
.icon-button { display: grid; width: 32px; height: 32px; padding: 0; place-items: center; border: 1px solid #d9e1ec; border-radius: 5px; background: #fff; color: #526173; cursor: pointer; }
.icon-button:disabled { cursor: wait; opacity: .6; }
.icon-button svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.state { margin: 28px 4px; color: #64748b; font-size: 13px; text-align: center; }
.state-error { color: #b42318; }
.state-error p { margin: 0 0 10px; }
.state-error button, .session-button { border: 0; background: transparent; color: #1976d2; cursor: pointer; font-size: 12px; }
.file-groups { display: grid; gap: 18px; padding-top: 16px; }
.file-group { display: grid; gap: 6px; }
.group-header { justify-content: space-between; gap: 8px; min-height: 24px; }
.group-header > div { display: flex; min-width: 0; align-items: center; gap: 8px; }
time { overflow: hidden; color: #64748b; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.execution-status { flex: 0 0 auto; padding: 3px 6px; border-radius: 4px; background: #eef2f6; color: #526173; font-size: 11px; }
.status-success { background: #e9f7ef; color: #16794c; }.status-running { background: #e6f3ff; color: #1976d2; }.status-failed, .status-timeout { background: #fff0ef; color: #b42318; }.status-pending { background: #fff8df; color: #9a6700; }
.file-row { width: 100%; min-height: 54px; gap: 10px; padding: 8px; border: 1px solid #e2e8f0; border-radius: 5px; background: #fff; color: #17223b; cursor: pointer; text-align: left; }
.file-row:hover:not(:disabled) { border-color: #b7d6f4; background: #f7fbff; }.file-row:disabled { cursor: wait; opacity: .65; }
.file-icon { display: grid; width: 30px; height: 30px; flex: 0 0 30px; place-items: center; overflow: hidden; border-radius: 4px; background: #e8f1fb; color: #1b66aa; font-size: 10px; font-weight: 700; text-transform: uppercase; }
.file-details { display: grid; min-width: 0; gap: 3px; }.file-details strong { overflow: hidden; font-size: 13px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }.file-details small { color: #7a8798; font-size: 11px; }
.download-label { margin-left: auto; color: #1976d2; font-size: 12px; }
</style>
