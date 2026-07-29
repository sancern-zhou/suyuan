import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const storeSource = readFileSync(new URL('../../stores/reactStore.js', import.meta.url), 'utf8')
const inputSource = readFileSync(new URL('../InputBox.vue', import.meta.url), 'utf8')
const selectorSource = readFileSync(new URL('../AgentModeSelector.vue', import.meta.url), 'utf8')

test('ppt mode has isolated state and is accepted by the composer', () => {
  assert.match(storeSource, /VALID_MODES\s*=\s*\[[^\]]*'ppt'/s)
  assert.match(storeSource, /modeStates:\s*\{[\s\S]*ppt:\s*createEmptyModeState\(\)/)
  assert.match(inputSource, /validAgentModes\s*=\s*\[[^\]]*'ppt'/s)
})

test('legacy mode selector exposes the dedicated ppt entry', () => {
  assert.match(selectorSource, /selectMode\('ppt'\)/)
  assert.match(selectorSource, /<span>幻灯片<\/span>/)
})
