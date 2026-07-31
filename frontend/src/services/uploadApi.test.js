import test from 'node:test'
import assert from 'node:assert/strict'

import { validateFile } from './uploadApi.js'

test('accepts HTML documents by MIME type', () => {
  const result = validateFile({ name: 'index.html', type: 'text/html', size: 1024 })

  assert.deepEqual(result, { valid: true, category: 'document' })
})

test('accepts HTM documents by extension when MIME type is unavailable', () => {
  const result = validateFile({ name: 'legacy.htm', type: '', size: 1024 })

  assert.deepEqual(result, { valid: true, category: 'document' })
})

test('accepts SVG images by MIME type', () => {
  const result = validateFile({ name: 'framework.svg', type: 'image/svg+xml', size: 1024 })

  assert.deepEqual(result, { valid: true, category: 'image' })
})

test('accepts SVG images by extension when MIME type is unavailable', () => {
  const result = validateFile({ name: 'framework.svg', type: '', size: 1024 })

  assert.deepEqual(result, { valid: true, category: 'image' })
})
