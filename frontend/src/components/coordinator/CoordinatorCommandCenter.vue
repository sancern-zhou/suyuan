<template>
  <main ref="screenRef" class="command-center" :class="[`workspace-${workspace}`, `scene-${scene}`, `voice-${voiceState}`]">
    <div class="grid-field" aria-hidden="true"></div>
    <div class="screen-aura aura-one" aria-hidden="true"></div>
    <div class="screen-aura aura-two" aria-hidden="true"></div>

    <header class="center-header">
      <div class="center-brand">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 44 44">
            <path d="M9 15.5 22 8l13 7.5v14L22 37 9 29.5v-14Z" />
            <path d="M15 19.5h14M16.5 25h11M19 30h6" />
          </svg>
        </span>
        <div><span>{{ coordinator.role || '江苏运维智能值班助手' }}</span><h1>空气站智能运维中枢</h1></div>
      </div>

      <div class="session-status" aria-label="当前智能工作会话">
        <i></i><span>持续会话</span><strong>{{ workspaceLabel }}</strong><em>场景演示</em>
      </div>

      <div class="header-actions">
        <span class="system-status"><i></i>系统运行正常</span>
        <span class="update-time">{{ updateTime }} 更新</span>
        <button class="view-switch" type="button" @click="exitCommandCenter">
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5.5h12M4 10h12M4 14.5h8" /></svg>
          <span>返回{{ assistantName }}首页</span>
        </button>
      </div>
    </header>

    <section class="workbench">
      <section class="goal-workspace">
        <header class="objective-bar">
          <div>
            <span class="objective-kicker"><i></i>{{ workspaceEyebrow }}</span>
            <h2>{{ currentObjective }}</h2>
          </div>
          <span class="workspace-state"><small>当前状态</small><strong>{{ workspaceStatus }}</strong></span>
        </header>

        <Transition name="workspace-shift" mode="out-in">
          <section v-if="workspace === workspaces.AMBIENT" key="ambient" class="workspace-canvas ambient-canvas" aria-label="今日值守总览">
            <section class="overview-map-stage">
              <header><div><span>江苏全省</span><h2>今日运维态势</h2></div><em><i></i>总体平稳</em></header>
              <JiangsuSituationMap :focus-region="scene === scenes.ALERT ? 'nanjing' : ''" mode="overview" />
              <span class="overview-map-note">真实行政边界 · 293 个在用站点</span>
            </section>

            <aside class="overview-events" aria-label="今日关注事件">
              <header><div><span>今日关注</span><strong>3</strong></div><small>场景演示</small></header>
              <div class="overview-event-list">
                <button :class="{ spotlight: scene === scenes.ALERT }" type="button" @click="runVoicePrompt('展开源创包装厂房站点异常')">
                  <span class="event-state danger"><i></i>高优先级</span>
                  <strong>颗粒物数据中断</strong>
                  <p>源创包装厂房（1002A）</p>
                  <small>PM2.5、PM10 自 09:12 停止更新</small>
                  <em>展开调查 <b>→</b></em>
                </button>
                <button type="button" @click="runVoicePrompt('分析全省智慧运维调度')">
                  <span class="event-state warning"><i></i>需要分析</span>
                  <strong>智慧运维调度</strong>
                  <p>单位、人员、任务与站点综合分析</p>
                  <small>跨市运维 · 轨迹洞察 · 高频到站 · 资源优化</small>
                  <em>查看分析 <b>→</b></em>
                </button>
                <button type="button" @click="runVoicePrompt('识别外部环境干扰')">
                  <span class="event-state warning"><i></i>AI 待研判</span>
                  <strong>外部环境干扰识别</strong>
                  <p>南京恩梯恩精密机械公司（1006A）</p>
                  <small>视频发现疑似喷淋雾炮进入采样影响范围</small>
                  <em>展开识别 <b>→</b></em>
                </button>
              </div>
            </aside>
          </section>

          <section v-else-if="workspace === workspaces.INVESTIGATION" key="investigation" class="workspace-canvas investigation-canvas" aria-label="源创包装厂房站点异常连续调查工作区">
            <section class="conversation-evidence" aria-label="对话历史与 AI 证据链">
              <header><div><span>与{{ assistantName }}的调查对话</span><strong>证据随追问持续补充</strong></div><em>{{ revealLevel }}/4</em></header>
              <div class="conversation-history">
                <div class="conversation-query"><span>你</span><p>展开源创包装厂房站点异常。</p></div>
                <article class="assistant-turn">
                  <span class="turn-avatar">AI</span>
                  <div>
                    <p>发现 PM2.5、PM10 同步断数，先把已确认的证据放进调查链。</p>
                    <p class="dialogue-evidence"><span><strong>关键数据：</strong>09:12 起，两个颗粒物因子停止更新。</span><span><strong>AI 小结：</strong>气态因子仍正常更新，暂不支持平台整体异常。</span></p>
                    <figure class="evidence-snapshot"><img v-if="coordinator.stationImageUrl" :src="coordinator.stationImageUrl" alt="源创包装厂房站点关键监控截图" /><div v-else>监控截图</div><figcaption>关键监控截图 · 站房画面正常</figcaption></figure>
                  </div>
                </article>

                <Transition name="grow-panel">
                  <div v-if="revealLevel >= 2" class="conversation-step">
                    <div class="conversation-query"><span>你</span><p>这个问题可能是什么原因？</p></div>
                    <article class="assistant-turn compact"><span class="turn-avatar">AI</span><div><p><strong>更可能是采集或传输链路异常。</strong> 分析设备异常仍需排查；通信日志和设备状态缺失，不能直接认定故障。</p><small class="answer-boundary">判断边界 · 当前为初步假设</small></div></article>
                  </div>
                </Transition>

                <Transition name="grow-panel">
                  <div v-if="revealLevel >= 3" class="conversation-step">
                    <div class="conversation-query"><span>你</span><p>附近谁可以到站处理？</p></div>
                    <article class="assistant-turn compact"><span class="turn-avatar">AI</span><div><p>综合距离、设备经验和当前负荷，建议优先确认<strong>王某某</strong>：距站点 12 公里，预计 30 分钟到达，有相关设备经验。</p></div></article>
                  </div>
                </Transition>

                <Transition name="grow-panel">
                  <div v-if="revealLevel >= 4" class="conversation-step">
                    <div class="conversation-query"><span>你</span><p>生成核查任务草案。</p></div>
                    <article class="assistant-turn plan-turn"><span class="turn-avatar">AI</span><button class="dispatch-plan" type="button"><header><span>调度计划草案</span><em>等待人工确认</em></header><strong>王某某 · 10:00 前到站</strong><p>检查数采仪与设备状态 → 导出通信日志 → 恢复后观察 30 分钟</p><span class="plan-link">打开详细操作工作台 <i>→</i></span></button></article>
                  </div>
                </Transition>
              </div>
            </section>

            <StationInterruptionEvidence :station-image-url="coordinator.stationImageUrl" />
          </section>

          <section v-else-if="workspace === workspaces.MOBILITY" key="mobility" class="workspace-canvas mobility-canvas" aria-label="全省智慧运维调度连续分析工作区">
            <section class="dispatch-evidence" aria-label="智慧运维调度关键截图与地图证据">
              <header>
                <div><span>AI 关键截图</span><strong>{{ revealLevel >= 2 ? '近 30 日调度轨迹综合分析' : '全省单位、人员与任务分布' }}</strong></div>
                <em>调度信号均为场景模拟</em>
              </header>
              <nav v-if="revealLevel >= 2" class="dispatch-layer-switch" aria-label="调度证据图层" @mouseleave="activeDispatchLayer = ''">
                <button type="button" :class="{ active: activeDispatchLayer === '' }" @click="activeDispatchLayer = ''">全部证据</button>
                <button type="button" :class="{ active: activeDispatchLayer === 'cross-city' }" @mouseenter="activeDispatchLayer = 'cross-city'" @focus="activeDispatchLayer = 'cross-city'" @blur="activeDispatchLayer = ''">跨市任务</button>
                <button type="button" :class="{ active: activeDispatchLayer === 'unit' }" @mouseenter="activeDispatchLayer = 'unit'" @focus="activeDispatchLayer = 'unit'" @blur="activeDispatchLayer = ''">运维单位轨迹</button>
                <button type="button" :class="{ active: activeDispatchLayer === 'person' }" @mouseenter="activeDispatchLayer = 'person'" @focus="activeDispatchLayer = 'person'" @blur="activeDispatchLayer = ''">运维人员轨迹</button>
                <button type="button" :class="{ active: activeDispatchLayer === 'station' }" @mouseenter="activeDispatchLayer = 'station'" @focus="activeDispatchLayer = 'station'" @blur="activeDispatchLayer = ''">频繁到站站点</button>
              </nav>
              <div class="dispatch-map-frame">
                <JiangsuSituationMap :focus-region="revealLevel >= 2 ? 'dispatch' : ''" :active-layer="activeDispatchLayer" mode="province" />
              </div>
              <footer><span>真实行政边界与 293 个在用站点</span><strong>截图依据：工单、签到、人员定位与到站记录</strong></footer>
            </section>

            <section class="conversation-evidence dispatch-conversation" aria-label="智慧运维调度 AI 对话区">
              <header><div><span>与{{ assistantName }}的调度分析对话</span><strong>数据、截图和结论随追问持续补充</strong></div><em>{{ revealLevel }}/2</em></header>
              <div class="conversation-history">
                <div class="conversation-query"><span>你</span><p>展示全省智慧运维调度情况。</p></div>
                <article class="assistant-turn">
                  <span class="turn-avatar">AI</span>
                  <div>
                    <p>我先汇总近 30 日的单位、人员、任务和站点到访记录，并把空间分布放入左侧关键截图。</p>
                    <p class="dialogue-evidence dispatch-data-lines">
                      <span><strong>跨市任务：</strong>41 次，其中 14 次具备属地技能人员承接条件。</span>
                      <span><strong>运维单位轨迹：</strong>7 条高频协作路线，2 处服务覆盖存在交叉。</span>
                      <span><strong>运维人员轨迹：</strong>6 人连续跨区执行任务，3 人任务负荷偏高。</span>
                      <span><strong>频繁到站站点：</strong>12 个站点被频繁到访，其中 5 个存在重复问题。</span>
                    </p>
                    <small class="answer-boundary">数据边界 · 人员、轨迹、任务频次与调度结论均为场景模拟</small>
                  </div>
                </article>

                <Transition name="grow-panel">
                  <div v-if="revealLevel >= 2" class="conversation-step">
                    <div class="conversation-query"><span>你</span><p>这些资源应该怎样调度和优化？</p></div>
                    <article class="assistant-turn compact dispatch-conclusion">
                      <span class="turn-avatar">AI</span>
                      <div>
                        <p><strong>当前更像是任务组织方式需要优化，不建议直接增加人员。</strong> 应优先合并同区域、相邻时段任务，将高频到站的重复问题转为专项治理，再按属地、技能和负荷动态派单；跨市运维只作为能力兜底。</p>
                        <p class="dialogue-evidence dispatch-result-lines"><span><strong>模拟效果：</strong>无效往返减少 34%，里程减少 1,260 公里，平均响应时间缩短 18 分钟。</span><span><strong>建议顺序：</strong>属地优先 → 技能匹配 → 负荷校准 → 同路合并 → 专项治理 → 跨市兜底。</span></p>
                        <button class="dispatch-plan dispatch-optimization-plan" type="button"><header><span>智慧调度优化方案草案</span><em>等待人工确认</em></header><strong>6 项资源优化建议</strong><p>包含任务合并、属地承接、人员负荷调整和高频站点专项治理建议</p><span class="plan-link">打开详细操作工作台 <i>→</i></span></button>
                      </div>
                    </article>
                  </div>
                </Transition>
              </div>
            </section>
          </section>

          <section v-else-if="workspace === workspaces.INTERFERENCE" key="interference" class="workspace-canvas investigation-canvas interference-canvas" aria-label="外部环境干扰识别连续分析工作区">
            <section class="conversation-evidence interference-conversation" aria-label="外部环境干扰识别 AI 对话区">
              <header><div><span>与{{ assistantName }}的干扰识别对话</span><strong>视频、数据和判断依据随追问持续补充</strong></div><em>{{ revealLevel }}/4</em></header>
              <div class="conversation-history">
                <div class="conversation-query"><span>你</span><p>查看外部环境干扰识别告警。</p></div>
                <article class="assistant-turn">
                  <span class="turn-avatar">AI</span>
                  <div>
                    <p>视频模型在 1006A 站点东北侧识别到<strong>疑似喷淋雾炮</strong>，持续约 8 分钟。我先保留原始片段、目标框和识别置信度。</p>
                    <p class="dialogue-evidence"><span><strong>视频识别：</strong>喷淋雾炮 86%，同时支持车辆停靠、人员靠近和摄像头遮挡识别。</span><span><strong>告警初筛：</strong>23 条原始告警中，18 条抖动、光照变化和短暂停留已过滤，5 条进入关联分析。</span></p>
                    <small class="answer-boundary">识别边界 · 视频目标不等同于已确认干扰</small>
                  </div>
                </article>

                <Transition name="grow-panel">
                  <div v-if="revealLevel >= 2" class="conversation-step">
                    <div class="conversation-query"><span>你</span><p>筛选告警并做时空关联。</p></div>
                    <article class="assistant-turn compact interference-turn"><span class="turn-avatar">AI</span><div><p>事件发生于<strong>09:36—09:44</strong>，喷淋区域位于站点东北侧约 120 米；同期为东北风 2.1 米/秒，目标处于采样点上风向，且时间窗与本站颗粒物抬升重合。</p><small class="answer-boundary">关联依据 · 视频位置、时间、风向风速与分钟数据</small></div></article>
                  </div>
                </Transition>

                <Transition name="grow-panel">
                  <div v-if="revealLevel >= 3" class="conversation-step">
                    <div class="conversation-query"><span>你</span><p>这次事件是否影响监测数据和代表性？</p></div>
                    <article class="assistant-turn compact interference-turn"><span class="turn-avatar">AI</span><div><p><strong>疑似产生局地影响，综合置信度 87%。</strong> 本站 PM10 从 64 升至 142 微克/立方米，邻近站点无同步变化；采样、流量、温控与质控状态正常，近 7 日运维记录也无重合作业。</p><small class="answer-boundary">判断边界 · 建议标记疑似影响并人工复核，不自动判定数据无效</small></div></article>
                  </div>
                </Transition>

                <Transition name="grow-panel">
                  <div v-if="revealLevel >= 4" class="conversation-step">
                    <div class="conversation-query"><span>你</span><p>生成干扰证据包和调度处置草案。</p></div>
                    <article class="assistant-turn plan-turn"><span class="turn-avatar">AI</span><button class="dispatch-plan interference-dispatch-plan" type="button"><header><span>外部环境干扰处置草案</span><em>等待人工确认</em></header><strong>完整证据包 · 现场核查建议</strong><p>视频片段 → 监测数据 → 气象条件 → 设备状态 → 运维记录 → 属地人员现场核查</p><span class="plan-link">打开详细操作工作台 <i>→</i></span></button></article>
                  </div>
                </Transition>
              </div>
            </section>

            <ExternalInterferenceEvidence :station-image-url="coordinator.stationImageUrl" :reveal-level="revealLevel" />
          </section>

        </Transition>
      </section>
    </section>

    <footer class="voice-console" aria-live="polite">
      <div class="assistant-identity">
        <span class="assistant-avatar" :class="{ active: voiceState !== 'idle' }"><img :src="xiaozhiRobotUrl" alt="" /></span>
        <span><small>{{ voiceStatusLabel }}</small><strong>{{ assistantName }}</strong></span>
      </div>

      <div class="voice-content">
        <div v-if="voiceState === 'listening'" class="listening-content"><span class="voice-wave" aria-hidden="true"><i v-for="index in 16" :key="index"></i></span><strong>{{ voiceTranscript || '正在聆听……' }}</strong></div>
        <div v-else-if="voiceState === 'thinking'" class="thinking-content"><span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span><span><small>{{ assistantName }}正在重组工作区</small><strong>正在保留当前上下文并关联目标所需的数据与证据……</strong></span></div>
        <div v-else-if="voiceResponse" class="response-content"><small>{{ assistantName }}</small><strong>{{ voiceResponse }}</strong></div>
        <div v-else class="idle-content"><small>目标式交互已就绪</small><strong>直接说出要解决的问题，当前工作区会围绕目标持续生长</strong></div>
      </div>

      <div class="voice-suggestions"><button v-for="prompt in voicePrompts" :key="prompt" type="button" @click="runVoicePrompt(prompt)">“{{ prompt }}”</button></div>
      <button class="microphone-button" :class="{ listening: voiceState === 'listening' }" type="button" :aria-label="voiceState === 'listening' ? '停止聆听' : `唤醒${assistantName}`" @click="toggleListening"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8.5" y="3" width="7" height="12" rx="3.5" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M8.5 21h7" /></svg></button>
    </footer>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import xiaozhiRobotUrl from '@/assets/coordinator/xiaozhi-robot.png'
