import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readSource = relativePath => readFile(new URL(relativePath, import.meta.url), 'utf8')

test('coordinator home exposes one assistant conversation entry with prompt routing', async () => {
  const source = await readSource('../coordinator/CoordinatorHome.vue')

  assert.match(source, /aria-label="助手模式对话窗口"/)
  assert.match(source, /@submit\.prevent="submitQuery"/)
  assert.match(source, /emit\('submit', \{ query: value \}\)/)
  assert.match(source, /quickPrompts/)
})

test('assistant sends can route through project coordinator rules', async () => {
  const source = await readFile(new URL('../../composables/reactAnalysis/useSessionManagement.js', import.meta.url), 'utf8')

  assert.match(source, /resolveCoordinatorMode\(/)
  assert.match(source, /agentMode === 'assistant'/)
  assert.match(source, /projectConfig\.coordinator\?\.routes/)
})

