<template>
  <main class="task-scheduler-center">
    <div class="ambient ambient-one" aria-hidden="true"></div>
    <div class="ambient ambient-two" aria-hidden="true"></div>

    <div class="center-content">
      <header class="scheduler-header">
        <div>
          <p class="scheduler-kicker">苏小环 · 任务调度</p>
          <h1>任务调度中心</h1>
          <p class="scheduler-description">统一查看待办与定时任务，点击卡片进入对应任务工作区查看执行情况与产出。</p>
        </div>
        <div class="header-actions">
          <span class="live-status"><i aria-hidden="true"></i>调度运行中</span>
          <button class="refresh-btn" type="button" :disabled="loading" @click="loadTasks">
            {{ loading ? '更新中…' : '刷新' }}
          </button>
        </div>
      </header>

      <div v-if="loadError" class="load-note">{{ loadError }}</div>

      <nav class="scheduler-tabs" aria-label="任务类型">
        <button
          v-for="tab in schedulerTabs"
          :key="tab.id"
          type="button"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.name }}
          <span>{{ tab.id === 'todo' ? todoTasks.length : scheduledTasks.length }}</span>
        </button>
      </nav>

      <section class="task-type-filters" aria-label="任务类型筛选">
        <button
          v-for="type in taskTypes"
          :key="type.id"
          type="button"
          :class="{ active: activeTaskType === type.id }"
          @click="activeTaskType = type.id"
        >
          <span class="type-icon" v-html="type.icon"></span>
          {{ type.name }}
          <span class="type-count">{{ getTaskCountByType(type.id) }}</span>
        </button>
      </section>

      <section class="status-grid" aria-label="任务概况">
        <article>
          <span>任务总数</span><strong>{{ tasks.length }}</strong><small>已配置定时任务</small>
        </article>
        <article>
          <span>已启用</span><strong class="active">{{ enabledTaskCount }}</strong><small>调度运行中</small>
        </article>
        <article>
          <span>已暂停</span><strong>{{ pausedTaskCount }}</strong><small>不参与调度</small>
        </article>
        <article>
          <span>运行中智能体</span><strong class="active">{{ runningModes.length }}</strong><small>正在执行任务</small>
        </article>
      </section>

      <section class="task-cards-section" aria-label="任务列表">
        <header class="section-header">
          <div><span>{{ activeTab === 'todo' ? 'TODO' : 'SCHEDULED' }}</span><h2>{{ activeTaskTypeName }}{{ activeTab === 'todo' ? '待办任务' : '定时任务' }}</h2></div>
          <span class="section-count">{{ filteredTasks.length }} TASKS</span>
        </header>
          <div v-if="filteredTasks.length" class="task-cards-grid">
            <article
              v-for="task in filteredTasks"
            :key="task.task_id || task.executionId"
            class="task-card"
            :class="{ paused: activeTab === 'scheduled' && !task.enabled }"
          >
            <span class="task-ambient" aria-hidden="true"></span>
            <span class="task-type-badge">{{ activeTab === 'todo' ? '待处理' : getTaskTypeLabel(task) }}</span>
            <span class="task-card-top">
              <span class="task-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /><path d="M8 2.8h8" /></svg>
              </span>
              <span class="task-title-wrap">
                <strong>{{ activeTab === 'todo' ? task.title : (task.workspace_entry?.title || task.name) }}</strong>
                <small>{{ activeTab === 'todo' ? task.taskName : task.name }}</small>
              </span>
              <span v-if="activeTab === 'scheduled'" :class="['task-state', { paused: !task.enabled }]">
                <i aria-hidden="true"></i>{{ task.enabled ? '已启用' : '已暂停' }}
              </span>
              <span v-else :class="['task-state', `todo-${task.status}`]">
                <i aria-hidden="true"></i>{{ formatTodoStatus(task.status) }}
              </span>
            </span>
            <span class="task-description">{{ activeTab === 'todo' ? task.summary : (task.description || '进入任务工作区查看执行情况与产出文件。') }}</span>
            <span class="task-meta">
              <span>{{ activeTab === 'todo' ? formatTodoTime(task.occurredAt) : formatTaskSchedule(task) }}</span>
              <span v-if="activeTab === 'todo'">{{ task.severityLabel }}</span>
              <span v-else>{{ task.timeout_seconds || 1800 }} 秒超时</span>
            </span>
            <button type="button" class="task-action" @click="emit('select-task', task.sourceTask || task)">
              {{ activeTab === 'todo' ? '查看执行结果' : '进入工作区' }}
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12" /><path d="m12 6 4 4-4 4" /></svg>
            </button>
          </article>
        </div>
        <div v-else class="empty-state">
          <strong>当前类型下暂无任务</strong>
          <span>切换其他任务类型，或在定时任务管理中创建新任务。</span>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'
