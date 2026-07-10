import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('knowledge base detail owns document replacement and graph management', () => {
  const panel = read('../KnowledgeBasePanel.vue')
  const graphTab = read('./KnowledgeGraphTab.vue')
  const graphReview = read('./KnowledgeGraphReview.vue')

  assert.match(panel, /activeTab/)
  assert.match(panel, /value:\s*'graph'/)
  assert.match(panel, /replaceDocument/)
  assert.match(graphTab, /candidate/)
  assert.match(graphTab, /confirmed/)
  assert.match(graphReview, /rejected/)
  assert.match(graphReview, /merge/)
  assert.doesNotMatch(graphTab, /uploadCognitiveMapFile|buildCognitiveMap/)
})
