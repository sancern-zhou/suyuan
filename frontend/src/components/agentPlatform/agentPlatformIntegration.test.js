import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const readSource = relativePath => readFile(new URL(relativePath, import.meta.url), 'utf8')

test('sidebar exposes the agent platform as a primary action', async () => {
  const source = await readSource('../AssistantSidebar.vue')

  assert.match(source, /agent-platform/)
  assert.match(source, /智能体平台/)
  assert.match(source, /<p class="module-title">新建任务<\/p>/)
  assert.match(source, /id: 'restart-session',[\s\S]*name: '新建任务'/)
  assert.doesNotMatch(source, /<span>智能体平台<\/span>/)
  assert.doesNotMatch(source, /agent-platform-btn|new-session-btn/)
  assert.doesNotMatch(source, /linear-gradient\(135deg/)
})

test('sidebar moves system management entries into the bottom user settings menu', async () => {
  const source = await readSource('../AssistantSidebar.vue')

  assert.match(source, /useAuthStore/)
  assert.match(source, /class="user-settings-footer"/)
  assert.match(source, /class="user-settings-menu"/)
  assert.match(source, /role="menu"/)
  assert.match(source, /:aria-expanded="settingsMenuOpen"/)
  assert.match(source, /userDisplayName/)
  assert.match(source, /settingsModules/)
  assert.match(source, /const SETTINGS_MODULE_IDS = Object\.freeze\(\[[\s\S]*'tools-management'[\s\S]*'skills-management'[\s\S]*'fetchers'[\s\S]*'social-platform'/)
  assert.match(source, /id: 'system',[\s\S]*ids: \['scheduled-tasks'\]/)
  assert.match(source, /document\.addEventListener\('pointerdown'/)
  assert.match(source, /event\.key === 'Escape'/)
  assert.match(source, /handleSettingsSelect/)
  assert.match(source, /settingsMenuOpen\.value = false/)
})

test('sidebar navigation omits work resource and system group labels', async () => {
  const source = await readSource('../AssistantSidebar.vue')

  assert.doesNotMatch(source, /module-group-title/)
  assert.doesNotMatch(source, /title: '(工作|资源|系统)'/)
})

test('main layout switches between agent platform and chat workspace', async () => {
  const source = await readSource('../reactAnalysis/MainLayout.vue')

  assert.match(source, /workspace === 'platform'/)
  assert.match(source, /<AgentPlatform/)
  assert.doesNotMatch(source, /AgentWorkspaceHeader/)
  assert.match(source, /:agent-mode="agentMode"/)
  assert.match(source, /select-agent/)
})

test('chat workspace passes the selected agent to the welcome area without changing query dashboard behavior', async () => {
  const chatArea = await readSource('../reactAnalysis/ChatArea.vue')
  const queryDashboard = await readSource('../queryDashboard/QueryDashboardWorkspace.vue')

  assert.match(chatArea, /agentMode:/)
  assert.match(chatArea, /:agent-mode="agentMode"/)
  assert.match(queryDashboard, /:hide-welcome="true"/)
})

test('analysis view defaults to the platform and opens chat through explicit flows', async () => {
  const source = await readSource('../../views/ReactAnalysisView.vue')

  assert.match(source, /const workspace = ref\('platform'\)/)
  assert.match(source, /resolveAgentSelection/)
  assert.match(source, /workspace\.value = 'chat'/)
  assert.match(source, /workspace\.value = 'platform'/)
  assert.match(source, /route\.params\.id/)
  assert.match(source, /watch\(\s*\(\) => route\.params\.id/)
  assert.match(source, /queueRouteSessionRestore/)
})

test('conversation workspace no longer exposes inline agent mode switching', async () => {
  const inputBox = await readSource('../InputBox.vue')
  const queryDashboard = await readSource('../queryDashboard/QueryDashboardWorkspace.vue')
  const chatArea = await readSource('../reactAnalysis/ChatArea.vue')
  const mainLayout = await readSource('../reactAnalysis/MainLayout.vue')
  const analysisView = await readSource('../../views/ReactAnalysisView.vue')

  for (const source of [inputBox, queryDashboard]) {
    assert.doesNotMatch(source, /AgentModeSelector/)
  }
  for (const source of [inputBox, queryDashboard, chatArea, mainLayout, analysisView]) {
    assert.doesNotMatch(source, /update:agentMode|update:agent-mode/)
  }
})
