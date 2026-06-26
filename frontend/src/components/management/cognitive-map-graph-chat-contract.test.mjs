import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = readFileSync(new URL('./CognitiveMapGraphChat.vue', import.meta.url), 'utf8')
const panelSource = readFileSync(new URL('./CognitiveMapPanel.vue', import.meta.url), 'utf8')

test('graph chat sends graph mode analysis with cognitive map context', () => {
  assert.match(source, /agentMode:\s*'graph'/)
  assert.match(source, /mapContext:\s*buildGraphMapContext\(\)/)
  assert.match(source, /active_map_id:\s*props\.currentMap\?\.id/)
  assert.match(source, /selected_item:/)
})

test('graph chat disables send without current map or input', () => {
  assert.match(source, /:disabled="!canSend"/)
  assert.match(source, /const canSend = computed/)
  assert.match(source, /props\.currentMap\?\.id/)
})

test('cognitive map panel embeds graph chat as a drawer tab', () => {
  assert.match(panelSource, /import CognitiveMapGraphChat from '\.\/CognitiveMapGraphChat\.vue'/)
  assert.match(panelSource, /inspectorTab === 'graph-chat'/)
  assert.match(panelSource, /<CognitiveMapGraphChat/)
  assert.match(panelSource, /@graph-updated="handleGraphChatUpdated"/)
})