import { executionToAttentionItem } from './coordinatorWorkspace.js'
import { listJiangsuSmartEventTasks } from '@/services/jiangsuSmartEventsApi.js'

const props = defineProps({
  runningModes: { type: Array, default: () => [] }
})
const emit = defineEmits(['select-task'])
const scheduledTasksStore = useScheduledTasksStore()
const loading = ref(false)
const loadError = ref('')
const executionLoading = ref(false)
const activeTab = ref('todo')
const activeTaskType = ref('all')

const schedulerTabs = Object.freeze([
  { id: 'todo', name: '待办任务' },
  { id: 'scheduled', name: '定时任务' }
])

const TYPE_ICON_SVG = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>'
const taskTypes = [
  { id: 'all', name: '全部任务', icon: '<svg viewBox="0 0 24 24"><path d="M4 6.5h7v7H4z" /><path d="M13 6.5h7v7h-7z" /><path d="M4 15h7v4H4z" /><path d="M13 15h7v4h-7z" /></svg>' },
  { id: 'smart_event', name: '智能事件', icon: '<svg viewBox="0 0 24 24"><path d="M12 4 5 7l7 3 7-3-7-3Z" /><path d="M5 12l7 3 7-3" /><path d="M5 16.5 12 19.5l7-3" /></svg>' },
  { id: 'fault', name: '故障诊断', icon: '<svg viewBox="0 0 24 24"><path d="M9 4.5h6l-.7 5.2 3.4 3-1 2.3-3.7-1.6V19l-1 1.5-1-1.5v-5.6l-3.7 1.6-1-2.3 3.4-3L9 4.5Z" /></svg>' },
  { id: 'work_order', name: '工单审核', icon: '<svg viewBox="0 0 24 24"><path d="M6.5 4.5h11v15h-11z" /><path d="M9.5 9h5" /><path d="M9.5 12.5h5" /><path d="M9.5 16h3" /></svg>' },
  { id: 'other', name: '其他任务', icon: TYPE_ICON_SVG }
]

const resolveTaskType = (task) => {
  const id = String(task?.task_id || '')
  if (task?.trigger_type === 'event' || id.includes('smart_event')) return 'smart_event'
  if (id.includes('work_order') || id.includes('review')) return 'work_order'
  if (id.includes('fault') || id.includes('diagnosis')) return 'fault'
  return 'other'
}

const tasks = computed(() => scheduledTasksStore.tasks)
const completedExecutions = ref([])
const smartEventTasks = ref([])
const toTodoCard = (card, execution = null) => {
  const sourceTask = tasks.value.find(task => task.task_id === (card.scheduled_task_id || execution?.task_id))
  const attention = execution ? executionToAttentionItem(execution) : null
  const status = card.status || execution?.status || '待查看'
  return {
    ...(attention || {}),
    task_id: sourceTask?.task_id || card.scheduled_task_id || execution?.task_id || card.task_id,
    taskName: card.title || card.task_name || execution?.task_name || sourceTask?.name || '待处理任务',
    trigger_type: sourceTask?.trigger_type || 'event',
    title: card.title || attention?.title || execution?.task_name || '待处理任务',
    summary: card.final_response || attention?.summary || '定时任务已完成，请查看执行结果并完成后续处理。',
    status,
    occurredAt: card.updated_at || card.created_at || attention?.occurredAt || execution?.completed_at,
    severity: attention?.severity || (status.includes('失败') ? 'high' : 'medium'),
    severityLabel: status.includes('失败') ? '需处理' : '待复核',
    sourceTask: sourceTask || { task_id: card.scheduled_task_id || execution?.task_id, name: card.title || execution?.task_name || '待处理任务' }
  }
}
const todoTasks = computed(() => {
  const executionById = new Map(completedExecutions.value.map(item => [item.execution_id, item]))
  const cards = smartEventTasks.value.map(card => toTodoCard(card, executionById.get(card.execution_id)))
  const linkedExecutionIds = new Set(smartEventTasks.value.map(card => card.execution_id).filter(Boolean))
  return cards.concat(
    completedExecutions.value
      .filter(execution => !linkedExecutionIds.has(execution.execution_id))
      .map(execution => toTodoCard({}, execution))
  )
})
const scheduledTasks = computed(() => tasks.value.filter(task => task?.trigger_type === 'schedule'))
const visibleTasks = computed(() => activeTab.value === 'todo' ? todoTasks.value : scheduledTasks.value)
const filteredTasks = computed(() => (
  activeTaskType.value === 'all'
    ? visibleTasks.value
    : visibleTasks.value.filter(task => resolveTaskType(task) === activeTaskType.value)
))
const enabledTaskCount = computed(() => tasks.value.filter(task => task.enabled).length)
const pausedTaskCount = computed(() => tasks.value.filter(task => !task.enabled).length)
const activeTaskTypeName = computed(() => (
  activeTaskType.value === 'all' ? '' : `${taskTypes.find(type => type.id === activeTaskType.value)?.name || ''}·`
))

