import assert from 'node:assert/strict'
import test from 'node:test'

import { summarizeRightPanelResources } from './rightPanelResources.js'

const item = (overrides = {}) => ({
  resource_id: 'docx', group_id: 'document', relation: 'primary', kind: 'file', role: 'report',
  renderer: 'file', format: 'docx', status: 'active', updated_at: '2026-08-01T10:00:00Z',
  ...overrides
})

test('derives every artifact tab and count only from resource DTOs', () => {
  const summary = summarizeRightPanelResources([
    item(),
    item({ resource_id: 'pdf', relation: 'preview', renderer: 'pdf', format: 'pdf' }),
    item({ resource_id: 'chart', group_id: 'chart', kind: 'visual', role: 'output', renderer: 'chart' }),
    item({ resource_id: 'board', group_id: 'board', kind: 'artifact', role: 'output', renderer: 'board', format: 'drawio' })
  ])

  assert.deepEqual(summary.counts, { files: 3, document: 1, visualization: 1, board: 1 })
  assert.deepEqual(summary.availableTabs, ['files', 'document', 'visualization', 'board'])
})

test('ignores message-shaped legacy fields because the selector accepts resources only', () => {
  const summary = summarizeRightPanelResources([])
  assert.equal(summary.counts.document, 0)
  assert.equal(summary.hasArtifacts, false)
})
