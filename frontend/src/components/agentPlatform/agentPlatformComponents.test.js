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

test('coordinator layout switches between the existing home and command center prototype', async () => {
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
  assert.match(commandCenter, /class="command-dock"/)
  assert.match(commandCenter, /xiaozhiRobotUrl/)
  assert.match(commandCenter, /assistantName.*智能值班助手形象/)
  assert.match(commandCenter, /coordinator\.stationImageUrl/)
  assert.match(commandCenter, /现场画面/)
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
