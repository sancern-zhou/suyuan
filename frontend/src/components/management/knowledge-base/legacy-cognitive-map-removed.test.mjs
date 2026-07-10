import assert from 'node:assert/strict'
import test from 'node:test'
import { existsSync, readFileSync } from 'node:fs'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('frontend has no standalone cognitive map runtime', () => {
  const sidebar = read('../../AssistantSidebar.vue')
  const chat = read('../CognitiveMapGraphChat.vue')
  assert.doesNotMatch(sidebar, /id:\s*'cognitive-map'/)
  assert.match(chat, /knowledge_base_id/)
  assert.doesNotMatch(chat, /active_map_id|@\/api\/cognitiveMap/)
  assert.equal(existsSync(new URL('../CognitiveMapPanel.vue', import.meta.url)), false)
})