import JiangsuSituationMap from './JiangsuSituationMap.vue'
import StationInterruptionEvidence from './StationInterruptionEvidence.vue'
import ExternalInterferenceEvidence from './ExternalInterferenceEvidence.vue'
import {
  COMMAND_CENTER_RESPONSES,
  COMMAND_CENTER_SCENE_SEQUENCE,
  COMMAND_CENTER_SCENES,
  COMMAND_CENTER_WORKSPACES,
  getCommandCenterRevealLevel,
  getCommandCenterWorkspace,
  nextCommandCenterScene,
  resolveCommandCenterScene
} from './commandCenterDemo.js'

const props = defineProps({ coordinator: { type: Object, default: () => ({}) } })
const emit = defineEmits(['switch-view'])

const scenes = COMMAND_CENTER_SCENES
const workspaces = COMMAND_CENTER_WORKSPACES
const scene = ref(scenes.OVERVIEW)
const voiceState = ref('idle')
const voiceTranscript = ref('')
const voiceResponse = ref('')
const activeDispatchLayer = ref('')
const screenRef = ref(null)
const updateTime = ref(formatClock(new Date()))
let recognition = null
let transitionTimer = null
let proactiveTimer = null

const assistantName = computed(() => props.coordinator.name || '苏小环')
const workspace = computed(() => getCommandCenterWorkspace(scene.value))
const revealLevel = computed(() => getCommandCenterRevealLevel(scene.value))
const workspaceLabel = computed(() => ({
  [workspaces.AMBIENT]: '值守态势',
  [workspaces.INVESTIGATION]: '异常调查',
  [workspaces.MOBILITY]: '智慧调度',
  [workspaces.INTERFERENCE]: '干扰识别'
}[workspace.value]))
const workspaceEyebrow = computed(() => ({
  [workspaces.AMBIENT]: `${assistantName.value}正在值守`,
  [workspaces.INVESTIGATION]: '当前目标 · 调查单站异常',
  [workspaces.MOBILITY]: '当前目标 · 优化运维调度',
  [workspaces.INTERFERENCE]: '当前目标 · 识别外部环境干扰'
}[workspace.value]))
const currentObjective = computed(() => ({
  [workspaces.AMBIENT]: '现在最值得关注什么？',
  [workspaces.INVESTIGATION]: '弄清源创包装厂房颗粒物断数的原因，并确定下一步',
  [workspaces.MOBILITY]: '统筹单位、人员与站点需求，优化全省运维资源',
  [workspaces.INTERFERENCE]: '判断外界环境或人为行为是否影响站点运行和监测代表性'
}[workspace.value]))
const workspaceStatus = computed(() => {
  if (scene.value === scenes.ALERT) return '发现新信号'
  if (scene.value === scenes.DIAGNOSIS) return '比较原因假设'
  if (scene.value === scenes.STAFFING) return '追加补证人员'
  if (scene.value === scenes.TASK_DRAFT) return '等待人工审核'
  if (scene.value === scenes.MOBILITY) return '策略模拟完成'
  if (scene.value === scenes.INTERFERENCE_CORRELATION) return '时空证据已关联'
  if (scene.value === scenes.INTERFERENCE_IMPACT) return '影响判断已形成'
  if (scene.value === scenes.INTERFERENCE_PACKAGE) return '等待人工审核'
  if (workspace.value === workspaces.INTERFERENCE) return '视频告警已筛选'
  return workspace.value === workspaces.INVESTIGATION ? '调查已建立' : workspace.value === workspaces.MOBILITY ? '等待分析目标' : '持续观察'
})
const voiceStatusLabel = computed(() => ({ idle: '正在值守', listening: '正在聆听', thinking: '正在分析', speaking: '正在回答' }[voiceState.value] || '正在值守'))
const voicePrompts = computed(() => {
  if (workspace.value === workspaces.AMBIENT) return ['展开源创包装厂房站点异常', '识别外部环境干扰']
  if (scene.value === scenes.ANOMALY) return ['这个问题可能是什么原因', '附近有没有可以到站处理的人员']
  if (scene.value === scenes.DIAGNOSIS) return ['附近有没有可以到站处理的人员', '分析全省智慧运维调度']
  if (scene.value === scenes.STAFFING) return ['为源创包装厂房站点生成任务草案', '分析全省智慧运维调度']
  if (scene.value === scenes.TASK_DRAFT) return ['分析全省智慧运维调度', '恢复今日值守总览']
  if (scene.value === scenes.PROVINCE) return ['分析全省智慧运维调度', '展开源创包装厂房站点异常']
  if (scene.value === scenes.MOBILITY) return ['展开源创包装厂房站点异常', '恢复今日值守总览']
  if (scene.value === scenes.INTERFERENCE) return ['筛选告警并进行时空关联', '恢复今日值守总览']
  if (scene.value === scenes.INTERFERENCE_CORRELATION) return ['判断是否影响监测代表性', '恢复今日值守总览']
  if (scene.value === scenes.INTERFERENCE_IMPACT) return ['生成干扰证据包和处置草案', '恢复今日值守总览']
  if (scene.value === scenes.INTERFERENCE_PACKAGE) return ['分析全省智慧运维调度', '恢复今日值守总览']
  return ['恢复今日值守总览', '展开源创包装厂房站点异常']
})

