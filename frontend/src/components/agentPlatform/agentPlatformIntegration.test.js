import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const readSource = relativePath => readFile(new URL(relativePath, import.meta.url), 'utf8')

test('sidebar exposes the agent platform as a primary action', async () => {
  const source = await readSource('../AssistantSidebar.vue')

  assert.match(source, /agent-platform/)
  assert.match(source, /智能体平台/)
  assert.match(source, /<p class="module-title">新建对话<\/p>/)
  assert.match(source, /id: 'restart-session',[\s\S]*name: '新建对话'/)
  assert.doesNotMatch(source, /<span>智能体平台<\/span>/)
  assert.doesNotMatch(source, /agent-platform-btn|new-session-btn/)
  assert.doesNotMatch(source, /linear-gradient\(135deg/)
})

test('sidebar exposes smart query and opens the AI query agent workspace', async () => {
  const sidebar = await readSource('../AssistantSidebar.vue')
  const analysisView = await readSource('../../views/ReactAnalysisView.vue')

  assert.match(sidebar, /<p class="module-title">智能问数<\/p>/)
  assert.match(sidebar, /handleModuleSelect\('query-dashboard'\)/)
  assert.match(sidebar, /id: 'query-dashboard',[\s\S]*name: '智能问数'/)
  assert.match(analysisView, /case 'query-dashboard':[\s\S]*store\.switchMode\('query'\)/)
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
  assert.match(source, /const SETTINGS_MODULE_IDS = Object\.freeze\(\[[\s\S]*'session-history'[\s\S]*'skills-management'[\s\S]*'scheduled-tasks'[\s\S]*'tools-management'[\s\S]*'file-manager'[\s\S]*'fetchers'[\s\S]*'social-platform'/)
  assert.doesNotMatch(source.match(/const SETTINGS_MODULE_IDS = Object\.freeze\(\[([\s\S]*?)\]\)/)?.[1] || '', /'knowledge-base'/)
  assert.match(source, /document\.addEventListener\('pointerdown'/)
  assert.match(source, /event\.key === 'Escape'/)
  assert.match(source, /handleSettingsSelect/)
  assert.match(source, /settingsMenuOpen\.value = false/)
})

test('data, scheduled task and social management settings open their connected panels', async () => {
  const analysisView = await readSource('../../views/ReactAnalysisView.vue')

  assert.match(analysisView, /case 'fetchers':[\s\S]*showManagementPanel\('fetchers'\)[\s\S]*refreshFetcherStatus/)
  assert.match(analysisView, /case 'scheduled-tasks':[\s\S]*showManagementPanel\('scheduled-tasks'\)[\s\S]*refreshScheduledTasks/)
  assert.match(analysisView, /case 'social-platform':[\s\S]*showManagementPanel\('social-platform'\)/)
})

test('agent platform supports project-selected scene and environment grid layouts', async () => {
  const source = await readSource('./AgentPlatform.vue')

  assert.match(source, /projectConfig\.agentModeIds/)
  assert.match(source, /projectConfig\.agentPlatformLayout/)
  assert.match(source, /class="scene-stack"/)
  assert.match(source, /class="agent-grid"/)
})

test('sidebar navigation omits work resource and system group labels', async () => {
  const source = await readSource('../AssistantSidebar.vue')

  assert.doesNotMatch(source, /module-group-title/)
  assert.doesNotMatch(source, /title: '(工作|资源|系统)'/)
})

test('primary sidebar navigation sits outside the independently scrolling recent sessions area', async () => {
  const source = await readSource('../AssistantSidebar.vue')
  const moduleListIndex = source.indexOf('<div class="module-list">')
  const scrollAreaIndex = source.indexOf('<div class="sidebar-scroll-area">')
  const recentSessionsIndex = source.indexOf('class="recent-sessions-section"')

  assert.ok(moduleListIndex >= 0)
  assert.ok(scrollAreaIndex >= 0)
  assert.ok(recentSessionsIndex >= 0)
  assert.ok(moduleListIndex < scrollAreaIndex)
  assert.ok(scrollAreaIndex < recentSessionsIndex)
  assert.match(source, /\.module-list \{[\s\S]*flex: 0 0 auto/)
})

test('recent conversations expose separate case-library and IM conversation views', async () => {
  const source = await readSource('../AssistantSidebar.vue')

  assert.match(source, /CONVERSATION_LIST_VIEW/)
  assert.match(source, /toggleConversationView\(CONVERSATION_LIST_VIEW\.CASES\)/)
  assert.match(source, /toggleConversationView\(CONVERSATION_LIST_VIEW\.IM\)/)
  assert.match(source, /title="查看IM对话"/)
  assert.match(source, /\[CONVERSATION_LIST_VIEW\.IM\]: 'IM对话'/)
})

test('session history applies the shared scheduled-conversation exclusion policy', async () => {
  const source = await readSource('../../composables/reactAnalysis/useSessionManagement.js')
  const legacyManager = await readSource('../SessionManager.vue')

  assert.match(source, /filterConversationHistory/)
  assert.match(source, /return filterConversationHistory\(Array\.from\(byId\.values\(\)\)\)/)
  assert.match(legacyManager, /filterConversationHistory/)
  assert.match(legacyManager, /sessions\.value = filterConversationHistory\(response\.sessions \|\| \[\]\)/)
  assert.match(legacyManager, /reconcileConversationHistoryStats\(data, sessions\.value\)/)
})

test('session restore does not replace the current chat with an empty persisted transcript', async () => {
  const source = await readSource('../../composables/reactAnalysis/useSessionManagement.js')

  const guardIndex = source.indexOf("throw new Error('该历史会话没有可恢复的消息")
  const resetIndex = source.indexOf('store.reset()', guardIndex)
  assert.ok(guardIndex >= 0)
  assert.ok(resetIndex > guardIndex)
  assert.match(source, /if \(hasRestorableLocalState\(store\.sessionStates\?\.\[sessionId\]\)\)/)
  assert.match(source, /if \(!hasRestorableLocalState\(localSessionState\)\) return false/)
})

test('primary sidebar actions share one uniform spacing system', async () => {
  const source = await readSource('../AssistantSidebar.vue')

  assert.match(source, /<div class="primary-navigation">/)
  assert.match(source, /\.primary-navigation \{[\s\S]*gap: 4px/)
  assert.match(source, /\.new-session-section \{[\s\S]*padding-bottom: 0;[\s\S]*margin-bottom: 0;[\s\S]*gap: 4px/)
  assert.match(source, /\.module-list \{[\s\S]*gap: 4px/)
  assert.match(source, /\.module-group \{[\s\S]*gap: 4px/)
})

test('knowledge management is primary while remaining management entries live in user settings', async () => {
  const source = await readSource('../AssistantSidebar.vue')
  const settingsIds = source.match(/const SETTINGS_MODULE_IDS = Object\.freeze\(\[([\s\S]*?)\]\)/)?.[1] || ''
  const primaryNavigation = source.slice(
    source.indexOf('<div class="primary-navigation">'),
    source.indexOf('<div class="sidebar-scroll-area">')
  )

  for (const moduleId of [
    'session-history',
    'skills-management',
    'scheduled-tasks',
    'file-manager'
  ]) {
    assert.match(settingsIds, new RegExp(`'${moduleId}'`))
  }
  assert.doesNotMatch(settingsIds, /'knowledge-base'/)
  assert.match(primaryNavigation, /handleModuleSelect\('knowledge-base'\)/)
  assert.match(primaryNavigation, /<p class="module-title">知识管理<\/p>/)
})

test('main layout switches between agent platform and chat workspace', async () => {
  const source = await readSource('../reactAnalysis/MainLayout.vue')

  assert.match(source, /workspace === 'platform'/)
  assert.match(source, /<AgentPlatform/)
  assert.match(source, /:scheduled-tasks="taskWorkspaceEntries"/)
  assert.match(source, /@select-task="handleTaskWorkspaceSelect"/)
  assert.match(source, /emit\('sidebar-action', \{ type: 'task-workspace', taskId: task\.task_id \}\)/)
  assert.doesNotMatch(source, /AgentWorkspaceHeader/)
  assert.match(source, /:agent-mode="agentMode"/)
  assert.match(source, /select-agent/)
})

test('chat workspace passes the selected agent to the welcome area for every agent mode', async () => {
  const chatArea = await readSource('../reactAnalysis/ChatArea.vue')
  const mainLayout = await readSource('../reactAnalysis/MainLayout.vue')

  assert.match(chatArea, /agentMode:/)
  assert.match(chatArea, /:agent-mode="agentMode"/)
  assert.doesNotMatch(mainLayout, /QueryDashboardWorkspace/)
  assert.doesNotMatch(mainLayout, /agentMode === 'query'/)
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

test('new task applies the isolated query-default feature and otherwise preserves assistant behavior', async () => {
  const source = await readSource('../../views/ReactAnalysisView.vue')

  assert.doesNotMatch(source, /请先选择一个智能体/)
  assert.match(source, /projectConfig\.hasFeature\('query_agent_as_default'\) \? 'query' : 'assistant'/)
  assert.match(source, /: store\.currentMode/)
  assert.match(source, /if \(newTaskMode !== store\.currentMode\) store\.switchMode\(newTaskMode\)/)
  assert.match(source, /store\.restart\(\)/)
})

test('conversation workspace no longer exposes inline agent mode switching', async () => {
  const inputBox = await readSource('../InputBox.vue')
  const chatArea = await readSource('../reactAnalysis/ChatArea.vue')
  const mainLayout = await readSource('../reactAnalysis/MainLayout.vue')
  const analysisView = await readSource('../../views/ReactAnalysisView.vue')

  for (const source of [inputBox, chatArea, mainLayout, analysisView]) {
    assert.doesNotMatch(source, /AgentModeSelector/)
  }
  for (const source of [inputBox, chatArea, mainLayout, analysisView]) {
    assert.doesNotMatch(source, /update:agentMode|update:agent-mode/)
  }
})
