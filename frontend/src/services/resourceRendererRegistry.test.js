import assert from 'node:assert/strict'
import test from 'node:test'

import { rendererKey, RESOURCE_RENDERERS } from './resourceRendererRegistry.js'

test('selects a supported renderer and safely falls back to file details', () => {
  assert.equal(rendererKey({ renderer: 'pdf', status: 'active' }), 'pdf')
  assert.equal(rendererKey({ renderer: 'unknown', status: 'active' }), 'file')
  assert.equal(rendererKey({ status: 'missing', renderer: 'pdf' }), 'file')
  assert.deepEqual(Object.keys(RESOURCE_RENDERERS), [
    'pdf', 'html', 'markdown', 'spreadsheet', 'presentation',
    'image', 'chart', 'board', 'file'
  ])
})