const getTaskCountByType = typeId => (
  typeId === 'all'
    ? visibleTasks.value.length
    : visibleTasks.value.filter(task => resolveTaskType(task) === typeId).length
)
const getTaskTypeLabel = task => taskTypes.find(type => type.id === resolveTaskType(task))?.name || '其他任务'
const formatTodoStatus = status => ({
  success: '待复核', failed: '需处理', timeout: '需处理', cancelled: '已取消',
  '已完成': '待复核', '执行失败': '需处理', '执行中': '处理中', '待执行': '待执行', '待调度': '待调度'
}[status] || '待查看')
const formatTodoTime = value => {
  if (!value) return '完成时间未知'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : `完成于 ${date.toLocaleString('zh-CN', { hour12: false })}`
}

const formatTaskSchedule = (task) => {
  if (task.trigger_type === 'event') return '事件触发'
  if (task.schedule_type === 'daily_8am') return '每天 08:00'
  if (task.schedule_type === 'every_2h') return '每 2 小时'
  if (task.schedule_type === 'every_30min') return '每 30 分钟'
  if (task.schedule_type === 'interval') return `每 ${task.interval_minutes || '--'} 分钟`
  if (task.schedule_type === 'daily_custom') {
    const hour = String(task.hour ?? 0).padStart(2, '0')
    const minute = String(task.minute ?? 0).padStart(2, '0')
    return `每天 ${hour}:${minute}`
  }
  if (task.schedule_type === 'once') return '单次执行'
  const labels = { daily: '每天执行', weekly: '每周执行', monthly: '每月执行', cron: '自定义周期' }
  return labels[task.schedule_type] || '定时执行'
}

