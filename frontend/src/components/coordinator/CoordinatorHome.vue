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
          <span class="agent-count">已接入 <strong>{{ agents.length }}</strong> 个智能体</span>
          <button class="agent-platform-entry secondary" type="button" @click="emit('switch-view')">
            <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.5" /><circle cx="10" cy="10" r="2" /><path d="M10 1.5v2M18.5 10h-2M10 18.5v-2M1.5 10h2" /></svg>
            智能中枢
          </button>
        </div>
      </header>

      <section class="assistant-conversation" aria-label="助手模式对话窗口">
        <div class="conversation-heading">
          <span class="conversation-avatar" aria-hidden="true">AI</span>
          <div>
            <span class="role">ASSISTANT MODE</span>
            <h2>{{ coordinator.greeting || '今天需要我关注什么？' }}</h2>
            <p>直接描述目标，我会提取意图并切换到合适的专业智能体。</p>
          </div>
        </div>
        <form class="conversation-composer" @submit.prevent="submitQuery">
          <input
            v-model="query"
            type="text"
            aria-label="输入助手任务"
            placeholder="例如：查询今天江苏全省异常站点并说明依据"
          >
          <button type="submit" :disabled="!query.trim()">发送</button>
        </form>
        <div v-if="quickPrompts.length" class="quick-prompts" aria-label="快捷提问">
          <button v-for="prompt in quickPrompts" :key="prompt.label" type="button" @click="submitPrompt(prompt)">
            {{ prompt.label }}
          </button>
        </div>
      </section>

      <section class="agent-groups" aria-label="智能体类型">
        <header class="section-header">
          <div><span>AGENT TYPES</span><h2>按类型选择智能体</h2></div>
        </header>
        <div class="agent-type-groups">
          <section v-for="group in agentGroups" :key="group.id" class="agent-type-group" :aria-label="group.name">
            <header class="agent-type-header">
              <span class="agent-type-mark" :style="{ '--group-accent': group.accent }"></span>
              <div><h3>{{ group.name }}</h3><p>{{ group.description }}</p></div>
              <span class="agent-type-count">{{ group.agents.length }} 个</span>
            </header>
            <div class="agent-grid">
              <button
                v-for="agent in group.agents"
                :key="agent.id"
                class="agent-card"
                type="button"
                :class="{ running: runningModes.includes(agent.id), selecting: selectingMode === agent.id }"
                :style="{ '--agent-accent': agent.accent }"
                :disabled="Boolean(selectingMode)"
                @click="emit('select', agent.id)"
              >
                <span class="agent-card-top">
                  <span class="agent-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><path v-for="path in agent.iconPaths" :key="path" :d="path" /></svg>
                  </span>
                  <span class="agent-title-wrap">
                    <strong>{{ agent.shortName || agent.name }}</strong>
                    <span v-if="runningModes.includes(agent.id)" class="running-badge"><i aria-hidden="true"></i>运行中</span>
                  </span>
                </span>
                <span class="agent-description">{{ agent.description }}</span>
                <span class="agent-tags" aria-label="能力标签">
                  <span v-for="tag in agent.tags" :key="tag">{{ tag }}</span>
                </span>
                <span class="card-action">
                  {{ selectingMode === agent.id ? '正在进入…' : (runningModes.includes(agent.id) ? '查看任务' : '开始使用') }}
                  <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12" /><path d="m12 6 4 4-4 4" /></svg>
                </span>
              </button>
            </div>
          </section>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, ref } from 'vue'
import { AGENT_SCENES } from '@/config/agentModes.js'

const emit = defineEmits(['select', 'select-task', 'restore-session', 'submit', 'switch-view'])
const query = ref('')

const props = defineProps({
  coordinator: { type: Object, default: () => ({}) },
  agents: { type: Array, default: () => [] },
  scenes: { type: Array, default: () => AGENT_SCENES },
  runningModes: { type: Array, default: () => [] },
  selectingMode: { type: String, default: '' },
  scheduledTasks: { type: Array, default: () => [] }
})

const quickPrompts = computed(() => Array.isArray(props.coordinator?.quickPrompts) ? props.coordinator.quickPrompts : [])

const agentGroups = computed(() => {
  const assigned = new Set()
  const groups = props.scenes.map((scene, index) => {
    const group = {
      ...scene,
      accent: scene.accent || ['#2878ff', '#0b9b8a', '#b54738', '#7656e8'][index % 4]
    }
    const groupAgents = group.modeIds
      .map(modeId => props.agents.find(agent => agent.id === modeId))
      .filter(agent => agent && !assigned.has(agent.id))
    groupAgents.forEach(agent => assigned.add(agent.id))
    return { ...group, agents: groupAgents }
  }).filter(group => group.agents.length)
  const remaining = props.agents.filter(agent => !assigned.has(agent.id))
  if (remaining.length) groups.push({
    id: 'other',
    name: '其他能力',
    description: '当前项目提供的其他智能体能力',
    accent: '#687f8a',
    agents: remaining
  })
  return groups
})

