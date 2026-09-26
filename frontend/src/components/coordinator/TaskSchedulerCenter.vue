<template>
  <main class="task-scheduler-center">
    <div class="ambient ambient-one" aria-hidden="true"></div>
    <div class="ambient ambient-two" aria-hidden="true"></div>

    <div class="center-content">
      <header class="scheduler-header">
        <div>
          <p class="scheduler-kicker">苏环智管 · 任务调度</p>
          <h1>任务调度中心</h1>
          <p class="scheduler-description">集中展示待人工确认或处置的故障工单审核与智能事件 AI 研判结果。</p>
        </div>
        <div class="header-actions">
          <span class="live-status"><i aria-hidden="true"></i>调度运行中</span>
          <button class="refresh-btn" type="button" :disabled="loading" @click="loadTasks">
            {{ loading ? '更新中…' : '刷新' }}
          </button>
        </div>
      </header>

      <div v-if="loadError" class="load-note">{{ loadError }}</div>

      <section class="task-list-section" aria-label="待办审核结果">
        <template v-if="todoTasks.length">
          <div class="filter-bar">
            <label class="filter-item">
              <span>任务类型</span>
              <select v-model="filters.taskType">
                <option v-for="(label, value) in TASK_TYPE_LABELS" :key="value" :value="value">{{ label }}</option>
              </select>
            </label>
            <label class="filter-item">
              <span>完成日期</span>
              <input v-model="filters.startDate" type="date" />
              <em>至</em>
              <input v-model="filters.endDate" type="date" />
            </label>
            <label class="filter-item">
              <span>审核建议</span>
              <select v-model="filters.decision">
                <option value="">全部</option>
                <option v-for="(label, key) in DECISION_LABELS" :key="key" :value="key">{{ label }}</option>
              </select>
            </label>
            <button v-if="hasActiveFilters" type="button" class="refresh-btn" @click="resetFilters">重置筛选</button>
          </div>
          <div v-if="filteredTasks.length" class="review-list-wrap">
            <table class="review-list">
              <thead>
                <tr>
                  <th>状态</th>
                  <th>审核标题</th>
                  <th>审核建议</th>
                  <th>数据处置</th>
                  <th class="col-summary">审核结论</th>
                  <th>完成时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="task in pagedTasks" :key="task.review_id">
                  <td><span :class="['review-status', `status-${task.status}`]">{{ formatTodoStatus(task) }}</span></td>
                  <td class="col-title">
                    <strong>{{ task.title }}</strong>
                    <small>{{ task.category }} · {{ task.taskName }}</small>
                  </td>
                  <td><span :class="['decision-badge', decisionClass(task)]">{{ decisionLabel(task) }}</span></td>
                  <td class="col-impact">{{ formatDataImpact(task) }}</td>
                  <td class="col-summary"><span class="review-summary">{{ task.summary }}</span></td>
                  <td class="col-time">{{ formatTodoTime(task.occurredAt) }}</td>
                  <td class="review-row-actions">
                    <button type="button" class="row-action" @click="selectedReviewId = task.review_id">查看详情</button>
                    <button type="button" class="row-action primary" @click="emit('select-review', task)">
                      进入对话工作区
                      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12" /><path d="m12 6 4 4-4 4" /></svg>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="pagination-bar">
              <span class="page-note">共 {{ filteredTasks.length }} 条 · 每页 {{ PAGE_SIZE }} 条 · 第 {{ page }}/{{ totalPages }} 页</span>
              <button type="button" class="row-action" :disabled="page <= 1" @click="page -= 1">上一页</button>
              <button type="button" class="row-action" :disabled="page >= totalPages" @click="page += 1">下一页</button>
            </div>
          </div>
          <div v-else class="empty-state">
            <strong>没有匹配的审核结果</strong>
            <span>请调整筛选条件或点击"重置筛选"后重试。</span>
          </div>
        </template>
        <div v-else class="empty-state">
          <strong>暂无待人工确认或处置的审核结果</strong>
          <span>AI 完成审核或研判后，待人工确认或处置的结果将按所选任务类型显示在这里。</span>
        </div>
      </section>
    </div>
    <div v-if="selectedReviewId" class="review-overlay" @click.self="selectedReviewId = null">
      <section class="review-dialog" role="dialog" aria-modal="true" aria-label="待办事项详情">
        <button class="review-close" type="button" @click="selectedReviewId = null">关闭</button>
        <TaskReviewPanel :review-id="selectedReviewId" compact @updated="loadTasks" />
      </section>
    </div>
  </main>
</template>

<script setup>
import { jiangsuReviewStatus } from '../management/jiangsuJudgmentPresentation.js'
import { computed, onMounted, ref, watch } from 'vue'
import { listTaskReviews } from '@/services/taskReviewsApi.js'
import TaskReviewPanel from '@/components/reviews/TaskReviewPanel.vue'

