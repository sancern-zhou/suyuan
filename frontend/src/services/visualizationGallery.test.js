import assert from 'node:assert/strict'
import test from 'node:test'

import { visualizationGalleryItems } from './visualizationGallery.js'

const visual = (overrides = {}) => ({
  resource_id: 'chart-1', group_id: 'group-1', relation: 'primary', kind: 'visual',
  role: 'output', label: '图表', format: 'json', renderer: 'chart', status: 'active',
  version: 1, created_at: '2026-08-02T10:00:00Z', updated_at: '2026-08-02T10:00:00Z',
  ...overrides
})

test('shows chart and image groups in first-produced order', () => {
  const items = visualizationGalleryItems([
    visual({ resource_id: 'new', group_id: 'new', created_at: '2026-08-02T11:00:00Z' }),
    visual({ resource_id: 'old', group_id: 'old', renderer: 'image', format: 'png', created_at: '2026-08-02T09:00:00Z' })
  ])
  assert.deepEqual(items.map(item => item.group.group_id), ['old', 'new'])
})

test('keeps one card per group and uses its preferred preview', () => {
  const items = visualizationGalleryItems([
    visual(),
    visual({ resource_id: 'chart-1-image', relation: 'rendition', renderer: 'image', format: 'png' })
  ])
  assert.equal(items.length, 1)
  assert.equal(items[0].resource.resource_id, 'chart-1-image')
})

test('can include an explicitly opened visual attachment', () => {
  const attachment = visual({ resource_id: 'attachment', group_id: 'attachment-group', role: 'attachment' })
  assert.equal(visualizationGalleryItems([attachment]).length, 0)
  assert.equal(visualizationGalleryItems([attachment], 'attachment').length, 1)
})
