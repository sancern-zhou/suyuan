import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildTaskOutputGroups,
  executionStatusLabel,
  formatTaskOutputSize,
  getTaskOutputFile
} from './taskOutputFiles.js'

test('only exposes generated output roles as task output files', () => {
  assert.equal(getTaskOutputFile({ role: 'attachment', download_url: '/download/input' }), null)
  assert.equal(getTaskOutputFile({ role: 'source', download_url: '/download/source' }), null)

  assert.deepEqual(getTaskOutputFile({
    resource_id: 'report', role: 'report', label: '日报.docx', format: 'docx',
    download_url: '/api/sessions/s/resources/report/content?disposition=attachment', size_bytes: 1024
  }), {
    id: 'report', label: '日报.docx', format: 'DOCX',
    url: '/api/sessions/s/resources/report/content?disposition=attachment', mimeType: '', sizeBytes: 1024, createdAt: ''
  })
})

test('groups output files by newest execution and retains only non-empty batches', () => {
  const groups = buildTaskOutputGroups([
    { execution_id: 'old', session_id: 's-old', started_at: '2026-07-21T08:00:00Z', status: 'success' },
    { execution_id: 'new', session_id: 's-new', started_at: '2026-07-22T08:00:00Z', status: 'failed' }
  ], {
    's-old': [{ resource_id: 'old-file', role: 'output', label: '旧文件.csv', format: 'csv', download_url: '/download/old' }],
    's-new': [{ resource_id: 'input', role: 'attachment', label: '输入.xlsx', download_url: '/download/input' }]
  })

  assert.deepEqual(groups.map(group => group.executionId), ['old'])
  assert.equal(groups[0].files[0].format, 'CSV')
})

test('uses declared artifact download URLs and formats file metadata', () => {
  const file = getTaskOutputFile({
    resource_id: 'html', role: 'output', label: '大屏',
    download_url: '/api/sessions/s/resources/html/content?disposition=attachment', format: 'html', size_bytes: 1536
  })

  assert.equal(file.url, '/api/sessions/s/resources/html/content?disposition=attachment')
  assert.equal(file.format, 'HTML')
  assert.equal(formatTaskOutputSize(file.sizeBytes), '1.5 KB')
  assert.equal(executionStatusLabel('timeout'), '执行超时')
})
