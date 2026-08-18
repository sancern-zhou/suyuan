<template>
  <CoordinatorHome
    v-if="isCoordinatorLayout && coordinatorView === 'home'"
    :coordinator="coordinator"
    :agents="agents"
    :running-modes="runningModes"
    :selecting-mode="selectingMode"
    :scheduled-tasks="scheduledTasks"
    @select="emit('select', $event)"
    @select-task="emit('select-task', $event)"
    @restore-session="emit('restore-session', $event)"
    @submit="emit('submit', $event)"
    @switch-view="coordinatorView = 'command-center'"
  />
  <CoordinatorCommandCenter
    v-else-if="isCoordinatorLayout"
    :coordinator="coordinator"
    @switch-view="coordinatorView = 'home'"
  />
  <main v-else class="agent-platform">
    <svg class="terrain-lines" viewBox="0 0 1400 1000" preserveAspectRatio="none" aria-hidden="true">
      <path d="M-30 145 C 210 88, 410 218, 690 165 S 1170 95, 1430 175" />
      <path d="M-30 205 C 240 145, 445 275, 730 220 S 1210 150, 1430 235" />
      <path d="M-30 270 C 265 208, 480 334, 770 280 S 1240 210, 1430 300" />
      <path d="M-30 765 C 280 700, 520 830, 810 775 S 1260 705, 1430 795" />
      <path d="M-30 835 C 310 772, 550 900, 850 845 S 1290 775, 1430 865" />
    </svg>
    <div class="platform-glow glow-cyan" aria-hidden="true"></div>
    <div class="platform-glow glow-amber" aria-hidden="true"></div>

    <div class="platform-content">
      <header class="platform-header">
        <div>
          <p class="platform-kicker">生态环境智能体应用门户</p>
          <h1>智能体平台</h1>
          <p class="platform-description">选择专业智能体开展工作，或进入正在运行的定时任务工作区。</p>
        </div>
        <div class="platform-summary" aria-label="平台概览">
          <span class="live-status"><i aria-hidden="true"></i>平台运行中</span>
          <span class="agent-count">已接入 <strong>{{ agents.length }}</strong> 个智能体</span>
        </div>
      </header>

      <div v-if="error" class="platform-error" role="alert">{{ error }}</div>

      <section class="portal-section task-portal" aria-labelledby="tasks-title">
        <header class="section-heading">
          <span class="heading-bar task-bar" aria-hidden="true"></span>
          <div>
            <h2 id="tasks-title">定时任务</h2>
            <p>与左侧工作区保持同步，快速进入任务执行空间</p>
          </div>
          <span class="section-count">{{ scheduledTasks.length }} TASKS</span>
        </header>

        <div v-if="scheduledTasks.length" class="scheduled-task-grid">
          <button
            v-for="task in scheduledTasks"
            :key="task.task_id"
            class="scheduled-task-card"
            type="button"
            @click="emit('select-task', task)"
          >
            <span class="task-ambient" aria-hidden="true"></span>
            <span class="task-badge">定时工作区</span>
            <span class="task-card-top">
              <span class="task-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /><path d="M8 2.8h8" /></svg>
              </span>
              <span class="task-title-wrap">
                <strong>{{ task.workspace_entry?.title || task.name }}</strong>
                <small>{{ task.name }}</small>
              </span>
              <span :class="['task-status', { paused: !task.enabled }]">
                <i aria-hidden="true"></i>{{ task.enabled ? '已启用' : '已暂停' }}
              </span>
            </span>
            <span class="card-description">{{ task.description || '进入任务工作区查看执行情况与产出文件。' }}</span>
            <span class="task-meta">
              <span>{{ formatTaskSchedule(task) }}</span>
              <span>{{ task.steps?.length || 0 }} 个步骤</span>
            </span>
            <span class="card-action task-action">
              进入工作区
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12" /><path d="m12 6 4 4-4 4" /></svg>
            </span>
          </button>
        </div>
        <div v-else class="task-empty-state">
          <span class="task-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>
          </span>
          <div><strong>暂无显示在工作区的定时任务</strong><p>启用任务的工作区入口后，它会自动出现在这里。</p></div>
        </div>
      </section>

      <section class="agent-groups" aria-label="智能体场景">
        <div v-if="isSceneLayout" class="scene-stack">
          <section
            v-for="scene in sceneGroups"
            :key="scene.id"
            class="scene-section"
            :aria-labelledby="`scene-${scene.id}`"
          >
            <header class="scene-header">
              <span class="scene-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path
                    v-for="path in scene.iconPaths"
                    :key="path.d"
                    :class="`tone-${path.tone}`"
                    :d="path.d"
                  />
                </svg>
              </span>
              <div>
                <h2 :id="`scene-${scene.id}`">{{ scene.name }}</h2>
                <p>{{ scene.description }}</p>
              </div>
            </header>

            <div class="agent-grid scene-agent-grid">
              <button
                v-for="agent in scene.agents"
                :key="agent.id"
                class="agent-card"
                type="button"
                :class="{ running: isRunning(agent.id), selecting: selectingMode === agent.id }"
                :style="{ '--agent-accent': agent.accent }"
                :disabled="Boolean(selectingMode)"
                @click="emit('select', agent.id)"
              >
                <span class="agent-card-top">
                  <span class="agent-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <path v-for="path in agent.iconPaths" :key="path" :d="path" />
                    </svg>
                  </span>
                  <span class="agent-title-wrap">
                    <strong>{{ agent.name }}</strong>
                    <span v-if="isRunning(agent.id)" class="running-badge"><i aria-hidden="true"></i>运行中</span>
                  </span>
                </span>
                <span class="card-description">{{ agent.description }}</span>
                <span class="agent-tags" aria-label="能力标签">
                  <span v-for="tag in agent.tags" :key="tag">{{ tag }}</span>
                </span>
                <span class="card-action">
                  {{ selectingMode === agent.id ? '正在进入…' : (isRunning(agent.id) ? '查看任务' : '开始使用') }}
                  <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12" /><path d="m12 6 4 4-4 4" /></svg>
                </span>
              </button>
            </div>
          </section>
        </div>

        <div v-else class="agent-grid">
          <button
            v-for="agent in agents"
            :key="agent.id"
            class="agent-card"
            type="button"
            :class="{ running: isRunning(agent.id), selecting: selectingMode === agent.id }"
            :style="{ '--agent-accent': agent.accent }"
            :disabled="Boolean(selectingMode)"
            @click="emit('select', agent.id)"
          >
            <span class="agent-card-top">
              <span class="agent-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path v-for="path in agent.iconPaths" :key="path" :d="path" /></svg>
              </span>
              <span class="agent-title-wrap">
                <strong>{{ agent.name }}</strong>
                <span v-if="isRunning(agent.id)" class="running-badge"><i aria-hidden="true"></i>运行中</span>
              </span>
            </span>
            <span class="card-description">{{ agent.description }}</span>
            <span class="agent-tags" aria-label="能力标签">
              <span v-for="tag in agent.tags" :key="tag">{{ tag }}</span>
            </span>
            <span class="card-action">
              {{ selectingMode === agent.id ? '正在进入…' : (isRunning(agent.id) ? '查看任务' : '开始使用') }}
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12" /><path d="m12 6 4 4-4 4" /></svg>
            </span>
          </button>
        </div>
      </section>

    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { AGENT_SCENES, selectAgentModes } from '@/config/agentModes.js'
