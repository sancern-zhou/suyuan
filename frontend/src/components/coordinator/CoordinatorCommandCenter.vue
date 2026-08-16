<template>
  <main class="command-center">
    <div class="grid-field" aria-hidden="true"></div>
    <div class="top-aura" aria-hidden="true"></div>

    <header class="center-header">
      <div class="center-brand">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 44 44">
            <path d="M9 15.5 22 8l13 7.5v14L22 37 9 29.5v-14Z" />
            <path d="M15 19.5h14M16.5 25h11M19 30h6" />
          </svg>
        </span>
        <div>
          <span>{{ coordinator.role || '智能运维值班助手' }}</span>
          <h1>空气站智能运维中枢</h1>
        </div>
      </div>

      <div class="header-actions">
        <div class="shift-summary" aria-label="当前值守摘要">
          <span><strong>{{ attentionItems.length }}</strong> 项关注</span>
          <span><strong>{{ reviewCount }}</strong> 项待确认</span>
        </div>
        <span class="system-status"><i></i>系统运行正常</span>
        <button class="view-switch" type="button" @click="emit('switch-view')">
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5.5h12M4 10h12M4 14.5h8" /></svg>
          <span>返回{{ assistantName }}首页</span>
        </button>
      </div>
    </header>

    <section class="center-stage">
      <aside class="intel-rail rail-left" aria-label="重点异常">
        <section class="glass-panel attention-panel">
          <header class="panel-heading">
            <div><span>重点异常</span><strong>当前优先事项</strong></div>
            <em>{{ primaryAttention.live ? '实时' : '场景演示' }}</em>
          </header>
          <div class="attention-level"><i></i>{{ severityLabel(primaryAttention.severity) }}</div>
          <h2>{{ displayText(primaryAttention.title) }}</h2>
          <p>{{ displayText(primaryAttention.summary) }}</p>
          <button type="button" @click="analyzePrimaryAttention">让{{ assistantName }}继续研判</button>
        </section>
      </aside>

      <section class="ai-core-column" :aria-label="`${assistantName}智能中枢`">
        <div class="assistant-presence">
          <div class="core-status"><i></i>{{ assistantName }}正在值守</div>
          <div class="orbital-core" aria-hidden="true">
            <span class="orbit orbit-outer"><i></i><i></i></span>
            <span class="orbit orbit-inner"></span>
            <span class="core-energy">
              <img :src="xiaozhiRobotUrl" :alt="`${assistantName}智能值班助手形象`" />
            </span>
          </div>
        </div>

        <div class="conversation-flow">
          <div class="user-context">
            <span>当前值守问题</span>
            <p>今天有哪些站点需要优先关注？</p>
          </div>

          <section class="core-dialogue" aria-live="polite">
            <div class="dialogue-indicator" aria-hidden="true"><span></span><span></span><span></span></div>
            <div>
              <span>{{ assistantName }}研判</span>
              <h2>{{ displayText(primaryAttention.title) }}需优先核查</h2>
              <p>{{ displayText(primaryAttention.diagnosis || '正在结合监测数据、设备状态和近期任务记录形成初步判断。') }}</p>
              <div class="core-actions">
                <button type="button" @click="analyzePrimaryAttention">补充诊断</button>
                <button class="primary" type="button" @click="submitQuery('根据当前研判结果生成核查任务草案，并列出需要人工确认的内容。')">生成核查任务</button>
              </div>
            </div>
          </section>

          <form class="command-dock" @submit.prevent="submitQuery(query)">
            <span class="dock-mark" aria-hidden="true">
              <svg viewBox="0 0 28 28"><path d="M6 9.5 14 5l8 4.5v9L14 23l-8-4.5v-9Z" /><path d="M10 12h8M11 16h6" /></svg>
            </span>
            <div class="dock-input">
              <label for="coordinator-query">继续与{{ assistantName }}对话</label>
              <input id="coordinator-query" v-model="query" :placeholder="coordinator.placeholder || '描述需要查看或处理的运维事项……'" />
            </div>
            <button class="dock-send" type="submit" :disabled="!query.trim() || Boolean(selectingMode)" :aria-label="`发送给${assistantName}`">
              <svg viewBox="0 0 24 24"><path d="m4 12 16-8-5.5 16-3-6.5L4 12Z" /><path d="m11.5 13.5 4-4" /></svg>
            </button>
          </form>

          <div v-if="quickPrompts.length" class="dock-prompts" aria-label="快捷操作">
            <button v-for="item in quickPrompts.slice(0, 3)" :key="item.label" type="button" @click="submitQuery(item.prompt, item.mode)">{{ item.label }}</button>
          </div>
        </div>
      </section>

      <aside class="intel-rail rail-right" aria-label="现场证据与处置建议">
        <section class="glass-panel evidence-panel">
          <header class="panel-heading">
            <div><span>现场证据</span><strong>{{ stationName }}</strong></div>
            <em class="healthy">站房在线</em>
          </header>
          <figure class="station-figure">
            <div class="station-scene" :class="{ 'has-station-image': coordinator.stationImageUrl }">
              <img
                v-if="coordinator.stationImageUrl"
                class="station-camera-image"
                :src="coordinator.stationImageUrl"
                :alt="`${stationName}现场画面`"
              />
              <template v-else>
                <span class="scene-sky"></span>
                <span class="scene-road"></span>
                <span class="scene-building building-one"></span>
                <span class="scene-building building-two"></span>
                <span class="scene-station"><i></i><i></i><i></i></span>
              </template>
              <span v-if="coordinator.stationImageUrl" class="scene-image-overlay" aria-hidden="true"></span>
              <span class="scene-tag">画面正常</span>
            </div>
            <figcaption v-if="coordinator.stationImageUrl">红圈区域为当前重点观察位置</figcaption>
          </figure>
          <div class="diagnosis-summary">
            <span>判断依据</span>
            <p>{{ displayText(primaryAttention.diagnosis || '暂未形成明确结论，建议继续补充关键证据。') }}</p>
          </div>
          <div class="evidence-list">
            <span v-for="evidence in primaryEvidence" :key="evidence"><i>✓</i>{{ displayText(evidence) }}</span>
          </div>
          <div class="confidence-row"><span>当前置信度</span><strong>{{ confidenceLabel(primaryAttention.confidence) }}</strong></div>
        </section>

        <section class="glass-panel dispatch-panel">
          <header class="panel-heading">
            <div><span>处置建议</span><strong>核查任务草案</strong></div>
            <em>等待确认</em>
          </header>
          <div class="dispatch-person">
            <span class="person-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.2" /><path d="M5.5 20c.8-4.2 3-6.2 6.5-6.2s5.7 2 6.5 6.2" /></svg>
            </span>
            <div><strong>建议安排当班运维人员</strong><small>派发前确认人员位置与当前任务</small></div>
          </div>
          <div class="dispatch-actions">
            <button type="button" @click="submitQuery('调整当前核查任务的人员安排，请先向我确认调度范围。')">调整方案</button>
            <button class="confirm" type="button" @click="submitQuery('确认基于当前建议生成核查任务草案，提交前展示完整内容供我审核。')">确认生成</button>
          </div>
        </section>
      </aside>
    </section>
  </main>
