import test from 'node:test'
import assert from 'node:assert/strict'

import { shouldAutoSwitchToDocument } from './panelTabPolicy.js'


test('auto-switches to document for a newly generated spreadsheet preview', () => {
  assert.equal(shouldAutoSwitchToDocument({
    doc: {
      file_path: '/data/result.xlsx',
      spreadsheet_preview: {
        file_type: 'xlsx',
        editable: true
      }
    },
    previousDoc: null,
    activeTab: 'visualization'
  }), true)
})


test('auto-switches to document for a restored native presentation preview', () => {
  assert.equal(shouldAutoSwitchToDocument({
    doc: {
      file_path: '/data/deck.pptx',
      ppt_preview: {
        pages: [{ slide: 1, image_url: '/api/file/slide-1.png' }]
      }
    },
    previousDoc: null,
    activeTab: 'visualization'
  }), true)
})