import { projectConfig } from '@/config/projectConfig.js'
import CoordinatorHome from '@/components/coordinator/CoordinatorHome.vue'
import CoordinatorCommandCenter from '@/components/coordinator/CoordinatorCommandCenter.vue'

const props = defineProps({
  agents: { type: Array, default: () => selectAgentModes(projectConfig.agentModeIds, projectConfig.agentModeOverrides) },
  scenes: { type: Array, default: () => AGENT_SCENES },
  layout: { type: String, default: () => projectConfig.agentPlatformLayout },
  coordinator: { type: Object, default: () => projectConfig.coordinator || {} },
  runningModes: { type: Array, default: () => [] },
  selectingMode: { type: String, default: '' },
  error: { type: String, default: '' },
  scheduledTasks: { type: Array, default: () => [] }
})

const emit = defineEmits(['select', 'select-task', 'restore-session', 'submit'])
const coordinatorView = ref('home')

onMounted(() => {
  const params = new URLSearchParams(window.location.search)
  if (params.get('command-center') === '1') coordinatorView.value = 'command-center'
})
const isCoordinatorLayout = computed(() => props.layout === 'coordinator')
const isSceneLayout = computed(() => props.layout === 'scenes')
const sceneGroups = computed(() => props.scenes.map(scene => ({
  ...scene,
  agents: scene.modeIds
    .map(mode => props.agents.find(agent => agent.id === mode))
    .filter(Boolean)
})).filter(scene => scene.agents.length))
const isRunning = mode => props.runningModes.includes(mode)

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
</script>

<style lang="scss" scoped>
.agent-platform {
  --ink: #0a2531;
  --muted: #5b7684;
  --faint: #8aa3ae;
  --surface: #ffffff;
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
  overflow: auto;
  isolation: isolate;
  color: var(--ink);
  background: #edf3f5;
}

