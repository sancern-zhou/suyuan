import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildResourceQuery,
  resourceContentUrl,
  resourceDownloadUrl
} from './sessionResources.js'

test('builds opaque session resource URLs with encoded identifiers', () => {
  assert.equal(
    resourceContentUrl('s 1', 'r/1'),
    '/api/sessions/s%201/resources/r%2F1/content'
  )
  assert.equal(
    resourceDownloadUrl('s 1', 'r/1'),
    '/api/sessions/s%201/resources/r%2F1/content?disposition=attachment'
  )
})

test('serializes only defined catalog filters', () => {
  assert.equal(
    buildResourceQuery({ renderer: 'pdf', status: 'active', cursor: '20' }),
    'renderer=pdf&status=active&cursor=20'
  )
  assert.equal(buildResourceQuery({ status: null, limit: undefined }), '')
})
