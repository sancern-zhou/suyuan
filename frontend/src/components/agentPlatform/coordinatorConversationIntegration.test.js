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

// 2026-10-12 产品决策：关键词路由（project.coordinator.routes）整体删除，不允许
// 关键词路由；发送统一走 useConversationActions（全页与浮窗共用），追问直通与
// 江苏自动档默认由该共享链路承载。契约随之改为守护委派结构而非路由代码。
test('assistant sends delegate to shared conversation actions without keyword routing', async () => {
  const management = await readFile(new URL('../../composables/reactAnalysis/useSessionManagement.js', import.meta.url), 'utf8')
  const actions = await readFile(new URL('../../composables/reactAnalysis/useConversationActions.js', import.meta.url), 'utf8')

  assert.match(management, /useConversationActions\(/)
  assert.doesNotMatch(management, /resolveCoordinatorMode\(/)
  assert.match(actions, /resolveDirectThroughRun\(/)
  assert.match(actions, /payload\.modelTier \|\| 'auto'/)
})

