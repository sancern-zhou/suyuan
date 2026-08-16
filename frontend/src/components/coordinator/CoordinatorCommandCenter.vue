<template>
  <main class="command-center">
    <div class="grid-field" aria-hidden="true"></div>
    <div class="top-aura" aria-hidden="true"></div>
    <div class="scan-line" aria-hidden="true"></div>

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
        <span class="system-status"><i></i>系统运行正常</span>
        <button class="view-switch" type="button" @click="emit('switch-view')">
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5.5h12M4 10h12M4 14.5h8" /></svg>
          返回小值首页
        </button>
      </div>
    </header>

    <section class="center-stage">
      <aside class="intel-rail rail-left" aria-label="实时运维信息">
        <section class="glass-panel attention-panel">
          <header class="panel-heading">
            <div><span>实时关注</span><strong>需要优先处理的事项</strong></div>
            <em>{{ primaryAttention.live ? '实时' : '场景演示' }}</em>
          </header>
          <div class="attention-level"><i></i>{{ severityLabel(primaryAttention.severity) }}</div>
          <h2>{{ primaryAttention.title }}</h2>
          <p>{{ primaryAttention.summary }}</p>
          <button type="button" @click="analyzePrimaryAttention">让小值继续研判</button>
        </section>

        <section class="glass-panel trend-panel">
          <header class="panel-heading">
            <div><span>设备状态</span><strong>近 24 小时运行趋势</strong></div>
            <em class="healthy">总体平稳</em>
          </header>
          <svg class="trend-chart" viewBox="0 0 420 150" preserveAspectRatio="none" aria-label="设备运行趋势示意图">
            <defs>
              <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#28e5d1" stop-opacity=".42" />
                <stop offset="1" stop-color="#28e5d1" stop-opacity="0" />
              </linearGradient>
            </defs>
            <g class="chart-grid"><path d="M0 28h420M0 68h420M0 108h420" /><path d="M70 0v140M175 0v140M280 0v140M385 0v140" /></g>
            <path class="trend-area" d="M0 118 C35 112 51 93 81 98 S135 81 170 85 S223 55 257 68 S312 48 340 53 S386 30 420 38 L420 140H0Z" />
            <path class="trend-line" d="M0 118 C35 112 51 93 81 98 S135 81 170 85 S223 55 257 68 S312 48 340 53 S386 30 420 38" />
            <g class="chart-points"><circle cx="81" cy="98" r="4" /><circle cx="257" cy="68" r="4" /><circle cx="420" cy="38" r="4" /></g>
          </svg>
          <div class="trend-legend"><span><i></i>在线设备运行率</span><strong>98.7%</strong></div>
        </section>

        <section class="glass-panel overview-panel">
          <header class="panel-heading">
            <div><span>环境态势</span><strong>今日巡查摘要</strong></div>
          </header>
          <div class="overview-items">
            <div><span>重点关注</span><strong>{{ attentionItems.length }}</strong><small>项</small></div>
            <div><span>待人工确认</span><strong>{{ reviewCount }}</strong><small>项</small></div>
            <div><span>正在研判</span><strong>{{ analyzingCount }}</strong><small>项</small></div>
          </div>
        </section>
      </aside>

      <section class="ai-core-column" aria-label="小值智能中枢">
        <div class="core-status"><i></i>{{ coordinator.name || '小值' }}正在值守</div>
        <div class="orbital-core" aria-hidden="true">
          <span class="orbit orbit-outer"><i></i><i></i><i></i></span>
          <span class="orbit orbit-middle"><i></i><i></i></span>
          <span class="orbit orbit-inner"></span>
          <span class="core-energy"></span>
          <span class="core-copy"><small>AI OPERATIONS CORE</small><strong>{{ coordinator.name || '小值' }}</strong><em>感知 · 研判 · 调度</em></span>
        </div>

        <section class="core-dialogue">
          <div class="dialogue-indicator"><span></span><span></span><span></span></div>
          <div>
            <span>小值研判</span>
            <p>{{ primaryAttention.diagnosis || '正在结合监测数据、设备状态和近期任务记录形成初步判断。' }}</p>
          </div>
        </section>

        <div class="core-actions">
          <button type="button" @click="analyzePrimaryAttention">补充诊断</button>
          <button class="primary" type="button" @click="submitQuery('根据当前研判结果生成核查任务草案，并列出需要人工确认的内容。')">生成核查任务</button>
        </div>
      </section>

      <aside class="intel-rail rail-right" aria-label="智能研判与处置建议">
        <section class="glass-panel station-panel">
          <header class="panel-heading">
            <div><span>站点感知</span><strong>{{ stationName }}</strong></div>
            <em class="healthy">连接正常</em>
          </header>
          <div class="station-scene" aria-hidden="true">
            <span class="scene-sky"></span>
            <span class="scene-road"></span>
            <span class="scene-building building-one"></span>
            <span class="scene-building building-two"></span>
            <span class="scene-station"><i></i><i></i><i></i></span>
            <span class="scene-scan"></span>
            <span class="scene-tag">站房在线</span>
          </div>
        </section>

        <section class="glass-panel diagnosis-panel">
          <header class="panel-heading">
            <div><span>智能研判</span><strong>当前判断与证据</strong></div>
            <em>{{ confidenceLabel(primaryAttention.confidence) }}</em>
          </header>
          <p class="diagnosis-copy">{{ primaryAttention.diagnosis || '暂未形成明确结论，建议继续补充关键证据。' }}</p>
          <div class="evidence-list">
            <span v-for="evidence in primaryEvidence" :key="evidence"><i>✓</i>{{ evidence }}</span>
          </div>
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
            <div><strong>建议安排当班运维人员</strong><small>派发前需确认人员位置与当前任务</small></div>
          </div>
          <div class="dispatch-actions">
            <button type="button" @click="submitQuery('调整当前核查任务的人员安排，请先向我确认调度范围。')">调整方案</button>
            <button class="confirm" type="button" @click="submitQuery('确认基于当前建议生成核查任务草案，提交前展示完整内容供我审核。')">确认生成</button>
          </div>
        </section>
      </aside>
    </section>

    <form class="command-dock" @submit.prevent="submitQuery(query)">
      <span class="dock-mark" aria-hidden="true">
        <svg viewBox="0 0 28 28"><path d="M6 9.5 14 5l8 4.5v9L14 23l-8-4.5v-9Z" /><path d="M10 12h8M11 16h6" /></svg>
      </span>
      <div class="dock-input">
        <span>与{{ coordinator.name || '小值' }}对话</span>
        <input v-model="query" :placeholder="coordinator.placeholder || '描述需要查看或处理的运维事项……'" />
      </div>
      <div class="dock-prompts">
        <button v-for="item in quickPrompts.slice(0, 2)" :key="item.label" type="button" @click="submitQuery(item.prompt, item.mode)">{{ item.label }}</button>
      </div>
      <button class="dock-send" type="submit" :disabled="!query.trim() || Boolean(selectingMode)" aria-label="发送给小值">
        <svg viewBox="0 0 24 24"><path d="m4 12 16-8-5.5 16-3-6.5L4 12Z" /><path d="m11.5 13.5 4-4" /></svg>
      </button>
    </form>
  </main>