const loadTasks = async () => {
  loading.value = true
  executionLoading.value = true
  loadError.value = ''
  try {
    const [, executionResult, eventTaskResult] = await Promise.allSettled([
      scheduledTasksStore.fetchTasks(),
      scheduledTasksStore.fetchRecentExecutions({ pageSize: 50 }),
      listJiangsuSmartEventTasks({ limit: 100 })
    ])
    const executions = executionResult.status === 'fulfilled' ? executionResult.value : { executions: [] }
    const eventTaskPayload = eventTaskResult.status === 'fulfilled' ? eventTaskResult.value : { tasks: [] }
    smartEventTasks.value = Array.isArray(eventTaskPayload?.tasks) ? eventTaskPayload.tasks : []
    completedExecutions.value = executions.executions.filter(execution => (
      execution.trigger_type === 'scheduled'
      && (Boolean(execution.completed_at) || ['success', 'failed', 'timeout', 'cancelled'].includes(execution.status))
    ))
    if (executionResult.status === 'rejected' && eventTaskResult.status === 'rejected') {
      throw executionResult.reason || eventTaskResult.reason
    }
  } catch (error) {
    console.error('[TaskSchedulerCenter] Failed to load scheduled tasks:', error)
    loadError.value = '任务或执行结果暂时不可用，请稍后重试。'
  } finally {
    loading.value = false
    executionLoading.value = false
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.task-scheduler-center {
  --ink: #0a2531;
  --muted: #5b7684;
  --faint: #8aa3ae;
  --line: #d9e6ea;
  --lake-900: #07293b;
  --lake-700: #0d4c6b;
  --lake-600: #116086;
  --teal-600: #0e8a96;
  --teal-500: #14a0ae;
  --cyan-400: #3fc8d4;
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  overflow: auto;
  isolation: isolate;
  color: var(--ink);
  background: #edf3f5;
}
.ambient { position: fixed; width: 420px; height: 420px; border-radius: 50%; pointer-events: none; filter: blur(12px); opacity: .3; }
.ambient-one { top: -220px; right: 5%; background: radial-gradient(circle, rgba(63, 200, 212, .5), transparent 68%); }
.ambient-two { bottom: -270px; left: 12%; background: radial-gradient(circle, rgba(242, 169, 59, .35), transparent 68%); }
.center-content { position: relative; z-index: 1; width: min(1180px, calc(100% - 56px)); margin: 0 auto; padding: 26px 0 44px; }

.scheduler-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 22px; }
.scheduler-kicker { margin: 0 0 7px; color: var(--teal-600); font-size: 12px; font-weight: 700; letter-spacing: .12em; }
.scheduler-header h1 { margin: 0; font-size: clamp(29px, 3vw, 38px); line-height: 1.15; letter-spacing: .04em; color: var(--ink); }
.scheduler-description { margin: 9px 0 0; color: var(--muted); font-size: 13px; }
.header-actions { display: flex; align-items: center; gap: 14px; }
.live-status { display: inline-flex; align-items: center; gap: 7px; padding: 5px 11px; border: 1px solid rgba(47, 181, 122, .3); border-radius: 999px; background: rgba(47, 181, 122, .1); color: #238b60; font-size: 12px; font-weight: 700; white-space: nowrap; }
.live-status i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 14%, transparent); }
.refresh-btn { padding: 8px 14px; border: 1px solid var(--line); border-radius: 10px; background: #fff; color: var(--lake-600); font: inherit; font-size: 12px; cursor: pointer; transition: all .2s ease; }
.refresh-btn:hover { border-color: color-mix(in srgb, var(--teal-500) 55%, var(--line)); color: var(--teal-600); }
.refresh-btn:disabled { cursor: wait; opacity: .6; }

.load-note { margin-bottom: 14px; padding: 8px 11px; border-radius: 8px; background: #fff4d9; color: #8b6614; font-size: 11px; }

.scheduler-tabs { display: flex; gap: 4px; margin-bottom: 14px; padding: 4px; border: 1px solid var(--line); border-radius: 12px; background: rgba(255, 255, 255, .74); width: fit-content; }
.scheduler-tabs button { display: inline-flex; align-items: center; gap: 7px; padding: 8px 14px; border: 0; border-radius: 8px; background: transparent; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; transition: all .2s ease; }
.scheduler-tabs button:hover { color: var(--lake-600); }
.scheduler-tabs button.active { background: var(--lake-900); color: #fff; box-shadow: 0 4px 12px rgba(7, 41, 59, .18); }
.scheduler-tabs button span { min-width: 17px; padding: 1px 5px; border-radius: 999px; background: rgba(10, 42, 58, .08); color: var(--faint); font-size: 10px; font-weight: 700; text-align: center; }
.scheduler-tabs button.active span { background: rgba(255, 255, 255, .16); color: #d7f7f6; }

.task-type-filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.task-type-filters button { display: inline-flex; align-items: center; gap: 7px; padding: 8px 13px; border: 1px solid var(--line); border-radius: 999px; background: #fff; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; transition: all .2s ease; }
.task-type-filters button:hover { border-color: color-mix(in srgb, var(--teal-500) 55%, var(--line)); color: var(--lake-600); }
.task-type-filters button.active { border-color: var(--teal-600); background: color-mix(in srgb, var(--teal-500) 12%, #fff); color: var(--teal-600); font-weight: 700; }
.type-icon { display: inline-flex; width: 15px; height: 15px; align-items: center; }
.type-icon :deep(svg) { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.type-count { padding: 1px 7px; border-radius: 999px; background: rgba(10, 42, 58, .07); color: var(--faint); font-size: 10px; font-weight: 700; }
.task-type-filters button.active .type-count { background: color-mix(in srgb, var(--teal-500) 20%, #fff); color: var(--teal-600); }

.status-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 0 0 22px; }
.status-grid article { display: grid; min-height: 82px; align-content: center; gap: 2px; padding: 0 20px; border: 1px solid rgba(207, 224, 226, .88); border-radius: 14px; background: rgba(255, 255, 255, .86); box-shadow: 0 6px 18px rgba(26, 69, 78, .04); }
.status-grid span, .status-grid small { color: var(--muted); font-size: 10px; }
.status-grid strong { font-size: 26px; }
.status-grid .active { color: var(--teal-600); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header span { color: var(--teal-600); font-size: 9px; font-weight: 800; letter-spacing: .14em; }
.section-header h2 { margin: 1px 0 0; font-size: 18px; letter-spacing: .04em; }
.section-count { color: var(--faint); font-size: 11px; font-weight: 700; letter-spacing: .08em; }

.task-cards-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.task-card {
  --agent-accent: var(--cyan-400);
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 224px;
  flex-direction: column;
  overflow: hidden;
  padding: 22px 22px 18px;
  border: 1px solid rgba(63, 200, 212, .28);
  border-radius: 14px;
  background: linear-gradient(120deg, var(--lake-900) 0%, #0a3a52 52%, var(--lake-700) 100%);
  box-shadow: 0 14px 32px rgba(7, 41, 59, .2);
  color: #fff;
  transition: transform .25s ease, border-color .25s ease, box-shadow .25s ease;
}
.task-card:hover { transform: translateY(-4px); border-color: rgba(63, 200, 212, .62); box-shadow: 0 18px 38px rgba(7, 41, 59, .28); }
.task-card.paused { opacity: .88; }
.task-ambient { position: absolute; width: 260px; height: 260px; top: -145px; right: -100px; border-radius: 50%; background: radial-gradient(circle, rgba(63, 200, 212, .3), transparent 70%); pointer-events: none; }
.task-type-badge { position: absolute; z-index: 2; top: 0; right: 0; padding: 5px 13px 6px 15px; border-radius: 0 14px 0 13px; background: linear-gradient(120deg, #f2a93b, #de9220); color: #fff; font-size: 9px; font-weight: 800; letter-spacing: .12em; }
.task-card-top { position: relative; z-index: 1; display: flex; align-items: flex-start; gap: 11px; padding-right: 76px; }
.task-icon { display: grid; width: 40px; height: 40px; flex: 0 0 auto; place-items: center; border: 1px solid rgba(255, 255, 255, .24); border-radius: 11px; background: rgba(255, 255, 255, .12); color: var(--cyan-400); }
.task-icon svg { width: 21px; height: 21px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.task-title-wrap { display: flex; min-width: 0; flex: 1; flex-direction: column; align-items: flex-start; gap: 5px; }
.task-title-wrap strong { color: #fff; font-size: 16px; line-height: 1.3; }
.task-title-wrap small { overflow: hidden; max-width: 100%; color: rgba(203, 226, 233, .56); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.task-state { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; color: #65ddb4; font-size: 10px; font-weight: 700; white-space: nowrap; }
.task-state.paused { color: #f3bf69; }
.task-state i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 14%, transparent); }
.task-description { position: relative; z-index: 1; display: block; margin-top: 11px; max-width: 90%; color: rgba(220, 239, 244, .78); font-size: 12px; line-height: 1.6; }
.task-meta { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }
.task-meta span { position: relative; z-index: 1; padding: 4px 10px; border: 1px solid rgba(255, 255, 255, .16); border-radius: 999px; background: rgba(255, 255, 255, .08); color: #bfe3ec; font-size: 10px; }
.task-action { position: relative; z-index: 1; display: flex; align-items: center; justify-content: space-between; margin-top: auto; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, .14); color: var(--cyan-400); font-size: 11px; font-weight: 700; cursor: pointer; }
.task-action svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; transition: transform .2s ease; }
.task-card:hover .task-action svg { transform: translateX(3px); }
.empty-state { display: grid; min-height: 180px; place-content: center; gap: 5px; border: 1px dashed #bfd1d7; border-radius: 14px; background: rgba(255, 255, 255, .58); color: var(--muted); text-align: center; }
.empty-state strong { color: var(--ink); font-size: 13px; }
.empty-state span { font-size: 11px; }

button:focus-visible { outline: 3px solid rgba(76, 202, 198, .35); outline-offset: 2px; }

@media (max-width: 820px) {
  .center-content { width: min(100% - 32px, 720px); }
  .scheduler-header { align-items: flex-start; flex-direction: column; }
  .header-actions { margin-left: 0; }
}
@media (max-width: 700px) {
  .center-content { width: calc(100% - 28px); padding-top: 18px; }
  .scheduler-description { display: none; }
  .status-grid { grid-template-columns: repeat(2, 1fr); }
  .task-cards-grid { grid-template-columns: 1fr; }
  .task-state { position: absolute; top: 16px; right: 15px; }
}
</style>