defineProps({
  runningModes: { type: Array, default: () => [] }
})
const emit = defineEmits(['select-task', 'select-review'])
const loading = ref(false)
const loadError = ref('')
const reviews = ref([])
const selectedReviewId = ref(null)

const todoTasks = computed(() => reviews.value.map(review => ({
  ...review, taskName: review.task_name, occurredAt: review.updated_at
})))

const formatTodoStatus = task => jiangsuReviewStatus(task) || ({ pending_review: '待人工确认', in_disposal: '待处置' }[task.status])
const formatTodoTime = value => {
  if (!value) return '完成时间未知'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : `完成于 ${date.toLocaleString('zh-CN', { hour12: false })}`
}

const DECISION_LABELS = { approve: '建议通过', reject: '建议退回', needs_evidence: '需要补证', needs_action: '需要处置' }
const IMPACT_DECISION_LABELS = { keep: '保留', partial_exclude: '部分剔除', exclude: '剔除', missing_no_delete: '缺失无需剔除', not_applicable: '不适用', needs_evidence: '需要补证' }
const decisionLabel = task => DECISION_LABELS[task.decision] || task.decision || '—'
const decisionClass = task => `decision-${task.decision || 'unknown'}`
const formatDataImpact = task => {
  const impacts = task.data_impact || []
  if (!impacts.length) return '无数据影响'
  return impacts.map(impact => `${impact.pollutant}·${IMPACT_DECISION_LABELS[impact.decision] || impact.decision}`).join('；')
}

// 任务类型筛选：review.category 的取值即 submit_task_review 各 Skill 输出契约里的固定值
const TASK_TYPE_LABELS = { '工单审核': '故障工单审核', '智能事件': '智能事件AI研判' }

// 筛选 + 分页：单次拉取全量（limit=1000），前端过滤后按 PAGE_SIZE 分页渲染
const PAGE_SIZE = 10
const formatLocalDay = d => {
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
const localDay = value => {
  const d = value ? new Date(value) : null
  if (!d || Number.isNaN(d.getTime())) return ''
  return formatLocalDay(d)
}
const todayStr = () => formatLocalDay(new Date())
// 完成日期默认当天，任务类型默认故障工单审核，避免默认翻到其他类型/历史数据
const DEFAULT_TASK_TYPE = '工单审核'
const defaultFilters = () => ({ startDate: todayStr(), endDate: todayStr(), taskType: DEFAULT_TASK_TYPE, decision: '' })
const filters = ref(defaultFilters())
const page = ref(1)
const filteredTasks = computed(() => todoTasks.value.filter(task => {
  if (filters.value.taskType && task.category !== filters.value.taskType) return false
  if (filters.value.decision && task.decision !== filters.value.decision) return false
  if (filters.value.startDate || filters.value.endDate) {
    const day = localDay(task.occurredAt)
    if (!day) return false
    if (filters.value.startDate && day < filters.value.startDate) return false
    if (filters.value.endDate && day > filters.value.endDate) return false
  }
  return true
}))
const pagedTasks = computed(() =>
  filteredTasks.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))
const totalPages = computed(() => Math.max(1, Math.ceil(filteredTasks.value.length / PAGE_SIZE)))
const hasActiveFilters = computed(() => {
  const f = filters.value
  return Boolean(f.decision || f.taskType !== DEFAULT_TASK_TYPE || f.startDate !== todayStr() || f.endDate !== todayStr())
})
const resetFilters = () => { filters.value = defaultFilters() }
watch(filters, () => { page.value = 1 }, { deep: true })
watch(totalPages, total => { if (page.value > total) page.value = total })

const loadTasks = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const reviewPayload = await listTaskReviews()
    const loaded = [...reviewPayload.reviews]
    reviews.value = [...new Map(loaded.map(review => [review.review_id, review])).values()]
  } catch (error) {
    console.error('[TaskSchedulerCenter] Failed to load task reviews:', error)
    loadError.value = '审核结果暂时不可用，请稍后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.review-overlay { position:fixed; inset:0; z-index:1000; background:#122f4266; display:grid; place-items:center; padding:24px; }
.review-dialog { width:min(840px,100%); height:90vh; background:white; border-radius:12px; display:flex; flex-direction:column; overflow:hidden; }
.review-close { align-self:flex-end; margin:8px 16px; padding:6px 16px; cursor:pointer; }
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
.refresh-btn { padding: 8px 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--bg-container); color: var(--lake-600); font: inherit; font-size: 12px; cursor: pointer; transition: all .2s ease; }
.refresh-btn:hover { border-color: color-mix(in srgb, var(--teal-500) 55%, var(--line)); color: var(--teal-600); }
.refresh-btn:disabled { cursor: wait; opacity: .6; }

