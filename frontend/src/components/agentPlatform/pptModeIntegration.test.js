import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const storeSource = readFileSync(new URL('../../stores/reactStore.js', import.meta.url), 'utf8')
const inputSource = readFileSync(new URL('../InputBox.vue', import.meta.url), 'utf8')

test('shared and project-declared modes receive isolated state and composer support', () => {
  assert.match(storeSource, /\.\.\.AGENT_MODE_IDS, \.\.\.projectConfig\.agentModeIds/)
  assert.match(storeSource, /Object\.fromEntries\(VALID_MODES\.map\(mode => \[mode, createEmptyModeState\(\)\]\)\)/)
  assert.match(inputSource, /\.\.\.AGENT_MODE_IDS, \.\.\.projectConfig\.agentModeIds/)
})
