import test from 'node:test'
import assert from 'node:assert/strict'

import { extractOfficeDocumentsFromMessages } from './officeDocumentRecovery.js'


test('recovers a native presentation preview from legacy tool-result messages', () => {
  const documents = extractOfficeDocumentsFromMessages([{
    type: 'tool_result',
    data: {
      result: {
        data: {
          file_path: '/data/deck.pptx',
          ppt_preview: {
            pages: [{ slide: 1, png_path: '/tmp/deck/page-001.png' }]
          }
        },
        metadata: { generator: 'present_artifact' },
        summary: 'PPT ready'
      }
    }
  }])

  assert.equal(documents.length, 1)
  assert.equal(documents[0].file_path, '/data/deck.pptx')
  assert.equal(documents[0].ppt_preview.pages[0].slide, 1)
})