function formatClock(value) {
  return value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
}
function clearProactiveTimer() {
  if (proactiveTimer) window.clearTimeout(proactiveTimer)
  proactiveTimer = null
}
function clearTransitionTimer() {
  if (transitionTimer) window.clearTimeout(transitionTimer)
  transitionTimer = null
}
function speak(text) {
  if (!('speechSynthesis' in window) || !text) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  utterance.rate = 1.02
  utterance.pitch = 1
  window.speechSynthesis.speak(utterance)
}
function showScene(nextScene, { response = COMMAND_CENTER_RESPONSES[nextScene], announce = false } = {}) {
  clearProactiveTimer()
  if (nextScene !== scenes.MOBILITY) activeDispatchLayer.value = ''
  scene.value = nextScene
  updateTime.value = formatClock(new Date())
  voiceResponse.value = response || ''
  voiceState.value = response ? 'speaking' : 'idle'
  if (announce) speak(response)
  clearTransitionTimer()
  transitionTimer = window.setTimeout(() => { voiceState.value = 'idle' }, 5600)
}
function runVoicePrompt(prompt) {
  if (!prompt) return
  clearProactiveTimer()
  clearTransitionTimer()
  voiceTranscript.value = prompt
  voiceResponse.value = ''
  voiceState.value = 'thinking'
  const nextScene = resolveCommandCenterScene(prompt, scene.value)
  transitionTimer = window.setTimeout(() => showScene(nextScene, { announce: true }), 720)
}
function createRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!Recognition) return null
  const instance = new Recognition()
  instance.lang = 'zh-CN'
  instance.continuous = false
  instance.interimResults = true
  instance.maxAlternatives = 1
  instance.onresult = event => {
    let transcript = ''
    let finalTranscript = ''
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const value = event.results[index][0]?.transcript || ''
      transcript += value
      if (event.results[index].isFinal) finalTranscript += value
    }
    voiceTranscript.value = transcript.trim()
    if (finalTranscript.trim()) runVoicePrompt(finalTranscript.trim())
  }
  instance.onerror = event => {
    voiceState.value = 'idle'
    voiceResponse.value = event.error === 'not-allowed' ? '麦克风权限未开启，可点击推荐语句继续演示。' : '没有听清，请再说一次或点击推荐语句。'
  }
  instance.onend = () => { if (voiceState.value === 'listening') voiceState.value = 'idle' }
  return instance
}
function toggleListening() {
  clearProactiveTimer()
  if (voiceState.value === 'listening') {
    recognition?.stop()
    voiceState.value = 'idle'
    return
  }
  recognition ||= createRecognition()
  if (!recognition) {
    voiceResponse.value = '当前浏览器不支持语音识别，可点击推荐语句继续演示。'
    voiceState.value = 'idle'
    return
  }
  window.speechSynthesis?.cancel()
  voiceTranscript.value = ''
  voiceResponse.value = ''
  voiceState.value = 'listening'
  try { recognition.start() } catch {
    recognition.stop()
    window.setTimeout(() => recognition.start(), 100)
  }
}
function exitCommandCenter() {
  recognition?.abort()
  window.speechSynthesis?.cancel()
  emit('switch-view')
}
function handlePresenterKey(event) {
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
  if (event.key === 'ArrowRight') showScene(nextCommandCenterScene(scene.value, 1))
  if (event.key === 'ArrowLeft') showScene(nextCommandCenterScene(scene.value, -1))
  const directKeys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=']
  const directIndex = directKeys.indexOf(event.key)
  if (directIndex >= 0) {
    const target = COMMAND_CENTER_SCENE_SEQUENCE[directIndex]
    if (target) showScene(target)
  }
  if (event.key.toLocaleLowerCase('zh-CN') === 'v') toggleListening()
  if (event.key === 'Escape' && voiceState.value === 'listening') toggleListening()
}

