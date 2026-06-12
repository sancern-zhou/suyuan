import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getPanelDocumentIdentity,
  shouldAutoSwitchToDocument
} from './panelTabPolicy.js'

const baseDoc = {
  file_path: '/tmp/report.docx',
  html_preview: {
    html_id: 'report-html',
    html_url: '/api/files/report.html'
  }
}

test('does not switch from board to document when the same document is replayed', () => {
  assert.equal(
    shouldAutoSwitchToDocument({
      doc: { ...baseDoc },
      previousDoc: { ...baseDoc },
      activeTab: 'board'
    }),
    false
  )
})

test('switches to document when a new preview document appears', () => {
  assert.equal(
    shouldAutoSwitchToDocument({
      doc: {
        file_path: '/tmp/new-report.docx',
        html_preview: {
          html_id: 'new-report-html',
          html_url: '/api/files/new-report.html'
        }
      },
      previousDoc: { ...baseDoc },
      activeTab: 'board'
    }),
    true
  )
})

test('uses stable preview fields as document identity', () => {
  assert.equal(getPanelDocumentIdentity(baseDoc), '/tmp/report.docx')
  assert.equal(
    getPanelDocumentIdentity({ html_preview: { html_url: '/api/files/report.html' } }),
    '/api/files/report.html'
  )
})

test('handles missing previous document while deciding document tab switch', () => {
  assert.equal(getPanelDocumentIdentity(null), '')
  assert.equal(
    shouldAutoSwitchToDocument({
      doc: { ...baseDoc },
      previousDoc: null,
      activeTab: 'board'
    }),
    true
  )
})
