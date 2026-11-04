import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readSource = relativePath => readFile(new URL(relativePath, import.meta.url), 'utf8')

test('coordinator home removes the fixed conversation card and keeps its catalog', async () => {
  const source = await readSource('../coordinator/CoordinatorHome.vue')

  assert.doesNotMatch(source, /class="assistant-conversation"/)
  assert.doesNotMatch(source, /aria-label="输入助手任务"/)
  assert.doesNotMatch(source, /emit\('submit'/)
  assert.match(source, /aria-label="智能体类型"/)
})

test('floating assistant uses the real conversation state on every coordinator workspace', async () => {
  const layout = await readSource('../reactAnalysis/MainLayout.vue')
  const dock = await readSource('../coordinator/CoordinatorAssistantDock.vue')
  const view = await readSource('../../views/ReactAnalysisView.vue')

  assert.match(layout, /<CoordinatorAssistantDock/)
  assert.match(layout, /:messages="messages"/)
  assert.match(layout, /@submit="\$emit\('coordinator-submit', \$event\)"/)
  assert.match(dock, /<ReActMessageList/)
  assert.match(dock, /<InputBox/)
  assert.match(dock, /position: fixed/)
  assert.match(view, /handleFloatingAssistantSubmit/)
  assert.match(view, /store\.enterModeConversation\(mode\)/)
  assert.match(view, /handleSend\(\{ query, agentMode: mode \}\)/)
})

test('assistant sends can route through project coordinator rules', async () => {
  const source = await readFile(new URL('../../composables/reactAnalysis/useSessionManagement.js', import.meta.url), 'utf8')

  assert.match(source, /resolveCoordinatorMode\(/)
  assert.match(source, /agentMode === 'assistant'/)
  assert.match(source, /projectConfig\.coordinator\?\.routes/)
})