onMounted(() => {
  window.addEventListener('keydown', handlePresenterKey)
  proactiveTimer = window.setTimeout(() => {
    if (scene.value === scenes.OVERVIEW) showScene(scenes.ALERT, { announce: false })
  }, 6500)
})
onBeforeUnmount(() => {
  clearProactiveTimer()
  clearTransitionTimer()
  recognition?.abort()
  window.speechSynthesis?.cancel()
  window.removeEventListener('keydown', handlePresenterKey)
})
</script>

<style scoped>
.command-center {
  --cyan: #51e0d7;
  --cyan-soft: #a9f6ef;
  --ink: #effdfd;
  --muted: #86a5ae;
  --dim: #54717a;
  position: fixed;
  z-index: 1400;
  inset: 0;
  display: grid;
  width: 100vw;
  height: 100dvh;
  min-width: 1180px;
  min-height: 680px;
  grid-template-rows: 74px minmax(0, 1fr) 96px;
  overflow: hidden;
  color: var(--ink);
  background: radial-gradient(circle at 68% 18%,rgba(15,113,134,.18),transparent 32%),linear-gradient(145deg,#040a12,#071824 52%,#040c15);
  font-family: Inter,"PingFang SC","Microsoft YaHei",sans-serif;
}
.grid-field { position: absolute; inset: 0; opacity: .12; pointer-events: none; background-image: linear-gradient(rgba(79,200,219,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(79,200,219,.07) 1px,transparent 1px); background-size: 48px 48px; mask-image: linear-gradient(to bottom,transparent,#000 13%,#000 88%,transparent); }
.screen-aura { position: absolute; border-radius: 50%; pointer-events: none; filter: blur(100px); }
.aura-one { top: -300px; left: 42%; width: 780px; height: 440px; background: rgba(24,156,177,.2); }
.aura-two { right: 0; bottom: 10%; width: 260px; height: 480px; background: rgba(25,94,133,.12); }
button { font: inherit; } button:focus-visible { outline: 3px solid rgba(88,241,233,.3); outline-offset: 2px; }

.center-header { position: relative; z-index: 10; display: grid; align-items: center; gap: 24px; padding: 9px 26px; background: linear-gradient(180deg,rgba(3,11,19,.98),rgba(4,18,30,.74)); grid-template-columns: minmax(390px,1fr) auto minmax(430px,1fr); }
.center-brand,.header-actions,.system-status,.view-switch,.session-status { display: flex; align-items: center; }
.center-brand { gap: 12px; }.brand-mark { display: grid; width: 46px; height: 46px; flex: none; place-items: center; border: 1px solid rgba(76,239,234,.28); border-radius: 13px; background: rgba(21,118,145,.16); }.brand-mark svg { width: 32px; fill: none; stroke: var(--cyan-soft); stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; }.center-brand div { display: grid; gap: 2px; }.center-brand div span { color: #63c4cb; font-size: 10px; font-weight: 750; letter-spacing: .1em; }.center-brand h1 { margin: 0; font-size: clamp(20px,1.42vw,27px); letter-spacing: .05em; }
.session-status { gap: 9px; color: #7999a2; font-size: 11px; }.session-status > i { width: 7px; height: 7px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 12px rgba(81,224,215,.7); }.session-status strong { color: #d9f4f3; font-size: 13px; }.session-status em { margin-left: 5px; padding: 3px 8px; border-radius: 999px; background: rgba(214,157,69,.1); color: #dcbb80; font-size: 9px; font-style: normal; }
.header-actions { justify-content: flex-end; gap: 14px; white-space: nowrap; }.system-status { gap: 8px; color: #7caeb2; font-size: 11px; }.system-status i { width: 7px; height: 7px; border-radius: 50%; background: #4ae39b; box-shadow: 0 0 12px rgba(74,227,155,.55); }.update-time { color: #58747d; font-size: 10px; }.view-switch { gap: 7px; padding: 8px 11px; border: 1px solid rgba(92,218,226,.2); border-radius: 7px; background: rgba(16,78,101,.16); color: #b5dcde; cursor: pointer; }.view-switch svg { width: 15px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-width: 1.7; }

.workbench { position: relative; z-index: 2; display: grid; min-height: 0; grid-template-columns: minmax(0,1fr); overflow: hidden; }

.goal-workspace { display: grid; min-width: 0; min-height: 0; padding: 0 26px 14px 28px; grid-template-rows: 90px minmax(0,1fr); }
.objective-bar { display: flex; align-items: center; justify-content: space-between; gap: 30px; }.objective-bar > div { min-width: 0; }.objective-kicker { display: flex; align-items: center; gap: 7px; color: #56ced0; font-size: 9px; font-weight: 800; letter-spacing: .12em; }.objective-kicker i { width: 6px; height: 6px; border-radius: 50%; background: var(--cyan); }.objective-bar h2 { margin: 7px 0 0; overflow: hidden; font-size: clamp(20px,1.55vw,30px); letter-spacing: .01em; text-overflow: ellipsis; white-space: nowrap; }.workspace-state { display: grid; flex: none; gap: 3px; padding-left: 16px; border-left: 1px solid rgba(83,177,187,.17); }.workspace-state small { color: #54747d; font-size: 8px; }.workspace-state strong { color: #e4bb78; font-size: 11px; }
.workspace-canvas { min-height: 0; overflow: hidden; }

.workspace-ambient .workbench { grid-template-columns: minmax(0,1fr); }
.workspace-ambient .goal-workspace { padding: 12px 30px 18px; grid-template-rows: minmax(0,1fr); }
.workspace-ambient .objective-bar { display: none; }
.ambient-canvas { display: grid; min-height: 0; gap: 26px; grid-template-columns: minmax(0,1fr) 420px; }
.overview-map-stage { position: relative; display: grid; min-height: 0; padding: 5px 8px 0; background: radial-gradient(circle at 50% 48%,rgba(17,113,133,.12),transparent 60%); grid-template-rows: 54px minmax(0,1fr); }
.overview-map-stage > header { display: flex; align-items: flex-start; justify-content: space-between; padding: 0 5px; }.overview-map-stage > header div { display: grid; gap: 3px; }.overview-map-stage > header span,.overview-events > header span { color: #4fcbd0; font-size: 9px; font-weight: 800; letter-spacing: .12em; }.overview-map-stage > header h2 { margin: 0; font-size: clamp(20px,1.4vw,27px); }.overview-map-stage > header em { display: flex; align-items: center; gap: 7px; color: #74bba9; font-size: 10px; font-style: normal; }.overview-map-stage > header em i { width: 6px; height: 6px; border-radius: 50%; background: #53d99f; box-shadow: 0 0 9px rgba(83,217,159,.55); }.overview-map-stage .situation-map { width: 100%; height: 100%; }.overview-map-note { position: absolute; right: 10px; bottom: 5px; color: #4e747c; font-size: 8px; }
.overview-events { display: grid; min-height: 0; padding: 6px 0 16px; grid-template-rows: 52px minmax(0,1fr); }.overview-events > header { display: flex; align-items: center; justify-content: space-between; padding: 0 5px 10px; border-bottom: 1px solid rgba(79,169,180,.12); }.overview-events > header div { display: flex; align-items: baseline; gap: 8px; }.overview-events > header strong { color: #e8fafa; font-size: 24px; }.overview-events > header small { color: #617d84; font-size: 8px; }.overview-event-list { display: grid; min-height: 0; gap: 16px; align-content: center; }.overview-event-list button { position: relative; display: grid; min-height: 210px; align-content: start; gap: 7px; padding: 24px 24px 21px; overflow: hidden; border: 1px solid rgba(76,164,176,.13); border-radius: 8px; background: linear-gradient(120deg,rgba(9,52,67,.56),rgba(6,31,44,.18)); color: inherit; cursor: pointer; text-align: left; transition: .24s ease; }.overview-event-list button:hover,.overview-event-list button.spotlight { transform: translateX(-5px); border-color: rgba(255,137,83,.34); background: linear-gradient(120deg,rgba(86,43,29,.36),rgba(7,39,51,.36)); }.event-state { display: flex; align-items: center; gap: 7px; margin-bottom: 14px; color: #dca666; font-size: 9px; }.event-state i { width: 7px; height: 7px; border-radius: 50%; background: #e6ad5b; }.event-state.danger { color: #f4a074; }.event-state.danger i { background: #ff775b; box-shadow: 0 0 9px rgba(255,119,91,.55); }.overview-event-list button > strong { font-size: clamp(20px,1.28vw,25px); }.overview-event-list button > p { margin: 0; color: #b2c9cc; font-size: 13px; }.overview-event-list button > small { color: #67858d; font-size: 10px; }.overview-event-list button > em { position: absolute; right: 22px; bottom: 20px; color: #57c7c7; font-size: 9px; font-style: normal; }.overview-event-list button > em b { margin-left: 5px; font-size: 12px; }

.investigation-canvas { display: grid; min-height: 0; gap: 26px; grid-template-columns: minmax(0,1fr) 310px; }.investigation-board { min-width: 0; min-height: 0; overflow: hidden; }.canvas-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 0 0 12px; border-bottom: 1px solid rgba(82,175,187,.12); }.canvas-heading h3 { margin: 6px 0 0; font-size: clamp(17px,1.25vw,24px); }.fact-tags { display: flex; gap: 6px; }.fact-tags span,.fact-tags em { padding: 4px 7px; background: rgba(24,83,95,.14); color: #739098; font-size: 8px; font-style: normal; }.fact-tags em { color: #f0aa70; }
.evidence-flow { position: relative; display: grid; min-height: 0; gap: 9px; padding: 13px 8px 0 18px; }.evidence-flow::before { position: absolute; top: 19px; bottom: 0; left: 3px; width: 1px; background: linear-gradient(#4bc8c8,rgba(75,200,200,.08)); content: ''; }.incident-anchor,.generated-layer { position: relative; }.incident-anchor::before,.generated-layer::before { position: absolute; top: 7px; left: -18px; width: 7px; height: 7px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 8px rgba(81,224,215,.6); content: ''; }.incident-anchor { display: grid; align-items: center; gap: 12px; padding: 4px 0; grid-template-columns: 104px minmax(0,1fr) 190px; }.flow-step { color: #4bc8ca; font-size: 8px; font-weight: 800; letter-spacing: .1em; }.incident-copy { display: grid; gap: 3px; }.incident-copy strong { font-size: 14px; }.incident-copy small { color: #68858d; font-size: 9px; }.incident-anchor figure { display: grid; margin: 0; gap: 2px; grid-template-columns: 64px 1fr; }.incident-anchor img,.station-placeholder { width: 64px; height: 38px; object-fit: cover; }.station-placeholder { display: grid; place-items: center; background: #0a2b3b; color: #67828a; font-size: 7px; }.incident-anchor figcaption { align-self: center; color: #65848c; font-size: 8px; line-height: 1.4; }
.evidence-branches { display: grid; gap: 7px; padding: 8px 0 5px 104px; grid-template-columns: repeat(3,1fr); }.evidence-branches article { display: grid; align-items: center; gap: 7px; padding: 8px 9px; background: linear-gradient(90deg,rgba(10,63,77,.28),transparent); grid-template-columns: 21px minmax(0,1fr) auto; }.evidence-branches article > i { color: #42777f; font-size: 11px; font-style: normal; font-weight: 800; }.evidence-branches article > span { display: grid; gap: 2px; }.evidence-branches strong { font-size: 10px; }.evidence-branches small { overflow: hidden; color: #647f87; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }.evidence-branches em { color: #5bcfb8; font-size: 7px; font-style: normal; }.evidence-branches .missing em { color: #dda65e; }
.generated-layer { padding: 8px 0 0 104px; }.generated-layer > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }.generated-layer > header small { color: #607b83; font-size: 8px; }.hypothesis-list { display: grid; gap: 7px; grid-template-columns: repeat(3,1fr); }.hypothesis-list article { position: relative; display: grid; gap: 3px; min-width: 0; padding: 8px 10px 11px; overflow: hidden; background: linear-gradient(120deg,rgba(11,58,72,.3),transparent); }.hypothesis-list article > span { color: #6f8d94; font-size: 7px; }.hypothesis-list article > strong { font-size: 10px; }.hypothesis-list article > small { overflow: hidden; color: #607b83; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }.hypothesis-list article > i { position: absolute; right: 0; bottom: 0; left: 0; height: 2px; background: rgba(57,106,115,.16); }.hypothesis-list article > i::before { display: block; width: var(--confidence); height: 100%; background: #4e8790; content: ''; }.hypothesis-list article.leading { background: linear-gradient(120deg,rgba(13,104,111,.3),transparent); }.hypothesis-list article.leading > span { color: #61d4bd; }.hypothesis-list article.leading > i::before { background: var(--cyan); }
.responder-list { display: grid; gap: 8px; grid-template-columns: repeat(2,1fr); }.responder-list article { display: grid; align-items: center; gap: 8px; padding: 7px 9px; background: linear-gradient(90deg,rgba(8,52,66,.26),transparent); grid-template-columns: 28px minmax(0,1fr) auto; }.responder-list article.recommended { background: linear-gradient(90deg,rgba(11,92,94,.28),transparent); }.avatar { display: grid; width: 27px; height: 27px; place-items: center; border-radius: 50%; background: rgba(48,151,157,.18); color: #76ded5; font-size: 10px; }.responder-list div { display: grid; gap: 1px; }.responder-list em { color: #4fc9c4; font-size: 7px; font-style: normal; }.responder-list strong { font-size: 10px; }.responder-list small { overflow: hidden; color: #637e86; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }.responder-list b { color: #6ccfb6; font-size: 7px; font-weight: 500; }
.handoff-layer > div { display: grid; align-items: center; gap: 9px; padding: 8px 10px; background: linear-gradient(90deg,rgba(19,104,78,.22),transparent); grid-template-columns: 26px minmax(0,1fr) auto; }.handoff-layer > div > i { display: grid; width: 24px; height: 24px; place-items: center; border-radius: 50%; background: rgba(62,203,150,.12); color: #62dcae; font-style: normal; }.handoff-layer > div > span { display: grid; gap: 2px; }.handoff-layer strong { font-size: 10px; }.handoff-layer small { color: #63847f; font-size: 8px; }.handoff-layer em { color: #d7ad6c; font-size: 8px; font-style: normal; }
.reasoning-thread { min-height: 0; padding: 8px 0 0 2px; background: linear-gradient(90deg,rgba(8,43,56,.22),transparent); }.reasoning-thread > header { display: grid; gap: 3px; padding: 0 14px 9px; }.reasoning-thread > header span { color: #4ecacd; font-size: 8px; font-weight: 800; letter-spacing: .1em; }.reasoning-thread > header strong { font-size: 14px; }.reasoning-thread ol { display: grid; gap: 0; margin: 0; padding: 0 13px; list-style: none; }.reasoning-thread li { position: relative; display: grid; gap: 9px; min-height: 80px; padding: 7px 0; grid-template-columns: 25px 1fr; opacity: .35; }.reasoning-thread li::after { position: absolute; top: 32px; bottom: -5px; left: 12px; width: 1px; background: rgba(72,161,171,.18); content: ''; }.reasoning-thread li:last-child::after { display: none; }.reasoning-thread li > i { display: grid; width: 24px; height: 24px; place-items: center; border: 1px solid rgba(78,165,175,.2); border-radius: 50%; color: #6d8a92; font-size: 8px; font-style: normal; }.reasoning-thread li.complete,.reasoning-thread li.current { opacity: 1; }.reasoning-thread li.complete > i { border-color: rgba(75,217,191,.3); background: rgba(45,162,133,.12); color: #62d7b1; }.reasoning-thread li > div { display: grid; align-content: start; gap: 2px; }.reasoning-thread li small { color: #52747c; font-size: 7px; }.reasoning-thread li strong { font-size: 10px; }.reasoning-thread li p { margin: 2px 0 0; color: #68858d; font-size: 8px; line-height: 1.45; }.reasoning-thread li button { justify-self: start; margin-top: 4px; padding: 4px 7px; border: 0; background: rgba(28,104,114,.18); color: #67c9c8; cursor: pointer; font-size: 8px; }.reasoning-boundary { margin: 4px 13px 0; padding: 9px; background: linear-gradient(90deg,rgba(106,65,28,.13),transparent); color: #8e8b7d; font-size: 8px; line-height: 1.5; }.reasoning-boundary span { display: block; margin-bottom: 2px; color: #d5a460; font-weight: 700; }

/* Investigation content is presentation-scaled to use the full 1080p canvas. */
.investigation-canvas { gap: 30px; grid-template-columns: minmax(0,1fr) 330px; }
.investigation-board { display: grid; grid-template-rows: auto minmax(0,1fr); }
.canvas-heading { padding-bottom: 14px; }.canvas-heading h3 { font-size: clamp(19px,1.35vw,26px); }.fact-tags span,.fact-tags em { padding: 5px 8px; font-size: 9px; }
.evidence-flow { align-content: start; gap: 14px; padding-top: 20px; }.evidence-flow::before { top: 26px; }.incident-anchor::before,.generated-layer::before { top: 8px; width: 8px; height: 8px; }
.incident-anchor { gap: 14px; padding-block: 6px; grid-template-columns: 112px minmax(0,1fr) 220px; }.flow-step { font-size: 9px; }.incident-copy strong { font-size: 16px; }.incident-copy small { font-size: 10px; }.incident-anchor figure { gap: 5px; grid-template-columns: 82px 1fr; }.incident-anchor img,.station-placeholder { width: 82px; height: 48px; }.incident-anchor figcaption { font-size: 9px; }
.evidence-branches { gap: 9px; padding: 11px 0 7px 112px; }.evidence-branches article { gap: 9px; padding: 13px 11px; grid-template-columns: 23px minmax(0,1fr) auto; }.evidence-branches article > i { font-size: 13px; }.evidence-branches strong { font-size: 11px; }.evidence-branches small { font-size: 9px; }.evidence-branches em { font-size: 8px; }
.generated-layer { padding: 12px 0 0 112px; }.generated-layer > header { margin-bottom: 9px; }.generated-layer > header small { font-size: 9px; }.hypothesis-list { gap: 9px; }.hypothesis-list article { gap: 4px; padding: 13px 12px 17px; }.hypothesis-list article > span { font-size: 8px; }.hypothesis-list article > strong { font-size: 12px; }.hypothesis-list article > small { font-size: 9px; }.hypothesis-list article > i { height: 3px; }
.responder-list { gap: 10px; }.responder-list article { gap: 10px; padding: 11px 12px; grid-template-columns: 34px minmax(0,1fr) auto; }.avatar { width: 33px; height: 33px; font-size: 11px; }.responder-list div { gap: 2px; }.responder-list em { font-size: 8px; }.responder-list strong { font-size: 12px; }.responder-list small { font-size: 9px; }.responder-list b { font-size: 8px; }
.handoff-layer > div { gap: 11px; padding: 13px 12px; grid-template-columns: 32px minmax(0,1fr) auto; }.handoff-layer > div > i { width: 30px; height: 30px; }.handoff-layer > div > span { gap: 3px; }.handoff-layer strong { font-size: 12px; }.handoff-layer small,.handoff-layer em { font-size: 9px; }
.reasoning-thread li { gap: 10px; min-height: 105px; padding-block: 10px; grid-template-columns: 28px 1fr; }.reasoning-thread li > i { width: 27px; height: 27px; font-size: 9px; }.reasoning-thread li small { font-size: 8px; }.reasoning-thread li strong { font-size: 12px; }.reasoning-thread li p { margin-top: 3px; font-size: 9px; line-height: 1.5; }.reasoning-boundary { padding: 11px; font-size: 9px; }

.workspace-investigation .workbench { grid-template-columns: minmax(0,1fr); }
.workspace-investigation .goal-workspace { padding-inline: 24px; }
.investigation-canvas { display: grid; min-width: 0; min-height: 0; gap: 30px; grid-template-columns: minmax(720px,1.42fr) minmax(460px,.78fr); }
.workspace-interference .goal-workspace { padding-inline: 24px; }.interference-canvas { grid-template-columns: minmax(720px,1.3fr) minmax(500px,.82fr); }.interference-turn > div { padding: 6px 0 5px!important; border-left: 2px solid rgba(78,190,191,.2); background: transparent!important; }.interference-turn > div > p,.interference-turn > div > small { margin-left: 11px!important; }.interference-dispatch-plan { margin-top: 2px; }
.incident-panel { display: grid; min-width: 0; min-height: 0; align-content: start; padding: 4px 18px 0 2px; border-right: 1px solid rgba(76,169,179,.14); grid-template-rows: 36px auto auto 1fr; }
.incident-panel > header { display: flex; align-items: center; justify-content: space-between; color: #51cccf; font-size: 9px; font-weight: 800; letter-spacing: .12em; }
.incident-panel > header strong { color: #dff7f5; font-size: 18px; }
.incident-card { display: grid; width: 100%; align-content: start; gap: 7px; margin-top: 10px; padding: 17px 15px; border: 1px solid rgba(255,131,94,.28); border-radius: 8px; background: linear-gradient(135deg,rgba(101,43,29,.34),rgba(8,42,54,.38)); color: inherit; text-align: left; }
.incident-card > span { display: flex; align-items: center; gap: 7px; color: #f1a078; font-size: 8px; }.incident-card > span i { width: 6px; height: 6px; border-radius: 50%; background: #ff795f; box-shadow: 0 0 8px rgba(255,121,95,.56); }
.incident-card > strong { margin-top: 5px; font-size: 17px; }.incident-card > p { margin: 0; color: #afc8ca; font-size: 11px; }.incident-card > small { color: #66848b; font-size: 8px; }
.incident-panel dl { display: grid; gap: 0; margin: 16px 0 0; }.incident-panel dl > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 11px 3px; border-bottom: 1px solid rgba(77,150,161,.09); }.incident-panel dt { color: #5f7d84; font-size: 8px; }.incident-panel dd { margin: 0; color: #bdd2d3; font-size: 9px; }
.incident-panel > footer { display: flex; align-self: end; align-items: flex-start; gap: 8px; padding: 12px 3px; color: #927c62; font-size: 8px; line-height: 1.45; }.incident-panel > footer > i { width: 6px; height: 6px; margin-top: 3px; flex: none; border-radius: 50%; background: #d3a15f; }.incident-panel > footer small { color: #665f54; font-size: 7px; }
.conversation-evidence { display: grid; min-width: 0; min-height: 0; grid-template-rows: 64px minmax(0,1fr); }
.conversation-evidence > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 4px 10px 14px 2px; border-bottom: 1px solid rgba(75,164,175,.12); }.conversation-evidence > header > div { display: grid; gap: 5px; }.conversation-evidence > header span { color: #51cccf; font-size: 11px; font-weight: 800; letter-spacing: .1em; }.conversation-evidence > header strong { font-size: 21px; }.conversation-evidence > header em { color: #6f969b; font-size: 11px; font-style: normal; }
.conversation-history { display: grid; min-height: 0; align-content: start; gap: 10px; padding: 14px 10px 0 2px; overflow: hidden; }
.conversation-query { display: flex; align-items: center; justify-content: flex-end; gap: 9px; }.conversation-query span { color: #55757c; font-size: 10px; }.conversation-query p { max-width: 82%; margin: 0; padding: 8px 13px; border-radius: 8px 8px 2px 8px; background: rgba(28,97,110,.22); color: #bdd6d7; font-size: 11px; line-height: 1.4; }
.assistant-turn { display: grid; min-width: 0; gap: 11px; grid-template-columns: 32px minmax(0,1fr); }.turn-avatar { display: grid; width: 31px; height: 31px; place-items: center; border: 1px solid rgba(78,205,204,.24); border-radius: 8px; background: rgba(22,102,113,.16); color: #65d4d0; font-size: 9px; font-weight: 800; }.assistant-turn > div { min-width: 0; }.assistant-turn > div > p { margin: 0 0 8px; color: #9db8bb; font-size: 11px; line-height: 1.55; }.assistant-turn > div > p strong { color: #dbeeed; }
.assistant-turn > div > .dialogue-evidence { display: grid; gap: 3px; margin: 0 0 8px; color: #8da9ac; }.dialogue-evidence span { display: block; }.dialogue-evidence strong { color: #65d2cf; font-weight: 700; }
.evidence-snapshot { position: relative; width: min(480px,64%); height: 112px; margin: 0; overflow: hidden; }.evidence-snapshot img,.evidence-snapshot > div { width: 100%; height: 100%; object-fit: cover; opacity: .62; }.evidence-snapshot > div { display: grid; place-items: center; color: #68848a; font-size: 10px; }.evidence-snapshot figcaption { position: absolute; right: 0; bottom: 0; left: 0; padding: 7px 9px; background: linear-gradient(transparent,rgba(3,20,29,.9)); color: #c4d9d9; font-size: 10px; }
.evidence-chain { display: grid; min-width: 0; gap: 7px; grid-template-columns: 1.05fr .78fr 1fr; }.evidence-chain figure,.evidence-chain section { display: grid; min-width: 0; min-height: 74px; align-content: center; gap: 3px; margin: 0; padding: 8px; overflow: hidden; border-left: 2px solid rgba(74,201,202,.32); background: linear-gradient(110deg,rgba(9,62,75,.35),rgba(7,35,47,.12)); }.evidence-chain figure { position: relative; padding: 0; }.evidence-chain figure img,.evidence-chain figure > div { width: 100%; height: 74px; object-fit: cover; opacity: .62; }.evidence-chain figure > div { display: grid; place-items: center; color: #68848a; font-size: 8px; }.evidence-chain figcaption { position: absolute; right: 0; bottom: 0; left: 0; padding: 5px 7px; background: linear-gradient(transparent,rgba(3,20,29,.9)); color: #c4d9d9; font-size: 8px; }.evidence-chain section span { color: #4fc6c9; font-size: 7px; }.evidence-chain section strong { font-size: 13px; }.evidence-chain section small { color: #66838a; font-size: 8px; line-height: 1.4; }
.conversation-step { display: grid; min-width: 0; gap: 6px; }.assistant-turn.compact > div { padding: 9px 12px; background: linear-gradient(90deg,rgba(8,54,66,.26),transparent); }.assistant-turn.compact > div > p { margin: 0; }.answer-boundary { display: block; margin-top: 6px; color: #bd9764; font-size: 9px; }.person-suggestion { display: grid; align-items: center; gap: 7px; margin-top: 6px; padding: 7px 9px; background: rgba(12,76,76,.2); grid-template-columns: auto minmax(0,1fr) auto; }.person-suggestion strong { color: #d9eeeb; font-size: 10px; }.person-suggestion span { color: #69878b; font-size: 8px; }.person-suggestion em { color: #60d2b5; font-size: 7px; font-style: normal; }
.assistant-turn.plan-turn { align-items: start; }.dispatch-plan { display: grid; width: 100%; gap: 9px; padding: 15px 17px; border: 1px solid rgba(75,207,166,.16); border-radius: 7px; background: linear-gradient(120deg,rgba(15,89,70,.3),rgba(7,39,48,.16)); color: inherit; cursor: pointer; text-align: left; }.dispatch-plan:hover { border-color: rgba(75,207,166,.34); background: linear-gradient(120deg,rgba(18,105,81,.38),rgba(7,39,48,.2)); }.dispatch-plan header { display: flex; align-items: center; justify-content: space-between; }.dispatch-plan header span { color: #62d5b5; font-size: 10px; font-weight: 800; letter-spacing: .08em; }.dispatch-plan header em { color: #d8a761; font-size: 9px; font-style: normal; }.dispatch-plan > strong { font-size: 17px; }.dispatch-plan > p { margin: 0; color: #718f90; font-size: 10px; line-height: 1.5; }.plan-link { justify-self: start; color: #7ddbc3; font-size: 10px; }.plan-link i { margin-left: 5px; font-style: normal; }

.workspace-mobility .goal-workspace { padding-inline: 24px; }
.mobility-canvas { display: grid; min-width: 0; min-height: 0; gap: 30px; grid-template-columns: minmax(0,1.12fr) minmax(500px,.88fr); }
.dispatch-evidence { display: flex; min-width: 0; min-height: 0; flex-direction: column; padding-right: 6px; }
.dispatch-evidence > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; min-height: 64px; padding: 4px 2px 12px; border-bottom: 1px solid rgba(75,164,175,.12); }.dispatch-evidence > header > div { display: grid; gap: 5px; }.dispatch-evidence > header span { color: #51cccf; font-size: 11px; font-weight: 800; letter-spacing: .1em; }.dispatch-evidence > header strong { font-size: 21px; }.dispatch-evidence > header em { color: #806f62; font-size: 9px; font-style: normal; }
.dispatch-layer-switch { display: flex; gap: 18px; min-height: 40px; align-items: end; padding: 7px 2px 6px; }.dispatch-layer-switch button { position: relative; padding: 4px 0; border: 0; background: transparent; color: #66868e; cursor: pointer; font-size: 9px; }.dispatch-layer-switch button::after { position: absolute; right: 0; bottom: 0; left: 0; height: 1px; transform: scaleX(0); background: #55d7cf; content: ''; transition: .2s ease; }.dispatch-layer-switch button:hover,.dispatch-layer-switch button.active,.dispatch-layer-switch button:focus-visible { color: #bde9e6; }.dispatch-layer-switch button.active::after,.dispatch-layer-switch button:hover::after { transform: scaleX(1); }
.dispatch-map-frame { min-height: 0; flex: 1 1 0; background: radial-gradient(circle at 48% 48%,rgba(17,113,133,.1),transparent 62%); }.dispatch-map-frame .situation-map { width: 100%; height: 100%; }.dispatch-evidence > footer { display: flex; justify-content: space-between; gap: 12px; min-height: 30px; align-items: center; border-top: 1px solid rgba(75,164,175,.09); color: #52757d; font-size: 8px; }.dispatch-evidence > footer strong { color: #6f8c91; font-weight: 500; }
.dispatch-conversation { grid-template-rows: 64px minmax(0,1fr); }.dispatch-conversation .conversation-history { padding-right: 2px; }.dispatch-data-lines { gap: 7px!important; padding: 3px 0 7px; }.dispatch-data-lines span { padding: 0 0 6px 10px; border-left: 2px solid rgba(81,205,202,.28); }.dispatch-conclusion > div { padding: 5px 0 0!important; background: transparent!important; }.dispatch-result-lines { gap: 6px!important; margin-top: 10px!important; }.dispatch-result-lines span { padding-left: 10px; border-left: 2px solid rgba(84,205,170,.28); }.dispatch-optimization-plan { margin-top: 13px; }


.voice-console { position: relative; z-index: 10; display: grid; align-items: center; gap: 17px; padding: 10px 25px; background: linear-gradient(180deg,rgba(4,20,33,.76),rgba(3,12,21,.98)); grid-template-columns: 190px minmax(360px,1fr) auto 58px; }.assistant-identity { display: flex; align-items: center; gap: 10px; }.assistant-avatar { display: grid; width: 55px; height: 55px; overflow: hidden; place-items: center; border: 1px solid rgba(91,231,225,.28); border-radius: 50%; background: #f4fbfc; box-shadow: 0 0 0 5px rgba(45,202,210,.04); transition: .25s ease; }.assistant-avatar.active { transform: scale(1.06); box-shadow: 0 0 0 7px rgba(45,202,210,.06),0 0 22px rgba(57,227,231,.2); }.assistant-avatar img { width: 115%; height: 115%; object-fit: cover; }.assistant-identity > span:last-child { display: grid; gap: 2px; }.assistant-identity small { color: #5dc8cc; font-size: 9px; letter-spacing: .08em; }.assistant-identity strong { font-size: 15px; }.voice-content { min-width: 0; }.idle-content,.response-content,.thinking-content { display: grid; min-width: 0; gap: 4px; }.voice-content small { color: #55c7ca; font-size: 9px; font-weight: 700; letter-spacing: .08em; }.voice-content strong { overflow: hidden; color: #c9e1e3; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.response-content strong { color: #eefcfc; }.thinking-content { display: flex; align-items: center; gap: 12px; }.thinking-content > span:last-child { display: grid; gap: 3px; }.thinking-dots { display: flex; gap: 4px; }.thinking-dots i { width: 6px; height: 6px; border-radius: 50%; background: #4adbd4; animation: thinking 1s ease-in-out infinite; }.thinking-dots i:nth-child(2) { animation-delay: .15s; }.thinking-dots i:nth-child(3) { animation-delay: .3s; }.listening-content { display: flex; align-items: center; gap: 14px; }.voice-wave { display: flex; height: 32px; align-items: center; gap: 3px; }.voice-wave i { width: 2px; height: 12px; border-radius: 2px; background: #55e2da; animation: voice-wave .8s ease-in-out infinite alternate; }.voice-wave i:nth-child(3n) { height: 25px; animation-delay: .12s; }.voice-wave i:nth-child(4n) { height: 16px; animation-delay: .25s; }.listening-content strong { color: #efffff; }.voice-suggestions { display: flex; justify-content: flex-end; gap: 7px; }.voice-suggestions button { max-width: 230px; padding: 7px 10px; overflow: hidden; border: 1px solid rgba(76,174,187,.15); border-radius: 999px; background: rgba(24,77,92,.11); color: #779aa3; cursor: pointer; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.voice-suggestions button:hover { border-color: rgba(81,221,216,.3); color: #a8d8d8; }.microphone-button { display: grid; width: 52px; height: 52px; place-items: center; border: 1px solid rgba(79,226,219,.3); border-radius: 50%; background: linear-gradient(145deg,#0c7786,#09516e); color: #eaffff; cursor: pointer; box-shadow: 0 0 0 6px rgba(57,207,206,.04); }.microphone-button.listening { background: linear-gradient(145deg,#bd664b,#8b3d3d); box-shadow: 0 0 0 8px rgba(236,103,70,.08),0 0 22px rgba(235,94,69,.2); }.microphone-button svg { width: 24px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-width: 1.6; }

.workspace-shift-enter-active,.workspace-shift-leave-active { transition: .32s ease; }.workspace-shift-enter-from { transform: translateY(10px); opacity: 0; }.workspace-shift-leave-to { transform: translateY(-7px); opacity: 0; }.grow-panel-enter-active,.grow-panel-leave-active { transition: .4s ease; }.grow-panel-enter-from { transform: translateX(15px); opacity: 0; }.grow-panel-leave-to { opacity: 0; }
@keyframes thinking { 50% { transform: translateY(-4px); opacity: .55; } } @keyframes voice-wave { to { transform: scaleY(.4); opacity: .5; } }
@media (max-width: 1500px) { .center-header { grid-template-columns: minmax(350px,1fr) auto minmax(400px,1fr); }.investigation-canvas { gap: 20px; grid-template-columns: minmax(650px,1.35fr) minmax(380px,.75fr); }.interference-canvas { grid-template-columns: minmax(650px,1.22fr) minmax(430px,.78fr); }.mobility-canvas { gap: 22px; grid-template-columns: minmax(0,1fr) minmax(460px,.9fr); }.voice-suggestions button:nth-child(2) { display: none; }.ambient-canvas { gap: 18px; grid-template-columns: minmax(0,1fr) 370px; } }
@media (max-height: 820px) { .command-center { grid-template-rows: 68px minmax(0,1fr) 82px; }.goal-workspace { grid-template-rows: 72px minmax(0,1fr); padding-bottom: 8px; }.workspace-ambient .goal-workspace { padding-block: 8px; grid-template-rows: minmax(0,1fr); }.overview-event-list button { min-height: 170px; padding-block: 17px; }.conversation-history { gap: 4px; padding-top: 6px; }.conversation-query p { padding-block: 4px; }.evidence-snapshot { height: 58px; }.assistant-turn > div > p { font-size: 8px; }.dispatch-data-lines { gap: 3px!important; }.dispatch-data-lines span { padding-bottom: 3px; }.dispatch-optimization-plan { margin-top: 7px; }.dispatch-plan { gap: 5px; padding-block: 7px; }.assistant-avatar { width: 47px; height: 47px; }.voice-console { padding-block: 6px; } }
@media (prefers-reduced-motion: reduce) { *,*::before,*::after { animation-duration: .01ms!important; animation-iteration-count: 1!important; transition-duration: .01ms!important; } }
</style>
