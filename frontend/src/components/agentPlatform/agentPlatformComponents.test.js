import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const readComponent = name => readFile(new URL(`./${name}`, import.meta.url), 'utf8')

test('agent platform renders accessible cards and emits mode selection', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.match(source, /v-for="agent in agents"/)
  assert.match(source, /class="agent-grid"/)
  assert.match(source, /<button/)
  assert.match(source, /emit\('select', agent\.id\)/)
  assert.match(source, /运行中/)
  assert.match(source, /focus-visible/)
})

test('coordinator layout delegates to the controlled coordinator home', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.match(source, /<CoordinatorHome/)
  assert.match(source, /:coordinator="coordinator"/)
  assert.match(source, /@submit="emit\('submit', \$event\)"/)
})

test('coordinator layout switches between the personal home and voice-driven command center', async () => {
  const platform = await readComponent('AgentPlatform.vue')
  const home = await readComponent('../coordinator/CoordinatorHome.vue')
  const commandCenter = await readComponent('../coordinator/CoordinatorCommandCenter.vue')

  assert.match(platform, /coordinatorView === 'home'/)
  assert.match(platform, /<CoordinatorCommandCenter/)
  assert.match(platform, /coordinatorView = 'command-center'/)
  assert.match(platform, /coordinatorView = 'home'/)
  assert.match(home, /智能中枢/)
  assert.match(commandCenter, /空气站智能运维中枢/)
  assert.match(commandCenter, /返回\{\{ assistantName \}\}首页/)
  assert.match(commandCenter, /class="voice-console"/)
  assert.match(commandCenter, /toggleListening/)
  assert.match(commandCenter, /SpeechRecognition/)
  assert.match(commandCenter, /xiaozhiRobotUrl/)
  assert.match(commandCenter, /coordinator\.stationImageUrl/)
  assert.match(commandCenter, /关键监控截图/)
  assert.doesNotMatch(commandCenter, /class="command-dock"/)
  assert.doesNotMatch(commandCenter, /确认生成/)
})

test('command center is a viewport-filling, non-scrolling large-screen surface', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')

  assert.match(source, /position: fixed/)
  assert.match(source, /width: 100vw/)
  assert.match(source, /height: 100dvh/)
  assert.match(source, /overflow: hidden/)
  assert.match(source, /grid-template-rows: 74px minmax\(0, 1fr\) 96px/)
  assert.match(source, /class="workspace-canvas ambient-canvas"/)
  assert.match(source, /class="workspace-canvas investigation-canvas"/)
  assert.match(source, /class="workspace-canvas mobility-canvas"/)
  assert.match(source, /class="workspace-canvas investigation-canvas interference-canvas"/)
  assert.match(source, /@media \(max-height: 820px\)/)
})

test('command center uses an open workbench instead of a grid of dashboard cards', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')

  assert.match(source, /class="workbench"/)
  assert.match(source, /class="goal-workspace"/)
  assert.match(source, /class="conversation-evidence"/)
  assert.doesNotMatch(source, /class="context-rail"|持续态势底座|江苏全省 · 今日值守/)
  assert.doesNotMatch(source, /class="surface-card"/)
  assert.doesNotMatch(source, /class="status-ribbon"/)
})

test('duty overview is map-first with three concise scenario summaries and the AI entry', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')

  assert.match(source, /class="overview-map-stage"/)
  assert.match(source, /class="overview-events"/)
  assert.match(source, /class="overview-event-list"/)
  assert.match(source, /颗粒物数据中断/)
  assert.match(source, /智慧运维调度/)
  assert.match(source, /外部环境干扰识别/)
  assert.match(source, /跨市运维 · 轨迹洞察 · 高频到站 · 资源优化/)
  assert.match(source, /\.workspace-ambient \.workbench/)
  assert.match(source, /class="voice-console"/)
  assert.doesNotMatch(source, /class="ambient-question"|class="ambient-focus-list"/)
})

test('command center visible headings and units are consistently Chinese', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')
  const retiredLabels = [
    'OPERATION SITUATION', 'PRIORITY', 'FIELD EVIDENCE', 'DATA &amp; DIAGNOSIS',
    'TASK DRAFT', 'PERSONNEL', 'PROGRESS', 'PROVINCE SITUATION',
    'MOBILITY ANALYSIS', 'MANAGEMENT FOCUS', 'OPTIMIZATION'
  ]

  for (const label of retiredLabels) assert.doesNotMatch(source, new RegExp(`>${label}<`))
  assert.doesNotMatch(source, />\s*(?:km|min)\s*</)
  assert.match(source, /里程减少 1,260 公里/)
  assert.match(source, /响应时间缩短 18 分钟/)
})