const submitQuery = () => {
  const value = query.value.trim()
  if (!value) return
  emit('submit', { query: value })
  query.value = ''
}

const submitPrompt = (prompt) => {
  const value = String(prompt?.prompt || '').trim()
  if (!value) return
  emit('submit', { query: value, mode: prompt?.mode })
}
</script>

<style scoped>
.coordinator-home {
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
  min-width: 0;
  min-height: 100%;
  flex: 1 1 0%;
  overflow: auto;
  isolation: isolate;
  color: var(--ink);
  background: #edf3f5;
}
.ambient { position: fixed; width: 420px; height: 420px; border-radius: 50%; pointer-events: none; filter: blur(12px); opacity: .3; }
.ambient-one { top: -220px; right: 5%; background: radial-gradient(circle, rgba(63, 200, 212, .5), transparent 68%); }
.ambient-two { bottom: -270px; left: 12%; background: radial-gradient(circle, rgba(242, 169, 59, .35), transparent 68%); }
.home-content { position: relative; z-index: 1; width: min(1180px, calc(100% - 56px)); margin: 0 auto; padding: 26px 0 44px; }

.coordinator-header, .identity, .header-actions, .section-header { display: flex; align-items: center; }
.coordinator-header { justify-content: space-between; gap: 24px; margin-bottom: 22px; }
.identity { gap: 14px; }
.header-actions { gap: 14px; }
.avatar { position: relative; display: grid; width: 56px; height: 56px; place-items: center; border-radius: 18px; background: linear-gradient(145deg, #0d5068, #0b8290); box-shadow: 0 9px 24px rgba(13, 80, 104, .2); }
.avatar svg { width: 39px; fill: none; stroke: #e9ffff; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
.avatar i { position: absolute; right: -2px; bottom: 3px; width: 11px; height: 11px; border: 3px solid #f5faf8; border-radius: 50%; background: #26c574; }
.identity h1 { margin: 1px 0 2px; font-size: 25px; letter-spacing: .04em; }
.identity p { margin: 0; color: var(--muted); font-size: 12px; }
.role { color: var(--teal-600); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.agent-count { display: inline-flex; align-items: center; gap: 7px; color: var(--muted); font-size: 12px; white-space: nowrap; }
.agent-count strong { color: var(--lake-600); font-size: 17px; }
.agent-platform-entry { display: flex; align-items: center; gap: 7px; padding: 10px 14px; border: 1px solid #c9dcdf; border-radius: 11px; background: rgba(255,255,255,.72); color: #496572; cursor: pointer; font-size: 13px; }
.agent-platform-entry svg { width: 16px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; }

.assistant-conversation { margin-bottom: 28px; padding: 20px 22px 17px; border: 1px solid rgba(63, 200, 212, .24); border-radius: 16px; background: linear-gradient(120deg, rgba(7, 41, 59, .98), rgba(13, 76, 107, .94)); box-shadow: 0 14px 30px rgba(7, 41, 59, .16); color: var(--bg-container); }
.conversation-heading { display: flex; align-items: center; gap: 12px; }
.conversation-avatar { display: grid; width: 38px; height: 38px; place-items: center; border: 1px solid rgba(126, 239, 232, .38); border-radius: 12px; background: rgba(75, 211, 210, .15); color: #a9f6ef; font-size: 11px; font-weight: 800; }
.conversation-heading .role { color: #70d9d3; }
.conversation-heading h2 { margin: 4px 0 2px; font-size: 18px; letter-spacing: .02em; }
.conversation-heading p { margin: 0; color: rgba(220, 239, 244, .72); font-size: 11px; }
.conversation-composer { display: flex; gap: 9px; margin-top: 17px; }
.conversation-composer input { min-width: 0; flex: 1; padding: 11px 13px; border: 1px solid rgba(173, 235, 234, .23); border-radius: 10px; outline: none; background: rgba(255, 255, 255, .1); color: var(--bg-container); font: inherit; font-size: 12px; }
.conversation-composer input::placeholder { color: rgba(212, 235, 239, .54); }
.conversation-composer input:focus { border-color: rgba(123, 239, 232, .68); box-shadow: 0 0 0 3px rgba(82, 222, 216, .12); }
.conversation-composer button { padding: 0 17px; border: 0; border-radius: 10px; background: #4fd2c7; color: #073441; font: inherit; font-size: 12px; font-weight: 800; cursor: pointer; }
.conversation-composer button:disabled { cursor: not-allowed; opacity: .48; }
.quick-prompts { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 11px; }
.quick-prompts button { padding: 5px 9px; border: 1px solid rgba(173, 235, 234, .18); border-radius: 999px; background: rgba(255, 255, 255, .06); color: rgba(220, 239, 244, .74); font: inherit; font-size: 10px; cursor: pointer; }
.quick-prompts button:hover { border-color: rgba(123, 239, 232, .55); color: #d9fffb; }

.section-header { justify-content: space-between; margin-bottom: 12px; }
.section-header span { color: var(--teal-600); font-size: 9px; font-weight: 800; letter-spacing: .14em; }
.section-header h2 { margin: 1px 0 0; font-size: 18px; letter-spacing: .04em; }

.agent-type-groups { display: grid; gap: 24px; }
.agent-type-group { min-width: 0; }
.agent-type-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; padding: 0 2px; }
.agent-type-mark { width: 4px; height: 28px; flex: 0 0 auto; border-radius: 4px; background: var(--group-accent); box-shadow: 0 4px 10px color-mix(in srgb, var(--group-accent) 28%, transparent); }
.agent-type-header h3 { margin: 0; color: var(--ink); font-size: 15px; letter-spacing: .03em; }
.agent-type-header p { margin: 3px 0 0; color: var(--faint); font-size: 11px; }
.agent-type-count { margin-left: auto; color: var(--faint); font-size: 10px; font-weight: 700; }

.agent-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.agent-card {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 192px;
  flex-direction: column;
  overflow: hidden;
  padding: 15px 16px 13px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--bg-container);
  box-shadow: 0 1px 2px rgba(10, 42, 58, .06);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform .25s ease, border-color .25s ease, box-shadow .25s ease;
}
.agent-card:hover:not(:disabled) { transform: translateY(-4px); border-color: color-mix(in srgb, var(--agent-accent, var(--teal-500)) 60%, var(--line)); box-shadow: 0 10px 25px rgba(10, 42, 58, .11); }
.agent-card:focus-visible { outline: 3px solid color-mix(in srgb, var(--agent-accent, var(--teal-500)) 28%, transparent); outline-offset: 2px; }
.agent-card:disabled { cursor: wait; opacity: .78; }
.agent-card-top { display: flex; align-items: flex-start; gap: 11px; }
.agent-icon { display: grid; width: 40px; height: 40px; flex: 0 0 auto; place-items: center; border-radius: 11px; background: var(--agent-accent, var(--lake-600)); color: var(--bg-container); box-shadow: 0 4px 12px rgba(10, 42, 58, .2); }
.agent-icon svg { width: 21px; height: 21px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.agent-title-wrap { display: flex; min-width: 0; flex: 1; flex-direction: column; align-items: flex-start; gap: 5px; }
.agent-title-wrap strong { color: var(--ink); font-size: 15px; line-height: 1.3; }
.running-badge { display: inline-flex; align-items: center; gap: 6px; color: #238b60; font-size: 10px; font-weight: 700; }
.running-badge i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 14%, transparent); }
.agent-description { display: block; margin-top: 11px; color: var(--muted); font-size: 12px; line-height: 1.6; }
.agent-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.agent-tags > span { padding: 2px 7px; border: 1px solid color-mix(in srgb, var(--agent-accent) 22%, transparent); border-radius: 6px; background: color-mix(in srgb, var(--agent-accent) 8%, var(--bg-container)); color: color-mix(in srgb, var(--agent-accent) 72%, var(--ink)); font-size: 10px; }
.card-action { display: flex; align-items: center; justify-content: space-between; margin-top: auto; padding-top: 12px; color: var(--agent-accent, var(--teal-600)); font-size: 11px; font-weight: 700; }
.card-action svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; transition: transform .2s ease; }
.agent-card:hover .card-action svg { transform: translateX(3px); }

button:focus-visible { outline: 3px solid rgba(76, 202, 198, .35); outline-offset: 2px; }

@media (max-width: 1080px) { .agent-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 820px) {
  .home-content { width: min(100% - 32px, 720px); }
  .coordinator-header { align-items: flex-start; flex-direction: column; }
}
@media (max-width: 700px) {
  .home-content { width: calc(100% - 28px); padding-top: 18px; }
  .identity p { display: none; }
  .header-actions { align-items: stretch; flex-direction: column; }
  .agent-platform-entry { justify-content: center; padding: 7px 9px; font-size: 10px; }
  .conversation-composer { align-items: stretch; flex-direction: column; }
  .conversation-composer button { min-height: 36px; }
  .agent-grid { grid-template-columns: 1fr; }
}
</style>
