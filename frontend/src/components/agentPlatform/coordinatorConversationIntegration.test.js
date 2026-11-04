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

// 2026-11-05 收敛：助手浮窗统一走 main 共享层 assistantFloating（App 级挂载，
// assistant_floating 特性门控），本地 CoordinatorAssistantDock 退役。共享面板
// 承载江苏沉淀的设计：运行时常用问题（管理端可配、配置兜底）、Esc 收起、
// 下拉箭头收起按钮；Dock 及 coordinator-submit 链路不得回流。
test('floating assistant is app-level with quick prompts and esc collapse; dock retired', async () => {
  const app = await readSource('../../App.vue')
  const host = await readSource('../assistantFloating/AssistantFloatingHost.vue')
  const panel = await readSource('../assistantFloating/AssistantFloatingPanel.vue')
  const layout = await readSource('../reactAnalysis/MainLayout.vue')
  const chat = await readSource('../reactAnalysis/ChatArea.vue')
  const projectYaml = await readFile(new URL('../../../../projects/jiangsu-ops/project.yaml', import.meta.url), 'utf8')

  assert.match(app, /<AssistantFloatingHost/)
  assert.match(projectYaml, /assistant_floating: true/)
  assert.match(host, /Escape/)
  assert.match(panel, /getCoordinatorQuickPrompts/)
  assert.match(panel, /quickPrompts/)
  assert.match(panel, /收起（Esc）/)
  assert.match(panel, /ChevronDown/)
  assert.doesNotMatch(layout, /CoordinatorAssistantDock/)
  assert.doesNotMatch(layout, /coordinator-submit/)
  assert.doesNotMatch(chat, /toggle-float-assistant/)
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