</template>

<script setup>
import { computed, ref } from 'vue'
import { normalizeAttentionItem, resolveCoordinatorMode } from './coordinatorWorkspace.js'

const props = defineProps({
  coordinator: { type: Object, default: () => ({}) },
  agents: { type: Array, default: () => [] },
  selectingMode: { type: String, default: '' }
})
const emit = defineEmits(['select', 'submit', 'switch-view'])
const query = ref('')

const quickPrompts = computed(() => props.coordinator.quickPrompts || [])
const attentionItems = computed(() => (props.coordinator.demoAttentionItems || [])
  .map(normalizeAttentionItem)
  .filter(Boolean))
const primaryAttention = computed(() => attentionItems.value[0] || normalizeAttentionItem({
  id: 'command-center-empty',
  title: '当前没有需要优先处置的站点',
  summary: '小值正在持续巡查全省站点和运维任务，有新情况时会及时提醒。',
  severity: 'info',
  status: 'new',
  diagnosis: '当前运行态势平稳。',
  evidence: ['站点连接状态正常', '巡查任务持续运行']
}))
const primaryEvidence = computed(() => (primaryAttention.value.evidence || []).slice(0, 3))
const stationName = computed(() => primaryAttention.value.station || String(primaryAttention.value.title || '').split('·')[0].trim() || '重点关注站点')
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
const analyzePrimaryAttention = () => {
  const action = primaryAttention.value.actions?.[0]
  submitQuery(action?.prompt || `继续研判${primaryAttention.value.title}，补充关键证据并形成处置建议。`, action?.mode)
}
const severityLabel = value => ({ critical: '紧急', high: '高优先级', medium: '需要关注', low: '一般', info: '运行信息' }[value] || '运行信息')
const confidenceLabel = value => ({ high: '判断较明确', medium: '初步判断', low: '线索不足' }[value] || '持续分析')
</script>