</template>

<script setup>
import { computed, ref } from 'vue'
import xiaozhiRobotUrl from '@/assets/coordinator/xiaozhi-robot.png'
import { normalizeAttentionItem, resolveCoordinatorMode } from './coordinatorWorkspace.js'

const props = defineProps({
  coordinator: { type: Object, default: () => ({}) },
  agents: { type: Array, default: () => [] },
  selectingMode: { type: String, default: '' }
})
const emit = defineEmits(['select', 'submit', 'switch-view'])
const query = ref('')

const quickPrompts = computed(() => props.coordinator.quickPrompts || [])
const assistantName = computed(() => props.coordinator.name || '智能助手')
const attentionItems = computed(() => (props.coordinator.demoAttentionItems || [])
  .map(normalizeAttentionItem)
  .filter(Boolean))
const primaryAttention = computed(() => attentionItems.value[0] || normalizeAttentionItem({
  id: 'command-center-empty',
  title: '当前没有需要优先处置的站点',
  summary: `${assistantName.value}正在持续巡查全省站点和运维任务，有新情况时会及时提醒。`,
  severity: 'info',
  status: 'new',
  diagnosis: '当前运行态势平稳。',
  evidence: ['站点连接状态正常', '巡查任务持续运行']
}))
const primaryEvidence = computed(() => (primaryAttention.value.evidence || []).slice(0, 3))
const stationName = computed(() => primaryAttention.value.station || String(primaryAttention.value.title || '').split('·')[0].trim() || '重点关注站点')
const reviewCount = computed(() => attentionItems.value.filter(item => item.status === 'awaiting_review').length)
const displayText = value => String(value || '').replaceAll('小值', assistantName.value)

