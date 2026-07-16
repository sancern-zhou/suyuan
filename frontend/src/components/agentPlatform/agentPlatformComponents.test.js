import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const readComponent = name => readFile(new URL(`./${name}`, import.meta.url), 'utf8')

test('agent platform renders accessible cards and emits mode selection', async () => {
  const source = await readComponent('AgentPlatform.vue')

  assert.match(source, /v-for="agent in agents"/)
  assert.match(source, /<button/)
  assert.match(source, /emit\('select', agent\.id\)/)
  assert.match(source, /运行中/)
  assert.match(source, /focus-visible/)
})

test('agent workspace header resolves display copy from the shared catalog', async () => {
  const source = await readComponent('AgentWorkspaceHeader.vue')

  assert.match(source, /getAgentMode/)
  assert.match(source, /agent\.name/)
  assert.match(source, /agent\.description/)
})
