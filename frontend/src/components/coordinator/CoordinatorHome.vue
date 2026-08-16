<template>
  <main class="coordinator-home">
    <div class="ambient ambient-one" aria-hidden="true"></div>
    <div class="ambient ambient-two" aria-hidden="true"></div>

    <div class="home-content">
      <header class="coordinator-header">
        <div class="identity">
          <span class="avatar" aria-hidden="true">
            <svg viewBox="0 0 48 48">
              <path d="M12 16.5 24 9l12 7.5v15L24 39l-12-7.5v-15Z" />
              <path d="M18 24h12M20 29h8" />
              <circle cx="19" cy="20" r="1.5" /><circle cx="29" cy="20" r="1.5" />
            </svg>
            <i></i>
          </span>
          <div>
            <span class="role">{{ coordinator.role || '智能统筹助手' }}</span>
            <h1>{{ coordinator.name || '智能助手' }}</h1>
            <p>{{ coordinator.description }}</p>
          </div>
        </div>
        <div class="header-actions">
          <button class="command-center-entry" type="button" @click="emit('switch-view')">
            <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.5" /><circle cx="10" cy="10" r="2" /><path d="M10 1.5v2M18.5 10h-2M10 18.5v-2M1.5 10h2" /></svg>
            智能中枢
          </button>
          <button class="professional-entry" type="button" @click="catalogOpen = !catalogOpen">
            专业工作区
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
          </button>
        </div>
      </header>

      <section class="command-surface" aria-labelledby="coordinator-greeting">
        <div class="command-copy">
          <span class="presence"><i></i>{{ coordinator.name || '智能助手' }}在线</span>
          <h2 id="coordinator-greeting">{{ coordinator.greeting }}</h2>
          <p>可以直接描述问题，也可以让我重新组织当前工作台。</p>
        </div>
        <form class="command-box" @submit.prevent="submitQuery(query)">
          <textarea
            v-model="query"
            rows="2"
            :placeholder="coordinator.placeholder || '输入问题、业务对象或任务……'"
            @keydown.enter.exact.prevent="submitQuery(query)"
          ></textarea>
          <button type="submit" :disabled="!query.trim() || Boolean(selectingMode)" aria-label="发送给统筹助手">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 12 16-8-5.5 16-3-6.5L4 12Z" /><path d="m11.5 13.5 4-4" /></svg>
          </button>
        </form>
        <div v-if="quickPrompts.length" class="quick-prompts" aria-label="快捷指令">
          <button v-for="item in quickPrompts" :key="item.label" type="button" @click="submitQuery(item.prompt, item.mode)">
            {{ item.label }}
          </button>
        </div>
      </section>

      <Transition name="catalog">
        <section v-if="catalogOpen" class="professional-catalog" aria-label="专业工作区">
          <button
            v-for="agent in agents"
            :key="agent.id"
            type="button"
            :disabled="Boolean(selectingMode)"
            @click="emit('select', agent.id)"
          >
            <span class="agent-dot" :style="{ backgroundColor: agent.accent }"></span>
            <span><strong>{{ agent.shortName || agent.name }}</strong><small>{{ agent.description }}</small></span>
            <em v-if="runningModes.includes(agent.id)">进行中</em>
          </button>
        </section>
      </Transition>

      <section class="status-grid" aria-label="今日态势">
        <article>
          <span>重点关注</span><strong>{{ attentionItems.length }}</strong><small>项待持续跟踪</small>
        </article>
        <article>
          <span>高优先级</span><strong class="danger">{{ highPriorityCount }}</strong><small>建议优先研判</small>
        </article>
        <article>
          <span>待人工审核</span><strong>{{ reviewCount }}</strong><small>AI 已形成建议</small>
        </article>
        <article>
          <span>小值处理中</span><strong class="active">{{ analyzingCount }}</strong><small>正在补充证据</small>
        </article>
      </section>

      <section class="workspace-grid">
        <div class="attention-column">
          <header class="section-header">
            <div><span>FOCUS</span><h2>重点关注</h2></div>
            <button type="button" :disabled="loading" @click="loadExecutions">{{ loading ? '更新中…' : '刷新' }}</button>
          </header>
          <div v-if="loadError" class="load-note">实时任务暂不可用，当前展示场景演示数据。</div>
          <article
            v-for="item in attentionItems"
            :key="item.id"
            class="attention-card"
            :class="`severity-${item.severity}`"
          >
            <div class="attention-topline">
              <span class="severity-label">{{ severityLabel(item.severity) }}</span>
              <span>{{ formatTime(item.occurredAt) }}</span>
              <span class="status-label">{{ statusLabel(item.status) }}</span>
              <em v-if="!item.live">场景演示</em>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.summary }}</p>
            <div v-if="item.diagnosis" class="diagnosis">
              <span>小值初判</span>
              <strong>{{ item.diagnosis }}</strong>
              <small v-if="item.confidence">{{ confidenceLabel(item.confidence) }}</small>
            </div>
            <div v-if="item.evidence.length" class="evidence-list">
              <span v-for="evidence in item.evidence" :key="evidence">✓ {{ evidence }}</span>
            </div>
            <div class="card-actions">
              <button v-if="item.sessionId" type="button" class="primary" @click="emit('restore-session', item.sessionId)">查看诊断</button>
              <button
                v-for="action in item.actions"
                :key="action.label"
                type="button"
                :class="{ primary: action.kind === 'open-agent' }"
                @click="runAction(action)"
              >{{ action.label }}</button>
              <button v-if="item.taskId && !item.sessionId" type="button" @click="openTask(item.taskId)">查看任务</button>
            </div>
          </article>
          <div v-if="!attentionItems.length" class="empty-state">
            <strong>当前没有待关注事项</strong>
            <span>小值会持续巡查，发现新情况后显示在这里。</span>
          </div>
        </div>

        <aside class="workspace-column">
          <header class="section-header"><div><span>WORKSPACE</span><h2>动态工作台</h2></div></header>
          <section v-for="block in workspaceBlocks" :key="block.id" class="workspace-block" :class="`block-${block.type}`">
            <h3>{{ block.title }}</h3>
            <template v-if="block.type === 'briefing'">
              <p v-for="item in block.items" :key="item.label || item.text">
                <strong v-if="item.label">{{ item.label }}</strong>{{ item.text }}
              </p>
            </template>
            <template v-else-if="block.type === 'metric-grid'">
              <div class="block-metrics">
                <article v-for="item in block.items" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.detail }}</small></article>
              </div>
            </template>
            <template v-else>
              <ul><li v-for="item in block.items" :key="item.label || item.text"><span>{{ item.label || item.text }}</span><small>{{ item.value || item.detail }}</small></li></ul>
            </template>
          </section>
          <section class="workspace-block capability-note">
            <span class="spark">✦</span>
            <div><h3>工作台可按需生成</h3><p>试试说：“生成今天的运维态势”或“只关注南京的异常站点”。</p></div>
          </section>
        </aside>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'
