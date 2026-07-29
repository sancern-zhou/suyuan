import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeArtifactUrl,
  normalizeRelatedArtifactFiles
} from './artifactRelatedFiles.js'

test('browser artifact API URLs use the configured gateway base', () => {
  const apiBaseUrl = '/api/suyuan'

  assert.equal(
    normalizeArtifactUrl('/api/office/pdf/ppt-preview', { apiBaseUrl }),
    '/api/suyuan/office/pdf/ppt-preview'
  )
  assert.equal(
    normalizeArtifactUrl('/api/reports/monthly/html', { apiBaseUrl }),
    '/api/suyuan/reports/monthly/html'
  )
  assert.equal(
    normalizeArtifactUrl('/api/html-artifacts/diagram/assets/result.svg', { apiBaseUrl }),
    '/api/suyuan/html-artifacts/diagram/assets/result.svg'
  )
})

test('already-routed and non-API artifact URLs remain stable', () => {
  const options = { apiBaseUrl: '/api/suyuan', origin: 'https://suyuan.example' }

  assert.equal(
    normalizeArtifactUrl('/api/suyuan/office/pdf/current', options),
    '/api/suyuan/office/pdf/current'
  )
  assert.equal(
    normalizeArtifactUrl('https://cdn.example/api/files/report.pdf', options),
    'https://cdn.example/api/files/report.pdf'
  )
  assert.equal(normalizeArtifactUrl('blob:preview-pdf', options), 'blob:preview-pdf')
  assert.equal(
    normalizeArtifactUrl('data:application/pdf;base64,AA==', options),
    'data:application/pdf;base64,AA=='
  )
})

test('same-origin historical absolute API URLs preserve query and hash', () => {
  assert.equal(
    normalizeArtifactUrl(
      'https://suyuan.example/api/office/pdf/legacy?download=0#page=2',
      { apiBaseUrl: '/api/suyuan', origin: 'https://suyuan.example' }
    ),
    '/api/suyuan/office/pdf/legacy?download=0#page=2'
  )
  assert.equal(
    normalizeArtifactUrl('/api?download=0#page=2', {
      apiBaseUrl: '/api/suyuan',
      origin: 'https://suyuan.example'
    }),
    '/api/suyuan?download=0#page=2'
  )
})

test('related artifact downloads share the browser artifact URL contract', () => {
  assert.deepEqual(
    normalizeRelatedArtifactFiles({
      artifact: {
        related_files: [
          {
            file_path: '/tmp/diagram.svg',
            format: 'svg',
            url: '/api/html-artifacts/diagram/assets/diagram.svg'
          }
        ]
      }
    }),
    [
      {
        format: 'svg',
        file_path: '/tmp/diagram.svg',
        url: '/api/suyuan/html-artifacts/diagram/assets/diagram.svg',
        relative_path: undefined,
        downloadLabel: 'diagram.svg',
        key: '/tmp/diagram.svg'
      }
    ]
  )
})

test('related artifacts without explicit URLs get a gateway-routed file URL', () => {
  assert.deepEqual(
    normalizeRelatedArtifactFiles({
      artifact: {
        related_files: [
          {
            file_path: '/tmp/diagram source.drawio',
            format: 'drawio'
          }
        ]
      }
    }),
    [
      {
        format: 'drawio',
        file_path: '/tmp/diagram source.drawio',
        url: '/api/suyuan/file/%2Ftmp%2Fdiagram%20source.drawio',
        relative_path: undefined,
        downloadLabel: 'diagram source.drawio',
        key: '/tmp/diagram source.drawio'
      }
    ]
  )
})