test('command center separates display-level insight from homepage business execution', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')

  assert.match(source, /今日值守总览/)
  assert.match(source, /源创包装厂房站点异常连续调查工作区/)
  assert.match(source, /全省智慧运维调度连续分析工作区/)
  assert.match(source, /调度计划草案/)
  assert.match(source, /打开详细操作工作台/)
  assert.match(source, /等待人工确认/)
  assert.doesNotMatch(source, /调整方案|确认生成|设备反控/)
  assert.doesNotMatch(source, /emit\('submit'/)
})

test('particulate interruption enlarges conversation and visual evidence without a duplicate event rail', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')
  const visual = await readComponent('../coordinator/StationInterruptionEvidence.vue')

  assert.match(source, /class="conversation-evidence"/)
  assert.match(source, /class="conversation-history"/)
  assert.match(source, /class="dialogue-evidence"/)
  assert.match(source, /class="evidence-snapshot"/)
  assert.match(source, /<button class="dispatch-plan"/)
  assert.match(source, /<StationInterruptionEvidence/)
  assert.doesNotMatch(source, /class="incident-panel"|class="evidence-chain"|class="investigation-board"|class="evidence-flow"|class="reasoning-thread"|class="hypothesis-list"/)
  assert.match(visual, /from 'echarts\/core'/)
  assert.match(visual, /LineChart/)
  assert.match(visual, /markLine/)
  assert.match(visual, />数据<\/button>/)
  assert.match(visual, />视频<\/button>/)
})

test('smart dispatch uses map evidence and a continuous AI conversation instead of insight cards', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')

  assert.match(source, /class="dispatch-evidence"/)
  assert.match(source, /class="conversation-evidence dispatch-conversation"/)
  assert.match(source, /数据、截图和结论随追问持续补充/)
  assert.match(source, /class="dialogue-evidence dispatch-data-lines"/)
  assert.match(source, /class="dispatch-plan dispatch-optimization-plan"/)
  assert.match(source, /智慧调度优化方案草案/)
  assert.doesNotMatch(source, /class="dispatch-dimensions"|class="strategy-lab"|class="dispatch-recommendation"/)
})

test('external interference grows video, correlation, impact and evidence-package turns in one AI workspace', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')
  const evidence = await readComponent('../coordinator/ExternalInterferenceEvidence.vue')

  assert.match(source, /外部环境干扰识别连续分析工作区/)
  assert.match(source, /视频、数据和判断依据随追问持续补充/)
  assert.match(source, /告警初筛/)
  assert.match(source, /时空关联/)
  assert.match(source, /影响监测数据和代表性/)
  assert.match(source, /外部环境干扰处置草案/)
  assert.match(source, /<ExternalInterferenceEvidence/)
  assert.match(evidence, /喷淋雾炮/)
  assert.match(evidence, /车辆停靠/)
  assert.match(evidence, /人员靠近/)
  assert.match(evidence, /摄像头遮挡/)
  assert.match(evidence, /视频证据/)
  assert.match(evidence, /监测数据/)
  assert.match(evidence, /气象条件/)
  assert.match(evidence, /设备状态/)
  assert.match(evidence, /运维记录/)
  assert.match(evidence, /LineChart/)
})

test('command center map uses real Jiangsu boundaries and the original platform station directory snapshot', async () => {
  const mapSource = await readComponent('../coordinator/JiangsuSituationMap.vue')
  const stationSource = await readComponent('../coordinator/jiangsuOpsStations.js')
  const geoSource = await readComponent('../coordinator/jiangsu-320000.geo.json')

  assert.match(mapSource, /jiangsu-320000\.geo\.json/)
  assert.match(mapSource, /JIANGSU_OPS_STATIONS/)
  assert.match(mapSource, /echarts\.registerMap/)
  assert.match(mapSource, /JIANGSU_OPS_STATION_TOTAL/)
  assert.match(mapSource, /name: '跨市运维轨迹'/)
  assert.match(mapSource, /name: '运维单位轨迹'/)
  assert.match(mapSource, /name: '轨迹人员'/)
  assert.match(mapSource, /name: '频繁到站站点'/)
  assert.match(mapSource, /props\.activeLayer/)
  assert.match(stationSource, /"code":"1002A"/)
  assert.match(stationSource, /"name":"源创包装厂房"/)
  assert.match(stationSource, /"city":"南京市"/)
  assert.match(stationSource, /"lng":118\.693087/)
  assert.match(geoSource, /"adcode":320100,"name":"南京市"/)
  assert.match(geoSource, /"adcode":321300,"name":"宿迁市"/)
  assert.doesNotMatch(mapSource, /province-shape/)
})

