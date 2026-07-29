import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = readFileSync(new URL('./KnowledgeGraphChat.vue', import.meta.url), 'utf8')
const tabSource = readFileSync(new URL('./knowledge-base/KnowledgeGraphTab.vue', import.meta.url), 'utf8')

test('knowledge graph chat sends the current knowledge base and selected graph context', () => {
  assert.match(source, /agentMode:\s*'graph'/)
  assert.match(source, /knowledge_base_id:\s*props\.knowledgeBaseId/)
  assert.match(source, /selected_item:\s*selectedItemPayload\(\)/)
  assert.match(source, /preserveCurrentMode:\s*true/)
  assert.match(source, /emit\('graph-updated'\)/)
})

test('knowledge graph tab renders the retained knowledge graph chat component', () => {
  assert.match(tabSource, /import KnowledgeGraphChat from '\.\.\/KnowledgeGraphChat\.vue'/)
  assert.match(tabSource, /<KnowledgeGraphChat/)
  assert.doesNotMatch(tabSource, /CognitiveMapGraphChat/)
})
