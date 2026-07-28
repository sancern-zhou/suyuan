<template>
  <section class="task-workspace">
    <header>
      <div>
        <p class="eyebrow">业务任务</p>
        <h2>{{ task?.name || '任务不可用' }}</h2>
        <p>{{ task?.description }}</p>
      </div>
      <button type="button" @click="$emit('close')">关闭</button>
    </header>
    <div v-if="loading" class="state">正在加载执行记录...</div>
    <div v-else-if="error" class="state">{{ error }}</div>
    <div v-else-if="!executions.length" class="state">暂无执行记录</div>
    <div v-else class="execution-list">
      <button v-for="execution in executions" :key="execution.execution_id" type="button" :disabled="!execution.session_id" @click="$emit('restore-execution-session', execution.session_id)">
        <strong>{{ statusLabel(execution.status) }}</strong>
        <span>{{ formatTime(execution.started_at) }}</span>
        <span>{{ execution.completed_steps || 0 }}/{{ execution.total_steps || 0 }} 步骤</span>
        <small>{{ execution.session_id ? '查看对话' : '未生成会话' }}</small>
      </button>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'

const props = defineProps({ task: { type: Object, default: null } })
defineEmits(['close', 'restore-execution-session'])
const store = useScheduledTasksStore()
const executions = ref([])
const loading = ref(false)
const error = ref('')
const statusLabel = status => ({ success: '成功', failed: '失败', running: '执行中', pending: '等待执行', timeout: '超时' }[status] || '未知')
const formatTime = value => value ? new Date(value).toLocaleString('zh-CN') : '时间未知'
async function load() {
  if (!props.task?.task_id) return
  loading.value = true
  error.value = ''
  try { executions.value = await store.fetchTaskExecutions(props.task.task_id, 50) } catch { error.value = '执行记录加载失败' } finally { loading.value = false }
}
watch(() => props.task?.task_id, load, { immediate: true })
</script>

<style scoped>
.task-workspace { height: 100%; overflow: auto; padding: 28px; background: #f7f9fc; }
header { display:flex; justify-content:space-between; gap:20px; margin-bottom:24px; }
h2 { margin:4px 0; font-size:22px; color:#17223b; } p { margin:0; color:#64748b; } .eyebrow { color:#1976d2; font-size:13px; }
header button { align-self:start; border:1px solid #cbd5e1; background:#fff; border-radius:6px; padding:7px 12px; cursor:pointer; }
.execution-list { display:grid; gap:8px; }.execution-list button { display:grid; grid-template-columns:70px 1fr 100px 80px; align-items:center; gap:12px; border:1px solid #e2e8f0; border-radius:6px; background:#fff; padding:14px; text-align:left; cursor:pointer; }.execution-list button:hover:not(:disabled) { border-color:#90caf9; background:#f0f7ff; }.execution-list button:disabled { opacity:.55; cursor:not-allowed; }.execution-list strong { color:#1976d2; }.execution-list small { color:#64748b; }.state { padding:40px; color:#64748b; text-align:center; }
</style>
