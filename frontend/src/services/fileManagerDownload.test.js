import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { downloadManagedFile, fileManagerDownloadUrl } from './fileManagerDownload.js'


test('builds a gateway-ready file-manager download URL with an encoded path', () => {
  assert.equal(
    fileManagerDownloadUrl('报告 文件/结果.xlsx'),
    '/api/file-manager/download?path=%E6%8A%A5%E5%91%8A+%E6%96%87%E4%BB%B6%2F%E7%BB%93%E6%9E%9C.xlsx'
  )
})


test('downloads a managed file through the authenticated resource downloader', async () => {
  const calls = []
  const item = { name: '结果.xlsx', path: '报告 文件/结果.xlsx' }

  await downloadManagedFile(item, {
    downloadImpl: async (resource, runtime) => calls.push({ resource, runtime }),
    downloadRuntime: { fetchImpl: 'authenticated-fetch' }
  })

  assert.deepEqual(calls, [{
    resource: {
      label: '结果.xlsx',
      download_url: '/api/file-manager/download?path=%E6%8A%A5%E5%91%8A+%E6%96%87%E4%BB%B6%2F%E7%BB%93%E6%9E%9C.xlsx'
    },
    runtime: { fetchImpl: 'authenticated-fetch' }
  }])
})


test('file manager component uses managed downloads instead of opening an SPA route', async () => {
  const source = await readFile(new URL('../components/FileManagerPanel.vue', import.meta.url), 'utf8')

  assert.match(source, /downloadManagedFile\(item\)/)
  assert.doesNotMatch(source, /window\.open\(/)
})
