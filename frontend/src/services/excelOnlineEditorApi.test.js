import assert from 'node:assert/strict'
import {
  downloadExcelFile,
  openExcelForEditing,
  saveEditedExcel
} from './excelOnlineEditorApi.js'

const opened = await openExcelForEditing('/tmp/source.xlsx', async (url, options) => {
  assert.equal(url, '/api/suyuan/office/open-excel')
  assert.equal(options.method, 'POST')
  assert.deepEqual(JSON.parse(options.body), { file_path: '/tmp/source.xlsx' })
  return {
    ok: true,
    async arrayBuffer() {
      return new Uint8Array([1, 2, 3]).buffer
    }
  }
}, '/api/suyuan')

assert.equal(opened.byteLength, 3)

const appended = []
class FakeFormData {
  append(...args) {
    appended.push(args)
  }
}

const saved = await saveEditedExcel({
  filePath: '/tmp/source.xlsx',
  sessionId: 'session-a',
  fileName: 'source.xlsx',
  buffer: new Uint8Array([4, 5, 6]).buffer,
  apiBaseUrl: '/api/suyuan/',
  formDataFactory: () => new FakeFormData(),
  fetchImpl: async (url, options) => {
    assert.equal(url, '/api/suyuan/office/save-excel')
    assert.equal(options.method, 'POST')
    assert.ok(options.body instanceof FakeFormData)
    return {
      ok: true,
      async json() {
        return {
          success: true,
          document: {
            doc_type: 'excel',
            file_path: '/tmp/source_edited.xlsx'
          }
        }
      }
    }
  }
})

assert.deepEqual(
  appended.map(([key]) => key),
  ['file_path', 'session_id', 'file']
)
assert.equal(appended[0][1], '/tmp/source.xlsx')
assert.equal(appended[1][1], 'session-a')
assert.equal(appended[2][2], 'source.xlsx')
assert.equal(saved.file_path, '/tmp/source_edited.xlsx')

const downloaded = await downloadExcelFile('/tmp/source_edited.xlsx', {
  fallbackFileName: 'source_edited.xlsx',
  apiBaseUrl: '/api/suyuan',
  fetchImpl: async (url, options) => {
    assert.equal(url, '/api/suyuan/office/download-excel')
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), {
      file_path: '/tmp/source_edited.xlsx',
      file_name: 'source_edited.xlsx'
    })
    return {
      ok: true,
      headers: {
        get(name) {
          return name.toLowerCase() === 'content-disposition'
            ? 'attachment; filename="download.xlsx"'
            : null
        }
      },
      async blob() {
        return new Blob(['excel'])
      }
    }
  }
})

assert.equal(downloaded.fileName, 'download.xlsx')
assert.equal(await downloaded.blob.text(), 'excel')