import {
  executionToAttentionItem,
  normalizeAttentionItem,
  normalizeWorkspaceBlocks,
  resolveCoordinatorMode
} from './coordinatorWorkspace.js'

const props = defineProps({
  coordinator: { type: Object, default: () => ({}) },
  agents: { type: Array, default: () => [] },
  runningModes: { type: Array, default: () => [] },
  selectingMode: { type: String, default: '' },
  scheduledTasks: { type: Array, default: () => [] }
})
const emit = defineEmits(['select', 'select-task', 'restore-session', 'submit', 'switch-view'])
const scheduledTasksStore = useScheduledTasksStore()
const query = ref('')
const catalogOpen = ref(false)
const loading = ref(false)
const loadError = ref('')
const liveItems = ref([])

const quickPrompts = computed(() => props.coordinator.quickPrompts || [])
const demoItems = computed(() => (props.coordinator.demoAttentionItems || [])
  .map(normalizeAttentionItem)
  .filter(Boolean))
const attentionItems = computed(() => {
  const ids = new Set()
  return [...liveItems.value, ...demoItems.value].filter(item => {
    if (!item || ids.has(item.id)) return false
    ids.add(item.id)
    return true
  }).slice(0, 8)
})
const workspaceBlocks = computed(() => normalizeWorkspaceBlocks(props.coordinator.workspaceBlocks || []))
const highPriorityCount = computed(() => attentionItems.value.filter(item => ['critical', 'high'].includes(item.severity)).length)
const reviewCount = computed(() => attentionItems.value.filter(item => item.status === 'awaiting_review').length)
const analyzingCount = computed(() => attentionItems.value.filter(item => item.status === 'analyzing').length)

