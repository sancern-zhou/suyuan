import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'

const __dirname = dirname(fileURLToPath(import.meta.url))
const componentsDir = resolve(__dirname, '..')
const inputBoxSource = readFileSync(resolve(componentsDir, './InputBox.vue'), 'utf8')
const messageListSource = readFileSync(resolve(componentsDir, './ReActMessageList.vue'), 'utf8')

test('input and message list expose query dashboard layout controls', () => {
  assert.match(inputBoxSource, /showAgentModeSelector:\s*\{[\s\S]*?type:\s*Boolean[\s\S]*?default:\s*true/)
  assert.match(inputBoxSource, /v-if="assistantMode === 'general-agent' && showAgentModeSelector"/)
  assert.match(messageListSource, /hideWelcome:\s*\{[\s\S]*?type:\s*Boolean[\s\S]*?default:\s*false/)
  assert.match(messageListSource, /v-if="messages\.length === 0 && !hideWelcome"/)
})
