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
  const validModesSource = storeSource.match(/const VALID_MODES = \[([^\]]+)\]/)?.[1]
  const modeStatesSource = storeSource.match(/modeStates:\s*\{([\s\S]*?)\n\s*\},\n\n\s*\/\/ 同一模式下/)?.[1]

  assert.ok(validModesSource, 'reactStore should declare VALID_MODES')
  assert.ok(modeStatesSource, 'reactStore should initialize modeStates')

  const validModes = [...validModesSource.matchAll(/'([^']+)'/g)].map(match => match[1])
  for (const mode of validModes) {
    assert.match(
      modeStatesSource,
      new RegExp(`\\b${mode}:\\s*createEmptyModeState\\(\\)`),
      `modeStates.${mode} must exist before reset or session restore`
    )
  }
})

test('mode selector exposes a dedicated board entry', () => {
  assert.match(selectorSource, /selectMode\('board'\)/)
  assert.match(selectorSource, /<span>画板<\/span>/)
})