const submitQuery = (value, explicitMode = '') => {
  const prompt = String(value || '').trim()
  if (!prompt || props.selectingMode) return
  const fallbackMode = props.coordinator.defaultMode || props.agents[0]?.id || 'assistant'
  const mode = explicitMode || resolveCoordinatorMode(prompt, props.coordinator.routes || [], fallbackMode)
  emit('submit', { query: prompt, mode })
  query.value = ''
}
const analyzePrimaryAttention = () => {
  const action = primaryAttention.value.actions?.[0]
  submitQuery(action?.prompt || `继续研判${primaryAttention.value.title}，补充关键证据并形成处置建议。`, action?.mode)
}
const severityLabel = value => ({ critical: '紧急', high: '高优先级', medium: '需要关注', low: '一般', info: '运行信息' }[value] || '运行信息')
const confidenceLabel = value => ({ high: '判断较明确', medium: '初步判断', low: '线索不足' }[value] || '持续分析')
</script>

<style scoped>
.command-center {
  --cyan: #42e8d9;
  --cyan-soft: #8af8ed;
  --ink: #edfdfd;
  --muted: #9ab9c2;
  --panel: rgba(7, 29, 46, .9);
  --line: rgba(82, 192, 204, .22);
  position: relative;
  width: 100%;
  min-width: 0;
  min-height: 100%;
  flex: 1 1 0%;
  overflow: hidden auto;
  color: var(--ink);
  background:
    radial-gradient(circle at 50% 29%, rgba(19, 119, 143, .22), transparent 34%),
    radial-gradient(circle at 8% 58%, rgba(16, 84, 108, .18), transparent 28%),
    linear-gradient(145deg, #050b13 0%, #071827 48%, #050e18 100%);
}
.grid-field { position: absolute; inset: 0; opacity: .16; pointer-events: none; background-image: linear-gradient(rgba(79,200,219,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(79,200,219,.08) 1px, transparent 1px); background-size: 48px 48px; mask-image: linear-gradient(to bottom, transparent, #000 18%, #000 82%, transparent); }
.top-aura { position: absolute; top: -260px; left: 50%; width: 820px; height: 430px; transform: translateX(-50%); border-radius: 50%; opacity: .25; background: #168aaa; filter: blur(110px); pointer-events: none; }
.center-header { position: relative; z-index: 4; display: flex; min-height: 88px; align-items: center; justify-content: space-between; gap: 24px; padding: 16px clamp(22px, 3vw, 52px); border-bottom: 1px solid rgba(72,207,223,.14); background: linear-gradient(180deg, rgba(4,12,21,.94), rgba(4,18,30,.58)); }
.center-brand, .header-actions, .system-status, .view-switch, .shift-summary { display: flex; align-items: center; }
.center-brand { gap: 13px; }
.brand-mark { display: grid; width: 48px; height: 48px; flex: none; place-items: center; border: 1px solid rgba(76,239,234,.3); border-radius: 13px; background: rgba(21,118,145,.18); box-shadow: inset 0 0 18px rgba(42,222,224,.1); }
.brand-mark svg { width: 34px; fill: none; stroke: var(--cyan-soft); stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; }
.center-brand span:not(.brand-mark) { color: #70cbd3; font-size: 11px; font-weight: 700; letter-spacing: .1em; }
.center-brand h1 { margin: 3px 0 0; font-size: clamp(20px, 1.55vw, 27px); letter-spacing: .06em; }
.header-actions { gap: 12px; }
.shift-summary { gap: 15px; padding-right: 4px; color: #7f9fa9; font-size: 12px; }
.shift-summary strong { color: #dffafa; font-size: 15px; }
.system-status { gap: 8px; color: #8bc5c8; font-size: 12px; }
.system-status i, .core-status i { width: 7px; height: 7px; border-radius: 50%; background: #4ae39b; box-shadow: 0 0 0 4px rgba(74,227,155,.08), 0 0 12px rgba(74,227,155,.55); }
.view-switch { gap: 7px; padding: 9px 13px; border: 1px solid rgba(92,218,226,.28); border-radius: 8px; background: rgba(16,78,101,.22); color: #cdf4f5; cursor: pointer; }
.view-switch:hover { border-color: rgba(103,246,240,.55); background: rgba(21,105,127,.36); }
.view-switch svg { width: 16px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-width: 1.7; }

.center-stage { position: relative; z-index: 2; display: grid; width: min(1680px, calc(100% - 52px)); margin: 0 auto; padding: 34px 0 44px; grid-template-columns: minmax(260px, .78fr) minmax(490px, 1.3fr) minmax(300px, .88fr); grid-template-areas: "left core right"; gap: clamp(18px, 1.55vw, 28px); }
.intel-rail { display: grid; align-content: start; gap: 16px; padding-top: 76px; }
.rail-left { grid-area: left; }
.rail-right { grid-area: right; }
.glass-panel { position: relative; overflow: hidden; border: 1px solid var(--line); border-radius: 10px; background: linear-gradient(140deg, rgba(8,36,56,.9), rgba(5,22,37,.82)); box-shadow: inset 0 0 26px rgba(26,134,161,.04), 0 16px 38px rgba(0,0,0,.18); backdrop-filter: blur(14px); }
.glass-panel::before { position: absolute; top: 0; left: 0; width: 34px; height: 2px; background: var(--cyan); box-shadow: 0 0 8px rgba(66,241,225,.52); content: ''; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 18px 18px 0; }
.panel-heading div { display: grid; gap: 4px; }
.panel-heading span { color: #5cd8dc; font-size: 11px; font-weight: 800; letter-spacing: .11em; }
.panel-heading strong { font-size: 15px; }
.panel-heading em { padding: 3px 8px; border: 1px solid rgba(244,184,77,.25); border-radius: 999px; background: rgba(244,162,52,.08); color: #ffd481; font-size: 11px; font-style: normal; white-space: nowrap; }
.panel-heading em.healthy { border-color: rgba(55,227,170,.22); background: rgba(42,210,159,.07); color: #6ee9b9; }

.attention-panel { padding-bottom: 19px; }
.attention-level { display: flex; align-items: center; gap: 7px; margin: 16px 18px 0; color: #ffc07b; font-size: 12px; }
.attention-level i { width: 7px; height: 7px; border-radius: 50%; background: #ff9b4d; box-shadow: 0 0 9px rgba(255,155,77,.8); }
.attention-panel h2 { margin: 9px 18px 7px; font-size: 17px; line-height: 1.45; }
.attention-panel p { margin: 0 18px; color: var(--muted); font-size: 13px; line-height: 1.7; }
.attention-panel > button { margin: 16px 18px 0; padding: 9px 12px; border: 1px solid rgba(78,219,224,.3); border-radius: 6px; background: rgba(33,144,162,.12); color: #8de4e3; cursor: pointer; font-size: 12px; }

.ai-core-column { grid-area: core; min-width: 0; }
.assistant-presence { display: flex; align-items: center; flex-direction: column; }
.core-status { display: flex; align-items: center; gap: 9px; color: #8bdde0; font-size: 12px; letter-spacing: .1em; }
.core-status i { background: var(--cyan); box-shadow: 0 0 10px rgba(66,232,217,.8); }
.orbital-core { position: relative; width: clamp(300px, 24vw, 390px); aspect-ratio: 1; margin-top: -3px; }
.orbit, .core-energy { position: absolute; border-radius: 50%; }
.orbit { border: 1px solid rgba(78,229,230,.26); }
.orbit-outer { inset: 7%; animation: rotate-clockwise 26s linear infinite; box-shadow: inset 0 0 34px rgba(24,168,190,.08), 0 0 22px rgba(27,159,184,.08); }
.orbit-outer::before { position: absolute; inset: -6px; transform: rotate(42deg); border: solid rgba(91,238,238,.42); border-width: 2px 0; border-radius: 50%; content: ''; }
.orbit-inner { inset: 21%; border-color: rgba(112,246,237,.38); animation: pulse-core 3.5s ease-in-out infinite; box-shadow: inset 0 0 30px rgba(47,218,220,.13), 0 0 30px rgba(31,199,211,.14); }
.orbit > i { position: absolute; width: 7px; height: 7px; border-radius: 50%; background: #a9fff7; box-shadow: 0 0 10px #4ce8e1; }
.orbit-outer i:nth-child(1) { top: 13%; left: 21%; }
.orbit-outer i:nth-child(2) { right: 5%; bottom: 34%; }
.core-energy { z-index: 2; inset: 20%; overflow: hidden; border: 2px solid rgba(138,255,247,.62); background: #f5fbfd; box-shadow: 0 0 0 7px rgba(45,202,210,.07), 0 0 36px rgba(57,227,231,.3), inset 0 0 22px rgba(39,166,195,.1); animation: breathe 3s ease-in-out infinite; }
.core-energy::after { position: absolute; inset: 0; border-radius: inherit; background: radial-gradient(circle at 50% 42%, transparent 52%, rgba(30,173,195,.1) 78%, rgba(31,218,218,.2) 100%); pointer-events: none; content: ''; }
.core-energy img { width: 118%; height: 118%; transform: translate(-8%, -4%); object-fit: cover; object-position: center; }

.conversation-flow { position: relative; z-index: 3; width: min(680px, 100%); margin: -28px auto 0; }
.user-context { width: fit-content; max-width: 88%; margin: 0 0 10px auto; padding: 10px 14px; border: 1px solid rgba(91,139,153,.2); border-radius: 12px 12px 3px 12px; background: rgba(29,58,72,.5); }
.user-context span { color: #7396a1; font-size: 11px; }
.user-context p { margin: 3px 0 0; color: #d7e8eb; font-size: 13px; }
.core-dialogue { display: flex; align-items: flex-start; gap: 13px; padding: 17px 18px; border: 1px solid rgba(81,220,225,.25); border-radius: 3px 12px 12px; background: rgba(6,29,46,.92); box-shadow: 0 14px 36px rgba(0,0,0,.24), inset 0 0 26px rgba(38,174,191,.05); backdrop-filter: blur(14px); }
.dialogue-indicator { display: flex; width: 38px; height: 38px; flex: none; align-items: center; justify-content: center; gap: 3px; border-radius: 50%; background: rgba(33,151,169,.18); }
.dialogue-indicator span { width: 2px; border-radius: 2px; background: #63eee4; animation: voice-wave 1s ease-in-out infinite; }
.dialogue-indicator span:nth-child(1) { height: 8px; }
.dialogue-indicator span:nth-child(2) { height: 16px; animation-delay: .15s; }
.dialogue-indicator span:nth-child(3) { height: 10px; animation-delay: .3s; }
.core-dialogue > div:last-child { min-width: 0; }
.core-dialogue > div > span { color: #55dddb; font-size: 11px; font-weight: 800; }
.core-dialogue h2 { margin: 4px 0 6px; color: #f3ffff; font-size: 17px; line-height: 1.45; }
.core-dialogue p { margin: 0; color: #b5cdd3; font-size: 13px; line-height: 1.7; }
.core-actions { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 14px; }
.core-actions button { padding: 9px 13px; border: 1px solid rgba(78,211,218,.27); border-radius: 6px; background: rgba(12,63,82,.6); color: #a6dfe1; cursor: pointer; font-size: 12px; }
.core-actions button.primary { border-color: rgba(76,239,224,.48); background: linear-gradient(135deg, rgba(17,144,157,.66), rgba(9,88,121,.72)); color: #f1ffff; }

.command-dock { display: flex; min-height: 64px; align-items: center; gap: 12px; margin-top: 13px; padding: 8px 9px 8px 13px; border: 1px solid rgba(80,221,225,.27); border-radius: 10px; background: rgba(4,23,38,.9); box-shadow: 0 14px 36px rgba(0,0,0,.24), inset 0 0 26px rgba(38,161,179,.05); }
.dock-mark { display: grid; width: 40px; height: 40px; flex: none; place-items: center; border: 1px solid rgba(79,232,226,.24); border-radius: 9px; background: rgba(26,129,150,.16); }
.dock-mark svg { width: 26px; fill: none; stroke: #7be7e2; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.3; }
.dock-input { display: grid; min-width: 0; flex: 1; gap: 3px; }
.dock-input label { color: #56d2d5; font-size: 11px; font-weight: 800; letter-spacing: .06em; }
.dock-input input { width: 100%; padding: 0; border: 0; outline: 0; background: transparent; color: #efffff; font: inherit; font-size: 13px; }
.dock-input input::placeholder { color: #718e97; }
.dock-send { display: grid; width: 46px; height: 46px; flex: none; place-items: center; border: 1px solid rgba(91,240,230,.42); border-radius: 9px; background: linear-gradient(135deg, #138994, #0b6283); color: #efffff; cursor: pointer; }
.dock-send:disabled { cursor: default; opacity: .35; }
.dock-send svg { width: 21px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.7; }
.dock-prompts { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 9px; padding-left: 4px; }
.dock-prompts button { padding: 7px 10px; border: 1px solid rgba(81,184,198,.17); border-radius: 999px; background: rgba(26,82,99,.16); color: #8eb6be; cursor: pointer; font-size: 11px; }

.evidence-panel { padding-bottom: 17px; }
.station-figure { margin: 14px 18px 0; }
.station-scene { position: relative; height: 150px; overflow: hidden; border: 1px solid rgba(84,206,219,.2); border-radius: 6px; background: linear-gradient(#0c4968 0 47%, #0a3048 47% 100%); }
.station-scene.has-station-image { height: auto; aspect-ratio: 526 / 320; background: #071a2b; }
.station-camera-image { position: absolute; inset: 0; display: block; width: 100%; height: 100%; object-fit: cover; }
.scene-image-overlay { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(4,31,49,.04), transparent 58%, rgba(3,27,43,.16)); box-shadow: inset 0 0 20px rgba(26,171,187,.12); pointer-events: none; }
.scene-sky { position: absolute; inset: 0; background: radial-gradient(circle at 75% 18%, rgba(105,238,237,.3), transparent 20%), linear-gradient(170deg, transparent 52%, rgba(76,181,193,.12) 53%); }
.scene-road { position: absolute; right: -15%; bottom: -42%; width: 84%; height: 80%; transform: rotate(-8deg); border-left: 2px solid rgba(98,240,235,.24); background: linear-gradient(90deg, rgba(12,42,59,.7), rgba(20,84,101,.6)); }
.scene-building { position: absolute; bottom: 31%; background: linear-gradient(135deg, #103d54, #17647a); }
.building-one { left: 0; width: 34%; height: 43%; }
.building-two { right: 9%; width: 28%; height: 56%; }
.scene-station { position: absolute; bottom: 27%; left: 48%; width: 46px; height: 54px; border: 1px solid rgba(114,241,235,.54); background: rgba(5,27,43,.85); }
.scene-station i { position: absolute; top: -24px; left: 21px; width: 2px; height: 24px; background: #7aece7; }
.scene-station i:nth-child(2) { top: -13px; left: 10px; width: 23px; height: 1px; }
.scene-station i:nth-child(3) { top: 12px; left: 11px; width: 22px; height: 22px; border: 1px solid rgba(78,222,220,.42); background: transparent; }
.scene-tag { position: absolute; top: 9px; right: 9px; padding: 4px 7px; border: 1px solid rgba(83,239,217,.3); border-radius: 4px; background: rgba(4,34,48,.74); color: #77e5cc; font-size: 11px; }
.station-figure figcaption { margin-top: 7px; color: #96adb4; font-size: 12px; }
.diagnosis-summary { margin: 15px 18px 10px; }
.diagnosis-summary span { color: #5cd8dc; font-size: 11px; font-weight: 800; letter-spacing: .08em; }
.diagnosis-summary p { margin: 5px 0 0; color: #b5cdd3; font-size: 13px; line-height: 1.65; }
.evidence-list { display: flex; flex-wrap: wrap; gap: 7px; padding: 0 18px; }
.evidence-list span { display: flex; align-items: center; gap: 5px; padding: 5px 8px; border: 1px solid rgba(87,185,198,.16); border-radius: 5px; background: rgba(30,96,113,.12); color: #91b6bf; font-size: 11px; }
.evidence-list i { color: #5be8cf; font-style: normal; }
.confidence-row { display: flex; align-items: center; justify-content: space-between; margin: 15px 18px 0; padding-top: 12px; border-top: 1px solid rgba(86,181,195,.13); color: #7898a2; font-size: 12px; }
.confidence-row strong { color: #ffd17e; font-size: 12px; }

.dispatch-panel { padding-bottom: 17px; }
.dispatch-person { display: flex; align-items: center; gap: 11px; margin: 15px 18px; padding: 11px; border: 1px solid rgba(82,188,200,.14); border-radius: 6px; background: rgba(16,67,86,.24); }
.person-icon { display: grid; width: 38px; height: 38px; flex: none; place-items: center; border-radius: 50%; background: rgba(30,148,162,.2); }
.person-icon svg { width: 24px; fill: none; stroke: #83dedb; stroke-linecap: round; stroke-width: 1.4; }
.dispatch-person div { display: grid; gap: 4px; }
.dispatch-person strong { font-size: 13px; }
.dispatch-person small { color: #829da5; font-size: 11px; }
.dispatch-actions { display: grid; gap: 9px; padding: 0 18px; grid-template-columns: 1fr 1fr; }
.dispatch-actions button { padding: 9px; border: 1px solid rgba(80,183,197,.23); border-radius: 6px; background: rgba(11,55,75,.68); color: #9dc7cd; cursor: pointer; font-size: 12px; }
.dispatch-actions button.confirm { border-color: rgba(66,239,222,.44); background: linear-gradient(135deg, rgba(18,146,153,.6), rgba(8,90,122,.68)); color: #efffff; }

button { font: inherit; }
button:focus-visible, input:focus-visible { outline: 3px solid rgba(88,241,233,.3); outline-offset: 2px; }
@keyframes rotate-clockwise { to { transform: rotate(360deg); } }
@keyframes pulse-core { 50% { transform: scale(1.025); border-color: rgba(131,255,245,.62); } }
@keyframes breathe { 50% { transform: scale(1.045); } }
@keyframes voice-wave { 50% { transform: scaleY(.45); opacity: .55; } }

@media (max-width: 1599px) {
  .center-stage { width: min(1240px, calc(100% - 40px)); grid-template-columns: minmax(0, 1.45fr) minmax(320px, .72fr); grid-template-areas: "core left" "core right"; align-items: start; gap: 17px; }
  .ai-core-column { position: sticky; top: 20px; }
  .intel-rail { padding-top: 0; }
  .orbital-core { width: clamp(310px, 31vw, 400px); }
  .conversation-flow { width: min(720px, 100%); }
}
@media (max-width: 1180px) {
  .center-stage { width: min(820px, calc(100% - 32px)); grid-template-columns: 1fr; grid-template-areas: "core" "left" "right"; }
  .ai-core-column { position: static; }
  .rail-left { margin-top: 8px; }
  .orbital-core { width: min(390px, 58vw); }
  .shift-summary { display: none; }
}
@media (max-width: 760px) {
  .center-header { min-height: 72px; padding: 11px 13px; }
  .center-brand { gap: 9px; }
  .brand-mark { width: 40px; height: 40px; }
  .brand-mark svg { width: 29px; }
  .center-brand span:not(.brand-mark) { font-size: 9px; letter-spacing: .06em; }
  .center-brand h1 { font-size: 17px; letter-spacing: .02em; }
  .system-status { display: none; }
  .view-switch { padding: 8px; }
  .view-switch span { display: none; }
  .view-switch svg { width: 19px; }
  .center-stage { width: calc(100% - 22px); padding: 20px 0 30px; gap: 12px; }
  .orbital-core { width: min(340px, 86vw); }
  .conversation-flow { margin-top: -22px; }
  .core-dialogue { padding: 14px; }
  .dialogue-indicator { width: 34px; height: 34px; }
  .command-dock { min-height: 60px; padding-left: 9px; }
  .dock-mark { display: none; }
  .dock-input label { font-size: 10px; }
  .dock-send { width: 43px; height: 43px; }
  .dock-prompts { overflow-x: auto; flex-wrap: nowrap; padding-bottom: 3px; }
  .dock-prompts button { flex: none; }
  .panel-heading, .station-figure { margin-inline: 0; }
  .panel-heading { padding-inline: 15px; }
  .attention-level, .attention-panel h2, .attention-panel p, .attention-panel > button, .diagnosis-summary, .confidence-row, .dispatch-person { margin-inline: 15px; }
  .evidence-list, .dispatch-actions { padding-inline: 15px; }
  .station-figure { margin-inline: 15px; }
}
@media (max-width: 420px) {
  .center-brand h1 { font-size: 15px; }
  .center-brand span:not(.brand-mark) { display: none; }
  .user-context { max-width: 94%; }
  .core-dialogue { gap: 10px; }
  .core-dialogue h2 { font-size: 15px; }
  .dispatch-actions { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) { .orbit, .core-energy, .dialogue-indicator span { animation: none; } }
</style>
