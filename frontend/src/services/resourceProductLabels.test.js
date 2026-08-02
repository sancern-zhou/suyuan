import assert from 'node:assert/strict'
import test from 'node:test'

import { derivativeLabel } from './resourceProductLabels.js'

test('presents derivative relations as user-facing Chinese labels', () => {
  assert.equal(derivativeLabel({ relation: 'preview', format: 'pdf' }), 'PDF 预览')
  assert.equal(derivativeLabel({ relation: 'rendition', format: 'docx' }), 'Word 导出版')
  assert.equal(derivativeLabel({ relation: 'rendition', format: 'html' }), 'HTML 导出版')
})
