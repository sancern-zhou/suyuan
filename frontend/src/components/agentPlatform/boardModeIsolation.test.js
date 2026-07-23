import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const storeSource = readFileSync(new URL('../../stores/reactStore.js', import.meta.url), 'utf8')
const inputSource = readFileSync(new URL('../InputBox.vue', import.meta.url), 'utf8')
const selectorSource = readFileSync(new URL('../AgentModeSelector.vue', import.meta.url), 'utf8')
const sessionManagementSource = readFileSync(new URL('../../composables/reactAnalysis/useSessionManagement.js', import.meta.url), 'utf8')

test('board state and snapshots are isolated to board mode', () => {
  assert.match(storeSource, /actualMode === 'board'/)
  assert.match(storeSource, /mode !== 'board'/)
  assert.match(storeSource, /actualMode === 'board' \? this\.buildBoardContext/)
  assert.doesNotMatch(storeSource, /actualMode === 'chart' \? this\.buildBoardContext/)
  assert.match(inputSource, /currentMode !== 'board'/)
  assert.match(sessionManagementSource, /store\.currentMode === 'board'/)
  assert.match(sessionManagementSource, /restoredMode === 'board'/)
})

test('mode selector exposes a dedicated board entry', () => {
  assert.match(selectorSource, /selectMode\('board'\)/)
  assert.match(selectorSource, /<span>画板<\/span>/)
})