const submitQuery = (value, explicitMode = '') => {
  const prompt = String(value || '').trim()
  if (!prompt || props.selectingMode) return
  const fallbackMode = props.coordinator.defaultMode || props.agents[0]?.id || 'assistant'
  const mode = explicitMode || resolveCoordinatorMode(prompt, props.coordinator.routes || [], fallbackMode)
  emit('submit', { query: prompt, mode })
  query.value = ''
}
const runAction = action => {
  if (action.kind === 'open-agent' && action.mode) return emit('select', action.mode)
  if (action.kind === 'open-task' && action.taskId) return openTask(action.taskId)
  submitQuery(action.prompt || action.label, action.mode)
}
const openTask = taskId => {
  const task = props.scheduledTasks.find(item => item.task_id === taskId)
  if (task) emit('select-task', task)
}
const loadExecutions = async () => {
  const allowedTaskIds = new Set(props.coordinator.attentionTaskIds || [])
  if (!allowedTaskIds.size) return
  loading.value = true
  loadError.value = ''
  try {
    const executions = await scheduledTasksStore.fetchRecentExecutions(20)
    liveItems.value = executions
      .filter(item => allowedTaskIds.has(item.task_id))
      .map(executionToAttentionItem)
      .map(normalizeAttentionItem)
      .filter(Boolean)
  } catch (error) {
    console.error('[CoordinatorHome] Failed to load attention items:', error)
    loadError.value = error?.message || '加载失败'
  } finally {
    loading.value = false
  }
}
const severityLabel = value => ({ critical: '紧急', high: '高优先级', medium: '需关注', low: '一般', info: '信息' }[value] || '信息')
const statusLabel = value => ({ new: '新发现', analyzing: '小值分析中', awaiting_review: '待人工审核', processing: '处理中', verifying: '等待复查', closed: '已闭环', needs_attention: '需要处理' }[value] || value)
const confidenceLabel = value => ({ high: '高置信度', medium: '中等置信度', low: '低置信度' }[value] || value)
const formatTime = value => {
  if (!value) return '刚刚更新'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
}

onMounted(loadExecutions)
</script>