test('command center grows persistent workspaces while retaining presenter fallbacks', async () => {
  const source = await readComponent('../coordinator/CoordinatorCommandCenter.vue')

  assert.match(source, /getCommandCenterWorkspace/)
  assert.match(source, /getCommandCenterRevealLevel/)
  assert.match(source, /workspaces\.AMBIENT/)
  assert.match(source, /workspaces\.INVESTIGATION/)
  assert.match(source, /workspaces\.MOBILITY/)
  assert.match(source, /workspaces\.INTERFERENCE/)
  assert.match(source, /证据随追问持续补充/)
  assert.match(source, /数据、截图和结论随追问持续补充/)
  assert.match(source, /跨市运维/)
  assert.match(source, /运维单位轨迹/)
  assert.match(source, /运维人员轨迹/)
  assert.match(source, /频繁到站站点/)
  assert.doesNotMatch(source, /管理简报|本周工单审核|generated-brief/)
  assert.match(source, /class="voice-suggestions"/)
  assert.match(source, /event\.key === 'ArrowRight'/)
  assert.match(source, /event\.key === 'ArrowLeft'/)
})

test('coordinator home fills the available flex workspace', async () => {
  const source = await readComponent('../coordinator/CoordinatorHome.vue')

  assert.match(source, /\.coordinator-home \{[^}]*width: 100%/)
  assert.match(source, /\.coordinator-home \{[^}]*min-width: 0/)
  assert.match(source, /\.coordinator-home \{[^}]*flex: 1 1 0%/)
})

test('agent platform presents the real agent catalog as a portal grid', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.match(source, /class="terrain-lines"/)
  assert.match(source, /平台运行中/)
  assert.match(source, /\{\{ agents\.length \}\}/)
  assert.match(source, /grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/)
  assert.match(source, /--lake-900: #07293b/)
  assert.match(source, /--teal-500: #14a0ae/)
  assert.match(source, /@media \(max-width: 820px\)/)
})

test('agent platform renders visible scheduled task entries and emits selection', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.match(source, /scheduledTasks:/)
  assert.match(source, /class="scheduled-task-grid"/)
  assert.match(source, /v-for="task in scheduledTasks"/)
  assert.match(source, /task\.workspace_entry\?\.title \|\| task\.name/)
  assert.match(source, /emit\('select-task', task\)/)
  assert.match(source, /暂无显示在工作区的定时任务/)
})

test('agent cards use clean surfaces without decorative side bars', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.doesNotMatch(source, /&::before/)
  assert.doesNotMatch(source, /inset: 0 auto 0 0/)
  assert.match(source, /class="agent-icon"/)
  assert.match(source, /agent\.iconPaths/)
})

test('scheduled tasks use a distinct two-column featured-card treatment', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.match(source, /\.scheduled-task-grid \{[\s\S]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
  assert.match(source, /\.scheduled-task-card \{[\s\S]*linear-gradient\(120deg, var\(--lake-900\)/)
  assert.match(source, /class="task-ambient"/)
  assert.match(source, /class="task-badge"/)
})

test('scheduled tasks appear before the agent catalog', async () => {
  const source = await readComponent('AgentPlatform.vue')
  const taskPortalIndex = source.indexOf('class="portal-section task-portal"')
  const agentPortalIndex = source.indexOf('class="agent-groups"')

  assert.ok(taskPortalIndex >= 0)
  assert.ok(agentPortalIndex >= 0)
  assert.ok(taskPortalIndex < agentPortalIndex)
})

test('scene headings are primary sections without a nested container surface', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.doesNotMatch(source, /智能体入口/)
  assert.doesNotMatch(source, /基于当前项目配置提供的真实专业能力/)
  assert.match(source, /<h2 :id="`scene-\$\{scene\.id\}`">\{\{ scene\.name \}\}<\/h2>/)
  assert.doesNotMatch(source, /\.scene-section \{[^}]*border/)
  assert.doesNotMatch(source, /\.scene-section \{[^}]*background/)
  assert.doesNotMatch(source, /\.scene-section \{[^}]*padding/)
})

test('empty chat resolves complete welcome copy from the selected agent catalog entry', async () => {
  const source = await readComponent('../ReActMessageList.vue')

  assert.match(source, /getAgentMode/)
  assert.match(source, /agentMode/)
  assert.match(source, /agent\.welcome/)
  assert.doesNotMatch(source, /大气环境智能分析与决策支持平台/)
})

test('welcome capabilities render as centered plain text instead of styled buttons', async () => {
  const source = await readComponent('../ReActMessageList.vue')

  assert.match(source, /<ul class="welcome-capabilities">/)
  assert.match(source, /<li[\s\S]*class="welcome-capability"/)
  assert.doesNotMatch(source, /<button[\s\S]*class="welcome-capability"/)
  assert.match(source, /\.welcome-capabilities[\s\S]*align-items: center/)
  assert.match(source, /\.welcome-capability[\s\S]*text-align: center/)
})
