import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

test('knowledge graph tab composes the G6 workbench without the legacy map panel', () => {
  const source = fs.readFileSync(new URL('./KnowledgeGraphTab.vue', import.meta.url), 'utf8')
  for (const component of ['KnowledgeGraphStatus', 'KnowledgeGraphToolbar', 'KnowledgeGraphCanvas', 'KnowledgeGraphDetailPanel', 'KnowledgeGraphChat']) {
    assert.match(source, new RegExp(component))
  }
  assert.doesNotMatch(source, /CognitiveMapPanel/)
  assert.doesNotMatch(source, /CognitiveMapGraphChat/)
  assert.doesNotMatch(source, /graphLinks\.slice/)
  assert.match(source, /store\.loadGraph/)
  assert.match(source, /getKnowledgeGraphBuild/)
})