.load-note { margin-bottom: 14px; padding: 8px 11px; border-radius: 8px; background: #fff4d9; color: #8b6614; font-size: 11px; }

.empty-state { display: grid; min-height: 180px; place-content: center; gap: 5px; border: 1px dashed #bfd1d7; border-radius: 14px; background: rgba(255, 255, 255, .58); color: var(--muted); text-align: center; }
.empty-state strong { color: var(--ink); font-size: 13px; }
.empty-state span { font-size: 11px; }

.review-list-wrap { overflow-x: auto; border: 1px solid rgba(207, 224, 226, .88); border-radius: 14px; background: rgba(255, 255, 255, .86); box-shadow: 0 6px 18px rgba(26, 69, 78, .04); }
.filter-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-bottom: 12px; padding: 11px 14px; border: 1px solid rgba(207, 224, 226, .88); border-radius: 14px; background: rgba(255, 255, 255, .86); }
.filter-item { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: 11px; font-weight: 700; }
.filter-item input[type="date"], .filter-item select { padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg-container); color: var(--ink); font: inherit; font-size: 12px; }
.filter-item em { font-style: normal; color: var(--faint); }
.pagination-bar { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 11px 14px; border-top: 1px solid rgba(217, 230, 234, .6); }
.page-note { color: var(--muted); font-size: 11px; }
.row-action:disabled { opacity: .45; cursor: not-allowed; }
.review-list { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 12px; }
.review-list th { padding: 11px 14px; border-bottom: 1px solid var(--line); background: rgba(237, 243, 245, .72); color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .08em; text-align: left; white-space: nowrap; }
.review-list td { padding: 13px 14px; border-bottom: 1px solid rgba(217, 230, 234, .6); vertical-align: middle; }
.review-list tbody tr:last-child td { border-bottom: none; }
.review-list tbody tr { transition: background .15s ease; }
.review-list tbody tr:hover { background: color-mix(in srgb, var(--teal-500) 6%, transparent); }
.review-status { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; border: 1px solid transparent; font-size: 11px; font-weight: 700; white-space: nowrap; }
.review-status::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.review-status.status-pending_review { border-color: rgba(29, 78, 216, .25); background: rgba(29, 78, 216, .08); color: #1d4ed8; }
.review-status.status-in_disposal { border-color: rgba(222, 146, 32, .3); background: rgba(242, 169, 59, .12); color: #a3660a; }
.mono { font-family: Consolas, 'Courier New', monospace; font-size: 11px; color: var(--lake-700); white-space: nowrap; }
.col-title { min-width: 180px; }
.col-title strong { display: block; color: var(--ink); font-size: 12.5px; line-height: 1.4; }
.col-title small { display: block; margin-top: 3px; color: var(--faint); font-size: 10px; }
.decision-badge { display: inline-block; padding: 3px 10px; border-radius: 999px; border: 1px solid transparent; font-size: 11px; font-weight: 700; white-space: nowrap; }
.decision-badge.decision-approve { border-color: rgba(35, 139, 96, .3); background: rgba(35, 139, 96, .1); color: #238b60; }
.decision-badge.decision-reject { border-color: rgba(200, 60, 60, .3); background: rgba(200, 60, 60, .08); color: #b34040; }
.decision-badge.decision-needs_evidence { border-color: rgba(222, 146, 32, .32); background: rgba(242, 169, 59, .12); color: #a3660a; }
.decision-badge.decision-needs_action { border-color: rgba(17, 96, 134, .3); background: rgba(17, 96, 134, .08); color: #116086; }
.col-impact { max-width: 170px; color: var(--muted); font-size: 11px; line-height: 1.5; }
.review-summary { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--muted); font-size: 11.5px; line-height: 1.55; }
.col-time { color: var(--muted); font-size: 11px; white-space: nowrap; }
.review-row-actions { white-space: nowrap; }
.row-action { display: inline-flex; align-items: center; gap: 5px; padding: 5px 10px; margin-right: 6px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg-container); color: var(--lake-600); font: inherit; font-size: 11px; cursor: pointer; transition: all .2s ease; }
.row-action:hover { border-color: color-mix(in srgb, var(--teal-500) 55%, var(--line)); color: var(--teal-600); }
.row-action.primary { border-color: color-mix(in srgb, var(--teal-600) 45%, var(--line)); color: var(--teal-600); font-weight: 700; }
.row-action.primary svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; transition: transform .2s ease; }
.row-action.primary:hover svg { transform: translateX(3px); }

button:focus-visible { outline: 3px solid rgba(76, 202, 198, .35); outline-offset: 2px; }

@media (max-width: 820px) {
  .center-content { width: min(100% - 32px, 720px); }
  .scheduler-header { align-items: flex-start; flex-direction: column; }
  .header-actions { margin-left: 0; }
}
@media (max-width: 700px) {
  .center-content { width: calc(100% - 28px); padding-top: 18px; }
  .scheduler-description { display: none; }
}
</style>
