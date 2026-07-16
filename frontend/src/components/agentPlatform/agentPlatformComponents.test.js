import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const readComponent = name => readFile(new URL(`./${name}`, import.meta.url), 'utf8')

test('agent platform renders accessible cards and emits mode selection', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.match(source, /v-for="scene in sceneGroups"/)
  assert.match(source, /v-for="agent in scene\.agents"/)
  assert.match(source, /class="scene-icon"/)
  assert.match(source, /scene\.iconPaths/)
  assert.match(source, /path\.tone/)
  assert.match(source, /<button/)
  assert.match(source, /emit\('select', agent\.id\)/)
  assert.match(source, /运行中/)
  assert.match(source, /focus-visible/)
})

test('agent platform keeps three scene rows compact enough for one desktop viewport', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.match(source, /padding: clamp\(24px, 4vh, 40px\) 0 32px/)
  assert.match(source, /grid-template-columns: 118px minmax\(0, 1fr\)/)
  assert.match(source, /min-height: 176px/)
  assert.match(source, /gap: 14px/)
  assert.match(source, /@media \(max-width: 820px\)/)
})

test('agent cards use a clean surface without a colored left-edge decoration', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.doesNotMatch(source, /&::before/)
  assert.doesNotMatch(source, /inset: 0 auto 0 0/)
  assert.doesNotMatch(source, /class="agent-icon"/)
  assert.doesNotMatch(source, /agent\.iconPaths/)
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