.terrain-lines {
  position: absolute;
  z-index: -2;
  inset: 0;
  width: 100%;
  height: 100%;
  min-height: 1000px;
  fill: none;
  stroke: var(--lake-700);
  stroke-width: 1.3;
  opacity: 0.055;
  pointer-events: none;
}

.platform-glow { position: absolute; z-index: -1; border-radius: 50%; pointer-events: none; }
.glow-cyan { width: 640px; height: 420px; top: -170px; right: -130px; background: radial-gradient(circle, rgba(63, 200, 212, 0.16), transparent 70%); }
.glow-amber { width: 520px; height: 380px; top: 380px; left: -260px; background: radial-gradient(circle, rgba(242, 169, 59, 0.08), transparent 70%); }

.platform-content { width: min(1180px, calc(100% - 56px)); margin: 0 auto; padding: 26px 0 44px; }
.platform-header { display: flex; align-items: center; gap: 28px; margin-bottom: 24px; }
.platform-kicker { margin: 0 0 7px; color: var(--teal-600); font-size: 12px; font-weight: 700; letter-spacing: 0.12em; }
.platform-header h1 { margin: 0; font-size: clamp(29px, 3vw, 38px); line-height: 1.15; letter-spacing: 0.04em; color: var(--ink); }
.platform-description { margin: 9px 0 0; color: var(--muted); font-size: 13px; }
.platform-summary { display: flex; align-items: center; gap: 14px; margin-left: auto; }
.live-status, .agent-count { display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; font-size: 12px; }
.live-status { padding: 5px 11px; border: 1px solid rgba(47, 181, 122, 0.3); border-radius: 999px; background: rgba(47, 181, 122, 0.1); color: #238b60; font-weight: 700; }
.live-status i, .running-badge i, .task-status i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 14%, transparent); }
.agent-count { color: var(--muted); }
.agent-count strong { color: var(--lake-600); font-size: 17px; }

