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
  assert.doesNotMatch(sessionManagementSource, /restoreDrawioBoardFromSession/)
  assert.match(sessionManagementSource, /resourceStore\.loadCatalog\(sessionId\)/)
})

test('every valid mode has an initialized mode state for reset and restore', () => {
  assert.match(storeSource, /const VALID_MODES = \[\.\.\.new Set\(\[\.\.\.AGENT_MODE_IDS, \.\.\.projectConfig\.agentModeIds, 'graph'\]\)\]/)
  assert.match(storeSource, /modeStates: Object\.fromEntries\(VALID_MODES\.map\(mode => \[mode, createEmptyModeState\(\)\]\)\)/)
})

test('mode selector exposes a dedicated board entry', () => {
  assert.match(selectorSource, /selectMode\('board'\)/)
  assert.match(selectorSource, /<span>画板<\/span>/)
})
