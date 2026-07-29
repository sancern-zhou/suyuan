import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./knowledgeBase.js', import.meta.url), 'utf8')

test('knowledge base client exposes replacement and graph child resources', () => {
  assert.match(source, /replaceDocument\(kbId, docId, file/)
  assert.match(source, /documents\/\$\{docId\}\/content/)
  assert.match(source, /getKnowledgeGraphStatus/)
  assert.match(source, /queryKnowledgeGraph/)
  assert.match(source, /updateKnowledgeGraphEntity/)
  assert.match(source, /mergeKnowledgeGraphEntities/)
  assert.match(source, /reindexKnowledgeGraph/)
})