.platform-error { margin-bottom: 18px; padding: 10px 14px; border: 1px solid #efb7af; border-radius: 10px; background: #fff6f4; color: #b44738; font-size: 13px; }
.portal-section + .portal-section { margin-top: 30px; }
.task-portal + .agent-groups { margin-top: 30px; }
.section-heading { display: flex; align-items: center; gap: 11px; margin-bottom: 14px; }
.heading-bar { width: 4px; height: 32px; border-radius: 3px; background: linear-gradient(180deg, var(--cyan-400), var(--teal-600)); }
.task-bar { background: linear-gradient(180deg, #f2a93b, #de9220); }
.section-heading h2 { margin: 0; font-size: 18px; letter-spacing: 0.04em; }
.section-heading p { margin: 3px 0 0; color: var(--faint); font-size: 11px; }
.section-count { margin-left: auto; color: var(--faint); font-size: 11px; font-weight: 700; letter-spacing: 0.08em; }

.scene-stack { display: flex; flex-direction: column; gap: 30px; }
.scene-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.scene-icon { display: grid; width: 34px; height: 34px; place-items: center; color: var(--lake-700); }
.scene-icon svg { width: 27px; height: 27px; fill: none; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.7; }
.scene-icon .tone-primary { stroke: var(--lake-700); }
.scene-icon .tone-accent { stroke: var(--teal-500); }
.scene-header h2 { margin: 0; color: var(--ink); font-size: 18px; letter-spacing: 0.04em; }
.scene-header p { margin: 3px 0 0; color: var(--faint); font-size: 11px; }

.agent-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.scheduled-task-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.agent-card, .scheduled-task-card {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 192px;
  flex-direction: column;
  overflow: hidden;
  padding: 15px 16px 13px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(10, 42, 58, 0.06);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;

  &:hover:not(:disabled) { transform: translateY(-4px); border-color: color-mix(in srgb, var(--agent-accent, var(--teal-500)) 60%, var(--line)); box-shadow: 0 10px 25px rgba(10, 42, 58, 0.11); }
  &:focus-visible { outline: 3px solid color-mix(in srgb, var(--agent-accent, var(--teal-500)) 28%, transparent); outline-offset: 2px; }
  &:disabled { cursor: wait; opacity: 0.78; }
}
.agent-card-top, .task-card-top { display: flex; align-items: flex-start; gap: 11px; }
.agent-icon, .task-icon { display: grid; width: 40px; height: 40px; flex: 0 0 auto; place-items: center; border-radius: 11px; background: var(--agent-accent, var(--lake-600)); color: #fff; box-shadow: 0 4px 12px rgba(10, 42, 58, 0.2); }
.agent-icon svg, .task-icon svg { width: 21px; height: 21px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.agent-title-wrap, .task-title-wrap { display: flex; min-width: 0; flex: 1; flex-direction: column; align-items: flex-start; gap: 5px; }
.agent-title-wrap strong, .task-title-wrap strong { color: var(--ink); font-size: 15px; line-height: 1.3; }
.running-badge, .task-status { display: inline-flex; align-items: center; gap: 6px; color: #238b60; font-size: 10px; font-weight: 700; }
.card-description { display: block; margin-top: 11px; color: var(--muted); font-size: 12px; line-height: 1.6; }
.agent-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.agent-tags > span { padding: 2px 7px; border: 1px solid color-mix(in srgb, var(--agent-accent) 22%, transparent); border-radius: 6px; background: color-mix(in srgb, var(--agent-accent) 8%, #fff); color: color-mix(in srgb, var(--agent-accent) 72%, var(--ink)); font-size: 10px; }
.card-action { display: flex; align-items: center; justify-content: space-between; margin-top: auto; padding-top: 12px; color: var(--agent-accent, var(--teal-600)); font-size: 11px; font-weight: 700; }
.card-action svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; transition: transform 0.2s ease; }
.agent-card:hover .card-action svg, .scheduled-task-card:hover .card-action svg { transform: translateX(3px); }

.scheduled-task-card {
  --agent-accent: var(--cyan-400);
  min-height: 224px;
  padding: 22px 22px 18px;
  border-color: rgba(63, 200, 212, 0.28);
  background: linear-gradient(120deg, var(--lake-900) 0%, #0a3a52 52%, var(--lake-700) 100%);
  box-shadow: 0 14px 32px rgba(7, 41, 59, 0.2);
  color: #fff;

  &:hover { border-color: rgba(63, 200, 212, 0.62); box-shadow: 0 18px 38px rgba(7, 41, 59, 0.28); }
  .card-description { position: relative; z-index: 1; max-width: 90%; color: rgba(220, 239, 244, 0.78); font-size: 12px; }
}
.task-ambient { position: absolute; width: 260px; height: 260px; top: -145px; right: -100px; border-radius: 50%; background: radial-gradient(circle, rgba(63, 200, 212, 0.3), transparent 70%); pointer-events: none; }
.task-badge { position: absolute; z-index: 2; top: 0; right: 0; padding: 5px 13px 6px 15px; border-radius: 0 14px 0 13px; background: linear-gradient(120deg, #f2a93b, #de9220); color: #fff; font-size: 9px; font-weight: 800; letter-spacing: 0.12em; }
.task-card-top { position: relative; z-index: 1; padding-right: 64px; }
.task-icon { border: 1px solid rgba(255, 255, 255, 0.24); background: rgba(255, 255, 255, 0.12); box-shadow: none; color: var(--cyan-400); }
.task-title-wrap strong { color: #fff; font-size: 16px; }
.task-title-wrap small { overflow: hidden; max-width: 100%; color: rgba(203, 226, 233, 0.56); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.task-status { margin-left: auto; color: #65ddb4; white-space: nowrap; }
.task-status.paused { color: #f3bf69; }
.task-meta { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }
.task-meta span { position: relative; z-index: 1; padding: 4px 10px; border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 999px; background: rgba(255, 255, 255, 0.08); color: #bfe3ec; font-size: 10px; }
.task-action { position: relative; z-index: 1; border-top: 1px solid rgba(255, 255, 255, 0.14); color: var(--cyan-400); }
.task-empty-state { display: flex; align-items: center; gap: 14px; padding: 24px; border: 1px dashed #bfd1d7; border-radius: 14px; background: rgba(255, 255, 255, 0.58); color: var(--muted); }
.task-empty-state .task-icon { width: 38px; height: 38px; }
.task-empty-state strong { color: var(--ink); font-size: 13px; }
.task-empty-state p { margin: 4px 0 0; font-size: 11px; }

@media (max-width: 1080px) {
  .agent-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 820px) {
  .platform-content { width: min(100% - 32px, 720px); }
  .platform-header { align-items: flex-start; flex-direction: column; }
  .platform-summary { margin-left: 0; }
}

@media (max-width: 620px) {
  .platform-content { width: calc(100% - 24px); padding-top: 20px; }
  .platform-summary { align-items: flex-start; flex-direction: column; gap: 8px; }
  .agent-grid, .scheduled-task-grid { grid-template-columns: 1fr; }
  .section-heading p { display: none; }
  .task-status { position: absolute; top: 16px; right: 15px; }
}
</style>
