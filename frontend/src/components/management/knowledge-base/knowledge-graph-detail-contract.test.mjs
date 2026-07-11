import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

test('detail panel loads evidence and exposes all graph fact management actions', () => {
  const source = fs.readFileSync(new URL('./KnowledgeGraphDetailPanel.vue', import.meta.url), 'utf8')
  for (const token of ['evidence_text', 'confidence', 'stale', 'confirm', 'reject', 'save', 'begin-merge', 'delete', 'open-document-chunk']) {
    assert.match(source, new RegExp(token))
  }
  assert.match(source, /AbortController/)
  assert.match(source, /getKnowledgeGraphEntityMentions/)
  assert.match(source, /getKnowledgeGraphRelationMentions/)
})
