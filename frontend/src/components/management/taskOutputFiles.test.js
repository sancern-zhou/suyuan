import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildTaskOutputGroups,
  executionStatusLabel,
  formatTaskOutputSize,
  getTaskOutputFile
} from './taskOutputFiles.js'

test('only exposes generated output roles as task output files', () => {
  assert.equal(getTaskOutputFile({ role: 'attachment', file_path: '/tmp/input.xlsx' }), null)
  assert.equal(getTaskOutputFile({ role: 'source', file_path: '/tmp/source.csv' }), null)

  assert.deepEqual(getTaskOutputFile({
    ref_id: 'report', role: 'report', label: '日报.docx', file_path: '/tmp/daily.docx',
    metadata: { size_bytes: 1024 }
  }), {
    id: 'report', label: '日报.docx', format: 'DOCX',
    url: '/api/file/%2Ftmp%2Fdaily.docx', mimeType: '', sizeBytes: 1024, createdAt: ''
  })
})

test('groups output files by newest execution and retains only non-empty batches', () => {
  const groups = buildTaskOutputGroups([
    { execution_id: 'old', session_id: 's-old', started_at: '2026-07-21T08:00:00Z', status: 'success' },
    { execution_id: 'new', session_id: 's-new', started_at: '2026-07-22T08:00:00Z', status: 'failed' }
  ], {
    's-old': [{ ref_id: 'old-file', role: 'output', label: '旧文件.csv', file_path: '/tmp/old.csv' }],
    's-new': [{ ref_id: 'input', role: 'attachment', label: '输入.xlsx', file_path: '/tmp/input.xlsx' }]
  })

  assert.deepEqual(groups.map(group => group.executionId), ['old'])
  assert.equal(groups[0].files[0].format, 'CSV')
})

test('uses declared artifact download URLs and formats file metadata', () => {
  const file = getTaskOutputFile({
    ref_id: 'html', role: 'primary', label: '大屏',
    metadata: { download_url: '/api/html-artifacts/dashboard/download/html', format: 'html', file_size: 1536 }
  })

  assert.equal(file.url, '/api/html-artifacts/dashboard/download/html')
  assert.equal(file.format, 'HTML')
  assert.equal(formatTaskOutputSize(file.sizeBytes), '1.5 KB')
  assert.equal(executionStatusLabel('timeout'), '执行超时')
})
