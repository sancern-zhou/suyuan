import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const storeSource = readFileSync(new URL('./reactStore.js', import.meta.url), 'utf8')
const inputBoxSource = readFileSync(new URL('../components/InputBox.vue', import.meta.url), 'utf8')

test('react store declares graph as a valid mode with isolated state', () => {
  assert.match(storeSource, /const VALID_MODES = \[[^\]]*'graph'[^\]]*\]/)
  assert.match(storeSource, /modeStates:\s*\{[\s\S]*graph:\s*createEmptyModeState\(\)/)
})

test('react store sends explicit graph map context to agent api', () => {
  assert.match(storeSource, /mapContext\s*=\s*actualMode === 'graph'\s*\?\s*options\.mapContext/)
  assert.match(storeSource, /\.\.\.\(mapContext !== null \? \{ mapContext \} : \{\}\)/)
})

test('input box accepts graph as a valid internal mode without changing selector markup', () => {
  assert.match(inputBoxSource, /const validAgentModes = \[[^\]]*'graph'[^\]]*\]/)
})