<style scoped>
.coordinator-home { --ink: #102a38; --muted: #607987; --line: #d9e8ea; --teal: #0d8994; position: relative; width: 100%; min-width: 0; min-height: 100%; flex: 1 1 0%; overflow: auto; background: linear-gradient(155deg, #eff8f7 0%, #f7faf8 43%, #edf4f5 100%); color: var(--ink); }
.ambient { position: fixed; width: 420px; height: 420px; border-radius: 50%; pointer-events: none; filter: blur(12px); opacity: .36; }.ambient-one { top: -220px; right: 5%; background: radial-gradient(circle, #7edbd0, transparent 68%); }.ambient-two { bottom: -270px; left: 12%; background: radial-gradient(circle, #f0c985, transparent 68%); }
.home-content { position: relative; z-index: 1; width: min(1320px, calc(100% - 56px)); margin: 0 auto; padding: 30px 0 52px; }
.coordinator-header, .identity, .header-actions, .command-box, .attention-topline, .section-header, .card-actions { display: flex; align-items: center; }.coordinator-header { justify-content: space-between; gap: 24px; margin-bottom: 24px; }.identity { gap: 14px; }.header-actions { gap: 8px; }.avatar { position: relative; display: grid; width: 56px; height: 56px; place-items: center; border-radius: 18px; background: linear-gradient(145deg, #0d5068, #0b8290); box-shadow: 0 9px 24px rgba(13, 80, 104, .2); }.avatar svg { width: 39px; fill: none; stroke: #e9ffff; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }.avatar i { position: absolute; right: -2px; bottom: 3px; width: 11px; height: 11px; border: 3px solid #f5faf8; border-radius: 50%; background: #26c574; }.identity h1 { margin: 1px 0 2px; font-size: 25px; }.identity p { margin: 0; color: var(--muted); font-size: 12px; }.role { color: var(--teal); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.command-center-entry { display: flex; align-items: center; gap: 7px; padding: 10px 14px; border: 1px solid #b9d8dc; border-radius: 11px; background: linear-gradient(135deg, #0d536b, #0b8691); box-shadow: 0 7px 18px rgba(13,95,107,.14); color: #fff; cursor: pointer; }.command-center-entry svg { width: 16px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-width: 1.5; }
.professional-entry { display: flex; align-items: center; gap: 8px; padding: 10px 15px; border: 1px solid #c9dcdf; border-radius: 11px; background: rgba(255,255,255,.72); color: #496572; cursor: pointer; }.professional-entry svg { width: 16px; fill: none; stroke: currentColor; stroke-width: 1.6; }
.command-surface { padding: 28px 34px 24px; border: 1px solid rgba(130, 184, 185, .46); border-radius: 22px; background: linear-gradient(120deg, rgba(8, 65, 83, .97), rgba(10, 117, 123, .94)); box-shadow: 0 18px 38px rgba(11, 81, 91, .15); color: #fff; }.presence { display: flex; align-items: center; gap: 7px; color: #ace9df; font-size: 11px; font-weight: 700; }.presence i { width: 7px; height: 7px; border-radius: 50%; background: #4cf09b; box-shadow: 0 0 0 4px rgba(76,240,155,.13); }.command-copy h2 { margin: 10px 0 5px; font-size: 24px; }.command-copy p { margin: 0 0 18px; color: #bfe0e1; font-size: 13px; }.command-box { gap: 10px; padding: 7px 7px 7px 18px; border: 1px solid rgba(255,255,255,.28); border-radius: 15px; background: rgba(255,255,255,.96); }.command-box textarea { width: 100%; min-height: 45px; resize: none; border: 0; outline: 0; background: transparent; color: #183743; font: inherit; line-height: 22px; }.command-box button { display: grid; width: 46px; height: 46px; flex: none; place-items: center; border: 0; border-radius: 12px; background: #123f54; color: #fff; cursor: pointer; }.command-box button:disabled { cursor: default; opacity: .38; }.command-box svg { width: 22px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }.quick-prompts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 13px; }.quick-prompts button { padding: 7px 12px; border: 1px solid rgba(255,255,255,.22); border-radius: 999px; background: rgba(255,255,255,.1); color: #e5f7f6; cursor: pointer; font-size: 12px; }.quick-prompts button:hover { background: rgba(255,255,255,.18); }
.professional-catalog { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; margin-top: 12px; padding: 12px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.9); box-shadow: 0 14px 32px rgba(25,65,77,.1); }.professional-catalog button { display: flex; min-width: 0; align-items: center; gap: 9px; padding: 11px; border: 1px solid transparent; border-radius: 10px; background: transparent; text-align: left; cursor: pointer; }.professional-catalog button:hover { border-color: #cde2e4; background: #f4f9f8; }.agent-dot { width: 9px; height: 9px; flex: none; border-radius: 50%; }.professional-catalog button > span:nth-child(2) { display: grid; min-width: 0; }.professional-catalog strong { font-size: 13px; }.professional-catalog small { overflow: hidden; color: #718792; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.professional-catalog em { margin-left: auto; color: var(--teal); font-size: 9px; font-style: normal; }
.status-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0 24px; }.status-grid article { display: grid; min-height: 82px; align-content: center; gap: 2px; padding: 0 20px; border: 1px solid rgba(207, 224, 226, .88); border-radius: 14px; background: rgba(255,255,255,.74); box-shadow: 0 6px 18px rgba(26,69,78,.04); }.status-grid span, .status-grid small { color: var(--muted); font-size: 10px; }.status-grid strong { font-size: 26px; }.status-grid .danger { color: #d45343; }.status-grid .active { color: var(--teal); }
.workspace-grid { display: grid; align-items: start; grid-template-columns: minmax(0, 1.45fr) minmax(320px, .75fr); gap: 22px; }.section-header { justify-content: space-between; margin-bottom: 11px; }.section-header span { color: var(--teal); font-size: 9px; font-weight: 800; letter-spacing: .14em; }.section-header h2 { margin: 1px 0 0; font-size: 18px; }.section-header button { border: 0; background: transparent; color: var(--teal); cursor: pointer; font-size: 12px; }.load-note { margin-bottom: 9px; padding: 8px 11px; border-radius: 8px; background: #fff4d9; color: #8b6614; font-size: 11px; }
.attention-card { position: relative; margin-bottom: 11px; padding: 17px 18px 15px 21px; overflow: hidden; border: 1px solid var(--line); border-radius: 15px; background: rgba(255,255,255,.91); box-shadow: 0 7px 18px rgba(29,70,79,.05); }.attention-card::before { position: absolute; inset: 0 auto 0 0; width: 4px; background: #65aab0; content: ''; }.attention-card.severity-critical::before, .attention-card.severity-high::before { background: #e05a47; }.attention-card.severity-medium::before { background: #d99930; }.attention-topline { gap: 9px; color: #80939d; font-size: 10px; }.severity-label { color: #c94e3e; font-weight: 800; }.status-label { margin-left: auto; padding: 3px 7px; border-radius: 999px; background: #e9f6f3; color: #148378; }.attention-topline em { padding: 3px 7px; border-radius: 999px; background: #eef1f4; color: #70808a; font-style: normal; }.attention-card h3 { margin: 10px 0 4px; font-size: 16px; }.attention-card > p { margin: 0; color: #5c7480; font-size: 12px; line-height: 1.7; }.diagnosis { display: flex; align-items: center; gap: 9px; margin-top: 11px; padding: 10px 12px; border-radius: 9px; background: #f1f8f7; }.diagnosis span { color: var(--teal); font-size: 10px; font-weight: 800; }.diagnosis strong { font-size: 12px; }.diagnosis small { margin-left: auto; color: #7a8c94; font-size: 9px; }.evidence-list { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 10px; color: #52727a; font-size: 10px; }.card-actions { flex-wrap: wrap; gap: 7px; margin-top: 13px; }.card-actions button { padding: 7px 11px; border: 1px solid #c9dcdf; border-radius: 8px; background: #fff; color: #48636e; cursor: pointer; font-size: 11px; }.card-actions button.primary { border-color: #177d86; background: #177d86; color: #fff; }.empty-state { display: grid; min-height: 180px; place-content: center; gap: 5px; border: 1px dashed #c9dcdf; border-radius: 15px; color: #78909a; text-align: center; }.empty-state strong { color: #45626e; }
.workspace-block { margin-bottom: 11px; padding: 16px; border: 1px solid var(--line); border-radius: 14px; background: rgba(255,255,255,.82); }.workspace-block h3 { margin: 0 0 10px; font-size: 14px; }.block-briefing p { margin: 0; padding: 8px 0; border-bottom: 1px solid #edf1f1; color: #5e7680; font-size: 11px; line-height: 1.6; }.block-briefing p:last-child { border-bottom: 0; }.block-briefing strong { display: block; color: #294956; font-size: 11px; }.block-metrics { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }.block-metrics article { display: grid; gap: 2px; padding: 10px; border-radius: 9px; background: #f2f7f6; }.block-metrics span, .block-metrics small { color: #778d96; font-size: 9px; }.block-metrics strong { font-size: 18px; }.workspace-block ul { margin: 0; padding: 0; list-style: none; }.workspace-block li { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; border-bottom: 1px solid #edf1f1; color: #48636e; font-size: 11px; }.workspace-block li:last-child { border-bottom: 0; }.workspace-block li small { color: #82949c; }.capability-note { display: flex; align-items: center; gap: 12px; background: linear-gradient(135deg, #edf8f5, #fff8e9); }.capability-note .spark { display: grid; width: 36px; height: 36px; flex: none; place-items: center; border-radius: 11px; background: #0e7f86; color: #fff; }.capability-note h3 { margin-bottom: 3px; }.capability-note p { margin: 0; color: #6d828a; font-size: 10px; line-height: 1.5; }
.catalog-enter-active,.catalog-leave-active { transition: .18s ease; }.catalog-enter-from,.catalog-leave-to { transform: translateY(-6px); opacity: 0; }
button:focus-visible, textarea:focus-visible { outline: 3px solid rgba(76, 202, 198, .35); outline-offset: 2px; }
@media (max-width: 980px) { .professional-catalog { grid-template-columns: repeat(2, 1fr); }.workspace-grid { grid-template-columns: 1fr; } }
@media (max-width: 700px) { .home-content { width: calc(100% - 28px); padding-top: 18px; }.identity p { display: none; }.header-actions { align-items: stretch; flex-direction: column; }.command-center-entry, .professional-entry { justify-content: center; padding: 7px 9px; font-size: 10px; }.command-surface { padding: 22px 18px 18px; }.status-grid { grid-template-columns: repeat(2, 1fr); }.professional-catalog { grid-template-columns: 1fr; } }
</style>
