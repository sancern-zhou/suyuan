import test from 'node:test'
import assert from 'node:assert/strict'

import { historyRowLabels, preserveCatalogFields } from './sessionHistoryAccess.js'

test('catalog fields survive session history merges', () => {
  const merged = preserveCatalogFields(
    { session_id: 's1', source: 'knowledge_qa', owner_username: 'alice' },
    { session_id: 's1', query: 'hello' }
  )

  assert.equal(merged.source, 'knowledge_qa')
  assert.equal(merged.owner_username, 'alice')
})

test('administrator labels include source and owner', () => {
  assert.deepEqual(
    historyRowLabels(
      { source: 'web', owner_display_name: 'Alice', owner_username: 'alice' },
      true
    ),
    { source: 'Web', owner: 'Alice（alice）', readOnly: false }
  )
})

test('social conversations are labelled read-only without exposing owner to users', () => {
  assert.deepEqual(
    historyRowLabels(
      { source: 'social', owner_display_name: 'Alice', read_only_on_web: true },
      false
    ),
    { source: '微信', owner: '', readOnly: true }
  )
})
