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
