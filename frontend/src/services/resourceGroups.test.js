import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildResourceGroups,
  preferredPreview,
  targetTab,
  topLevelProducts
} from './resourceGroups.js'

const primary = (overrides = {}) => ({
  resource_id: 'report-docx', group_id: 'report', relation: 'primary',
  kind: 'file', role: 'report', label: '报告.docx', format: 'docx',
  renderer: 'file', status: 'active', version: 2, updated_at: '2026-08-01T10:00:00Z',
  ...overrides
})

test('groups versions and exposes only current generated primary products', () => {
  const groups = buildResourceGroups([
    primary({ resource_id: 'old', version: 1, status: 'superseded' }),
    primary(),
    primary({ resource_id: 'pdf', relation: 'preview', parent_resource_id: 'report-docx', format: 'pdf', renderer: 'pdf' }),
    primary({ resource_id: 'chart', group_id: 'chart-group', label: '趋势图.png', kind: 'visual', role: 'output', renderer: 'chart' }),
    primary({ resource_id: 'dataset', group_id: 'data-group', label: '查询数据.json', kind: 'data', role: 'output', renderer: 'file' }),
    primary({ resource_id: 'input', group_id: 'upload', label: '输入.xlsx', role: 'attachment' })
  ])

  assert.deepEqual(topLevelProducts(groups).map(group => group.primary.label), ['报告.docx', '趋势图.png', '查询数据.json'])
  assert.equal(topLevelProducts(groups).some(group => group.primary.relation === 'preview'), false)
  assert.equal(topLevelProducts(groups).some(group => group.primary.role === 'attachment'), false)
  assert.equal(groups.find(group => group.group_id === 'report').versions.length, 2)
})

test('chooses the best active renderer and target tab for each group', () => {
  const [reportGroup] = buildResourceGroups([
    primary(),
    primary({ resource_id: 'pdf', relation: 'preview', parent_resource_id: 'report-docx', format: 'pdf', renderer: 'pdf' })
  ])
  assert.equal(preferredPreview(reportGroup).renderer, 'pdf')
  assert.equal(targetTab(reportGroup), 'document')
  assert.equal(targetTab({ primary: primary({ renderer: 'chart', kind: 'visual' }) }), 'visualization')
  assert.equal(targetTab({ primary: primary({ renderer: 'board', format: 'drawio' }) }), 'board')
  assert.equal(targetTab({ primary: primary({ renderer: 'file', format: 'zip' }) }), 'files')
})

test('keeps chart image renditions in visualization and treats standalone images as visual', () => {
  const [chartGroup] = buildResourceGroups([
    primary({ resource_id: 'chart', kind: 'visual', renderer: 'chart', format: 'json' }),
    primary({
      resource_id: 'chart-image', relation: 'rendition', parent_resource_id: 'chart',
      renderer: 'image', format: 'png'
    })
  ])

  assert.equal(preferredPreview(chartGroup).renderer, 'image')
  assert.equal(targetTab(chartGroup), 'visualization')
  assert.equal(targetTab({ primary: primary({ renderer: 'image', format: 'png' }) }), 'visualization')
})