<style scoped>
.command-center {
  --cyan: #42f1e1;
  --cyan-soft: #79fff0;
  --blue: #39aef3;
  --panel: rgba(5, 31, 53, .76);
  --line: rgba(74, 220, 230, .28);
  position: relative;
  width: 100%;
  min-width: 0;
  min-height: 100%;
  flex: 1 1 0%;
  overflow: hidden auto;
  color: #eafcff;
  background:
    radial-gradient(circle at 50% 42%, rgba(21, 129, 166, .3), transparent 31%),
    radial-gradient(circle at 4% 48%, rgba(24, 109, 141, .22), transparent 29%),
    linear-gradient(145deg, #020d1b 0%, #04192b 48%, #03111f 100%);
}
.grid-field { position: absolute; inset: 0; opacity: .24; pointer-events: none; background-image: linear-gradient(rgba(79,200,219,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(79,200,219,.08) 1px, transparent 1px); background-size: 42px 42px; mask-image: linear-gradient(to bottom, transparent, #000 18%, #000 82%, transparent); }
.top-aura { position: absolute; top: -220px; left: 50%; width: 780px; height: 400px; transform: translateX(-50%); border-radius: 50%; opacity: .34; background: #1596bc; filter: blur(100px); pointer-events: none; }
.scan-line { position: absolute; z-index: 0; top: 94px; left: 10%; width: 80%; height: 1px; background: linear-gradient(90deg, transparent, rgba(76,238,235,.55), transparent); box-shadow: 0 0 14px rgba(54,227,226,.6); }
.center-header { position: relative; z-index: 4; display: flex; min-height: 94px; align-items: center; justify-content: space-between; gap: 24px; padding: 18px clamp(24px, 3.2vw, 58px); border-bottom: 1px solid rgba(72,207,223,.17); background: linear-gradient(180deg, rgba(3,15,29,.92), rgba(3,19,34,.46)); }
.center-brand, .header-actions, .system-status, .view-switch { display: flex; align-items: center; }.center-brand { gap: 14px; }.brand-mark { display: grid; width: 49px; height: 49px; place-items: center; border: 1px solid rgba(76,239,234,.36); border-radius: 13px; background: rgba(21,118,145,.22); box-shadow: inset 0 0 20px rgba(42,222,224,.12), 0 0 20px rgba(32,189,203,.1); }.brand-mark svg { width: 35px; fill: none; stroke: var(--cyan-soft); stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; }.center-brand span:not(.brand-mark) { color: #62cbd5; font-size: 10px; font-weight: 700; letter-spacing: .13em; }.center-brand h1 { margin: 3px 0 0; font-size: clamp(20px, 1.55vw, 28px); letter-spacing: .08em; text-shadow: 0 0 18px rgba(105,240,239,.16); }.header-actions { gap: 12px; }.system-status { gap: 8px; color: #82d9dd; font-size: 11px; }.system-status i { width: 7px; height: 7px; border-radius: 50%; background: #4af0a1; box-shadow: 0 0 0 4px rgba(74,240,161,.1), 0 0 14px rgba(74,240,161,.7); }.view-switch { gap: 7px; padding: 9px 13px; border: 1px solid rgba(92,218,226,.33); border-radius: 8px; background: rgba(16,78,101,.26); color: #c9f6f7; cursor: pointer; }.view-switch:hover { border-color: rgba(103,246,240,.65); background: rgba(21,105,127,.4); }.view-switch svg { width: 16px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-width: 1.7; }
.center-stage { position: relative; z-index: 2; display: grid; width: min(1720px, calc(100% - 54px)); min-height: 720px; margin: 0 auto; padding: 26px 0 122px; grid-template-columns: minmax(260px, .86fr) minmax(410px, 1.18fr) minmax(270px, .9fr); gap: clamp(16px, 1.45vw, 27px); }
.intel-rail { display: grid; align-content: center; gap: 15px; }.glass-panel { position: relative; overflow: hidden; border: 1px solid var(--line); border-radius: 6px; background: linear-gradient(135deg, rgba(7,40,64,.88), rgba(5,24,43,.68)); box-shadow: inset 0 0 30px rgba(26,134,161,.06), 0 16px 45px rgba(0,0,0,.18); backdrop-filter: blur(15px); }.glass-panel::before, .glass-panel::after { position: absolute; width: 26px; height: 2px; background: var(--cyan); box-shadow: 0 0 9px rgba(66,241,225,.65); content: ''; }.glass-panel::before { top: 0; left: 0; }.glass-panel::after { right: 0; bottom: 0; }.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 16px 18px 0; }.panel-heading div { display: grid; gap: 3px; }.panel-heading span { color: #59dce1; font-size: 10px; font-weight: 800; letter-spacing: .12em; }.panel-heading strong { font-size: 13px; }.panel-heading em { padding: 3px 7px; border: 1px solid rgba(244,184,77,.26); border-radius: 999px; background: rgba(244,162,52,.08); color: #ffd481; font-size: 9px; font-style: normal; white-space: nowrap; }.panel-heading em.healthy { border-color: rgba(55,227,170,.22); background: rgba(42,210,159,.07); color: #6ef3c0; }
.attention-panel { min-height: 208px; padding-bottom: 17px; }.attention-level { display: flex; align-items: center; gap: 7px; margin: 14px 18px 0; color: #ffbd73; font-size: 10px; }.attention-level i { width: 6px; height: 6px; border-radius: 50%; background: #ff9b4d; box-shadow: 0 0 10px #ff9b4d; }.attention-panel h2 { margin: 8px 18px 5px; font-size: 16px; }.attention-panel p { display: -webkit-box; margin: 0 18px; overflow: hidden; color: #8eb5c1; font-size: 11px; line-height: 1.7; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }.attention-panel > button { margin: 13px 18px 0; padding: 7px 10px; border: 1px solid rgba(78,219,224,.32); border-radius: 5px; background: rgba(33,144,162,.12); color: #83e8e7; cursor: pointer; font-size: 10px; }
.trend-panel { min-height: 232px; }.trend-chart { width: calc(100% - 36px); height: 116px; margin: 10px 18px 0; overflow: visible; }.chart-grid { fill: none; stroke: rgba(112,181,197,.12); stroke-width: 1; }.trend-area { fill: url(#areaFill); }.trend-line { fill: none; stroke: #37e7cf; stroke-linecap: round; stroke-width: 2.6; filter: drop-shadow(0 0 5px rgba(55,231,207,.5)); }.chart-points circle { fill: #e3fffb; stroke: #31d9c9; stroke-width: 2; }.trend-legend { display: flex; align-items: center; justify-content: space-between; padding: 0 18px 15px; color: #769ca8; font-size: 9px; }.trend-legend span { display: flex; align-items: center; gap: 6px; }.trend-legend i { width: 14px; height: 2px; background: #37e7cf; }.trend-legend strong { color: #6ff3de; font-size: 15px; }
.overview-panel { min-height: 126px; }.overview-items { display: grid; padding: 17px 18px 19px; grid-template-columns: repeat(3, 1fr); }.overview-items div { display: grid; justify-items: center; border-right: 1px solid rgba(86,181,195,.16); }.overview-items div:last-child { border-right: 0; }.overview-items span { color: #759aa5; font-size: 9px; }.overview-items strong { margin-top: 4px; color: #eaffff; font-size: 22px; }.overview-items small { color: #5c8e9b; font-size: 9px; }
.ai-core-column { position: relative; display: flex; min-height: 650px; align-items: center; flex-direction: column; justify-content: center; }.core-status { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; color: #72dce1; font-size: 10px; letter-spacing: .12em; }.core-status i { width: 6px; height: 6px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 11px var(--cyan); }.orbital-core { position: relative; width: clamp(330px, 29vw, 500px); aspect-ratio: 1; }.orbit, .core-energy, .core-copy { position: absolute; border-radius: 50%; }.orbit { border: 1px solid rgba(78,229,230,.32); }.orbit::before, .orbit::after { position: absolute; border: solid rgba(91,238,238,.58); border-width: 3px 0; border-radius: 50%; content: ''; }.orbit-outer { inset: 4%; animation: rotate-clockwise 22s linear infinite; box-shadow: inset 0 0 36px rgba(24,168,190,.1), 0 0 26px rgba(27,159,184,.1); }.orbit-outer::before { inset: -8px; transform: rotate(42deg); }.orbit-outer::after { inset: 16px; transform: rotate(-28deg); border-color: rgba(79,165,208,.28); }.orbit-middle { inset: 16%; animation: rotate-counter 13s linear infinite; border-width: 2px; border-style: dashed; }.orbit-middle::before { inset: -5px; transform: rotate(86deg); }.orbit-middle::after { inset: 12px; transform: rotate(-49deg); }.orbit-inner { inset: 29%; border: 2px solid rgba(115,251,241,.52); animation: pulse-core 3.3s ease-in-out infinite; box-shadow: inset 0 0 38px rgba(47,218,220,.18), 0 0 40px rgba(31,199,211,.2); }.orbit > i { position: absolute; width: 7px; height: 7px; border-radius: 50%; background: #9dfff6; box-shadow: 0 0 11px #4ce8e1; }.orbit-outer i:nth-child(1) { top: 11%; left: 24%; }.orbit-outer i:nth-child(2) { right: 3%; bottom: 38%; }.orbit-outer i:nth-child(3) { bottom: 4%; left: 38%; }.orbit-middle i:nth-child(1) { top: 15%; right: 13%; }.orbit-middle i:nth-child(2) { bottom: 12%; left: 18%; }.core-energy { inset: 33%; background: radial-gradient(circle at 48% 46%, #ddffff 0 1%, #65f1e8 2%, rgba(31,196,211,.58) 13%, rgba(8,91,133,.42) 42%, rgba(2,23,42,.2) 68%); filter: drop-shadow(0 0 20px rgba(57,227,231,.48)); animation: breathe 2.7s ease-in-out infinite; }.core-copy { inset: 34%; display: grid; place-content: center; justify-items: center; text-align: center; }.core-copy small { color: rgba(143,238,239,.58); font-size: 7px; letter-spacing: .18em; }.core-copy strong { margin: 5px 0 2px; color: #edffff; font-size: clamp(25px, 2.1vw, 37px); letter-spacing: .18em; text-indent: .18em; text-shadow: 0 0 20px rgba(111,250,245,.52); }.core-copy em { color: #70d7df; font-size: 9px; font-style: normal; letter-spacing: .12em; }
.core-dialogue { position: relative; z-index: 2; display: flex; width: min(500px, 92%); align-items: flex-start; gap: 12px; margin-top: -19px; padding: 13px 15px; border: 1px solid rgba(81,220,225,.27); border-radius: 8px; background: rgba(5,31,50,.8); box-shadow: 0 12px 35px rgba(0,0,0,.2), inset 0 0 28px rgba(38,174,191,.06); backdrop-filter: blur(14px); }.dialogue-indicator { display: flex; width: 34px; height: 34px; flex: none; align-items: center; justify-content: center; gap: 2px; border-radius: 50%; background: rgba(33,151,169,.2); }.dialogue-indicator span { width: 2px; border-radius: 2px; background: #63eee4; animation: voice-wave 1s ease-in-out infinite; }.dialogue-indicator span:nth-child(1) { height: 8px; }.dialogue-indicator span:nth-child(2) { height: 15px; animation-delay: .15s; }.dialogue-indicator span:nth-child(3) { height: 10px; animation-delay: .3s; }.core-dialogue > div:last-child { min-width: 0; }.core-dialogue span { color: #4bdedc; font-size: 9px; font-weight: 800; }.core-dialogue p { margin: 3px 0 0; color: #b5d4d9; font-size: 11px; line-height: 1.6; }.core-actions { display: flex; gap: 8px; margin-top: 10px; }.core-actions button { padding: 8px 14px; border: 1px solid rgba(78,211,218,.29); border-radius: 5px; background: rgba(12,63,82,.6); color: #9bdde0; cursor: pointer; font-size: 10px; }.core-actions button.primary { border-color: rgba(76,239,224,.56); background: linear-gradient(135deg, rgba(17,144,157,.72), rgba(9,88,121,.75)); color: #ecffff; box-shadow: 0 0 18px rgba(38,213,207,.12); }
.station-panel { min-height: 216px; }.station-scene { position: relative; height: 143px; margin: 12px 18px 18px; overflow: hidden; border: 1px solid rgba(84,206,219,.24); border-radius: 4px; background: linear-gradient(#0c4968 0 47%, #0a3048 47% 100%); }.scene-sky { position: absolute; inset: 0; background: radial-gradient(circle at 75% 18%, rgba(105,238,237,.38), transparent 20%), linear-gradient(170deg, transparent 52%, rgba(76,181,193,.15) 53%); }.scene-road { position: absolute; right: -15%; bottom: -42%; width: 84%; height: 80%; transform: rotate(-8deg); border-left: 2px solid rgba(98,240,235,.28); background: linear-gradient(90deg, rgba(12,42,59,.7), rgba(20,84,101,.6)); }.scene-building { position: absolute; bottom: 31%; background: linear-gradient(135deg, #103d54, #17647a); box-shadow: inset -10px 0 18px rgba(0,0,0,.2); }.building-one { left: 0; width: 34%; height: 43%; }.building-two { right: 9%; width: 28%; height: 56%; }.scene-station { position: absolute; bottom: 27%; left: 48%; width: 46px; height: 54px; border: 1px solid rgba(114,241,235,.54); background: rgba(5,27,43,.85); box-shadow: 0 0 17px rgba(49,216,218,.19); }.scene-station i { position: absolute; top: -24px; left: 21px; width: 2px; height: 24px; background: #7aece7; }.scene-station i:nth-child(2) { top: -13px; left: 10px; width: 23px; height: 1px; }.scene-station i:nth-child(3) { top: 12px; left: 11px; width: 22px; height: 22px; border: 1px solid rgba(78,222,220,.42); background: transparent; }.scene-scan { position: absolute; top: -20%; left: 41%; width: 90px; height: 130%; transform: perspective(100px) rotateX(18deg); border: 1px solid rgba(65,240,228,.18); border-radius: 50%; animation: scene-scan 3.4s ease-in-out infinite; }.scene-tag { position: absolute; top: 9px; right: 9px; padding: 3px 6px; border: 1px solid rgba(83,239,217,.32); background: rgba(4,34,48,.7); color: #70efd3; font-size: 8px; }
.diagnosis-panel { min-height: 181px; }.diagnosis-copy { margin: 14px 18px 8px; color: #b3d6db; font-size: 11px; line-height: 1.65; }.evidence-list { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 18px 17px; }.evidence-list span { display: flex; align-items: center; gap: 5px; padding: 4px 7px; border: 1px solid rgba(87,185,198,.18); border-radius: 4px; background: rgba(30,96,113,.12); color: #82b5bf; font-size: 9px; }.evidence-list i { color: #5be8cf; font-style: normal; }
.dispatch-panel { min-height: 195px; }.dispatch-person { display: flex; align-items: center; gap: 10px; margin: 14px 18px; padding: 10px; border: 1px solid rgba(82,188,200,.16); background: rgba(16,67,86,.26); }.person-icon { display: grid; width: 35px; height: 35px; flex: none; place-items: center; border-radius: 50%; background: rgba(30,148,162,.22); }.person-icon svg { width: 23px; fill: none; stroke: #7fe9e5; stroke-linecap: round; stroke-width: 1.4; }.dispatch-person div { display: grid; gap: 3px; }.dispatch-person strong { font-size: 10px; }.dispatch-person small { color: #7499a4; font-size: 8px; }.dispatch-actions { display: grid; gap: 8px; padding: 0 18px 17px; grid-template-columns: 1fr 1fr; }.dispatch-actions button { padding: 8px; border: 1px solid rgba(80,183,197,.25); border-radius: 4px; background: rgba(11,55,75,.7); color: #8fc8cf; cursor: pointer; font-size: 9px; }.dispatch-actions button.confirm { border-color: rgba(66,239,222,.5); background: linear-gradient(135deg, rgba(18,146,153,.65), rgba(8,90,122,.72)); color: #edffff; }
.command-dock { position: absolute; z-index: 8; right: clamp(24px, 4vw, 70px); bottom: 24px; left: clamp(24px, 4vw, 70px); display: flex; min-height: 68px; align-items: center; gap: 13px; padding: 9px 10px 9px 15px; border: 1px solid rgba(80,221,225,.31); border-radius: 10px; background: rgba(4,25,42,.92); box-shadow: 0 18px 50px rgba(0,0,0,.4), inset 0 0 30px rgba(38,161,179,.06); backdrop-filter: blur(20px); }.dock-mark { display: grid; width: 41px; height: 41px; flex: none; place-items: center; border: 1px solid rgba(79,232,226,.27); border-radius: 10px; background: rgba(26,129,150,.18); }.dock-mark svg { width: 27px; fill: none; stroke: #72ece6; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.3; }.dock-input { display: grid; min-width: 140px; flex: 1; gap: 2px; }.dock-input span { color: #53d8db; font-size: 8px; font-weight: 800; letter-spacing: .11em; }.dock-input input { width: 100%; padding: 0; border: 0; outline: 0; background: transparent; color: #e8ffff; font: inherit; font-size: 12px; }.dock-input input::placeholder { color: #668993; }.dock-prompts { display: flex; gap: 6px; }.dock-prompts button { padding: 6px 8px; border: 1px solid rgba(81,184,198,.17); border-radius: 5px; background: rgba(26,82,99,.17); color: #7cabb5; cursor: pointer; font-size: 9px; }.dock-send { display: grid; width: 47px; height: 47px; flex: none; place-items: center; border: 1px solid rgba(91,240,230,.47); border-radius: 9px; background: linear-gradient(135deg, #138e9b, #0b6689); color: #efffff; cursor: pointer; box-shadow: 0 0 18px rgba(40,218,213,.13); }.dock-send:disabled { cursor: default; opacity: .35; }.dock-send svg { width: 22px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.7; }
button:focus-visible, input:focus-visible { outline: 3px solid rgba(88,241,233,.32); outline-offset: 2px; }
@keyframes rotate-clockwise { to { transform: rotate(360deg); } }
@keyframes rotate-counter { to { transform: rotate(-360deg); } }
@keyframes pulse-core { 50% { transform: scale(1.035); border-color: rgba(131,255,245,.82); } }
@keyframes breathe { 50% { transform: scale(1.1); opacity: .82; } }
@keyframes voice-wave { 50% { transform: scaleY(.45); opacity: .55; } }
@keyframes scene-scan { 50% { transform: perspective(100px) rotateX(18deg) scale(.7); opacity: .25; } }
@media (max-width: 1250px) { .center-stage { grid-template-columns: minmax(240px, .9fr) minmax(380px, 1.15fr) minmax(250px, .9fr); width: calc(100% - 34px); gap: 12px; }.center-header { padding-inline: 22px; }.panel-heading { padding-inline: 13px; }.attention-panel h2, .attention-panel p, .attention-level { margin-inline: 13px; }.dock-prompts { display: none; } }
@media (max-width: 980px) { .command-center { overflow: auto; }.center-stage { grid-template-columns: 1fr 1fr; padding-bottom: 110px; }.ai-core-column { min-height: 580px; grid-column: 1 / -1; grid-row: 1; }.intel-rail { align-content: start; }.command-dock { position: fixed; }.orbital-core { width: 410px; }.system-status { display: none; } }
@media (max-width: 700px) { .center-header { align-items: flex-start; }.center-brand h1 { font-size: 17px; }.brand-mark { width: 42px; height: 42px; }.view-switch { padding: 8px; font-size: 0; }.view-switch svg { width: 19px; }.center-stage { grid-template-columns: 1fr; }.ai-core-column, .intel-rail { grid-column: 1; }.rail-left { grid-row: 2; }.rail-right { grid-row: 3; }.orbital-core { width: min(390px, 92vw); }.command-dock { right: 10px; bottom: 10px; left: 10px; }.dock-mark { display: none; } }
@media (prefers-reduced-motion: reduce) { .orbit, .core-energy, .dialogue-indicator span, .scene-scan { animation: none; } }
</style>
