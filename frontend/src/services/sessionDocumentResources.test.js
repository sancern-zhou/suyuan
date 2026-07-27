import test from 'node:test'
import assert from 'node:assert/strict'

import {
  mapSessionDocumentResource,
  mapSessionDocumentResources,
  refreshDurableDocumentResources
} from './sessionDocumentResources.js'


test('maps a unified spreadsheet resource to the office document preview contract', () => {
  const resource = {
    ref_id: 'resource-1',
    label: '回款请款匹配结果',
    locator: {
      path: '/data/回款请款匹配结果.xlsx'
    },
    presentation: {
      format: 'XLSX',
      preview: {
        file_type: 'xlsx',
        editable: true,
        sheet_names: ['匹配结果']
      }
    }
  }

  const document = mapSessionDocumentResource(resource)

  assert.equal(document.file_name, '回款请款匹配结果')
  assert.equal(document.file_path, '/data/回款请款匹配结果.xlsx')
  assert.equal(document.format, 'xlsx')
  assert.equal(document.pdf_preview, undefined)
  assert.deepEqual(document.spreadsheet_preview, {
    file_type: 'xlsx',
    editable: true,
    sheet_names: ['匹配结果']
  })
})


test('maps missing resource arrays to an empty document list', () => {
  assert.deepEqual(mapSessionDocumentResources(undefined), [])
})


test('maps direct HTML previews by format without fabricating a PDF preview', () => {
  const document = mapSessionDocumentResource({
    label: '网页报告',
    locator: { path: '/data/report.html' },
    presentation: {
      format: 'html',
      preview: {
        html_id: 'report-1',
        html_url: '/api/html/report-1'
      }
    }
  })

  assert.equal(document.pdf_preview, undefined)
  assert.equal(document.html_preview.html_id, 'report-1')
  assert.equal(document.html_url, '/api/html/report-1')
})


test('does not expose an empty preview as a supported office preview', () => {
  const document = mapSessionDocumentResource({
    label: '源文件',
    locator: { path: '/data/source.drawio' },
    presentation: { format: 'drawio', preview: {} }
  })

  assert.equal(document.pdf_preview, undefined)
  assert.equal(document.html_preview, undefined)
  assert.equal(document.spreadsheet_preview, undefined)
})


const spreadsheetResource = {
  ref_id: 'resource-1',
  label: '匹配结果',
  locator: { path: '/data/result.xlsx' },
  presentation: {
    format: 'xlsx',
    preview: { file_type: 'xlsx', editable: true }
  }
}

const durableTerminalData = (version) => ({
  resource_durable: true,
  resource_version: version
})

const silentLogger = { error() {} }


test('refreshes and applies documents for a new durable resource version only once', async () => {
  const targetState = {
    sessionId: 'assistant_session_1',
    lazyArtifacts: {}
  }
  let fetchCount = 0
  let appliedDocuments = null
  const options = {
    terminalData: durableTerminalData(2),
    sessionId: targetState.sessionId,
    targetState,
    fetchDocuments: async () => {
      fetchCount += 1
      return { resources: [spreadsheetResource] }
    },
    applyDocuments: (documents) => {
      appliedDocuments = documents
    },
    logger: silentLogger
  }

  await refreshDurableDocumentResources(options)
  await refreshDurableDocumentResources(options)

  assert.equal(fetchCount, 1)
  assert.equal(appliedDocuments.length, 1)
  assert.equal(appliedDocuments[0].file_path, '/data/result.xlsx')
  assert.equal(targetState.documentResourceRefresh.appliedVersion, 2)
  assert.equal(targetState.lazyArtifacts.loadingOfficeDocuments, false)
})


test('deduplicates the same resource version while its request is in flight', async () => {
  const targetState = {
    sessionId: 'assistant_session_1',
    lazyArtifacts: {}
  }
  let resolveFetch
  let fetchCount = 0
  const fetchPromise = new Promise(resolve => {
    resolveFetch = resolve
  })
  const options = {
    terminalData: durableTerminalData(3),
    sessionId: targetState.sessionId,
    targetState,
    fetchDocuments: async () => {
      fetchCount += 1
      return fetchPromise
    },
    applyDocuments() {},
    logger: silentLogger
  }

  const first = refreshDurableDocumentResources(options)
  const second = refreshDurableDocumentResources(options)
  resolveFetch({ resources: [spreadsheetResource] })
  await Promise.all([first, second])

  assert.equal(fetchCount, 1)
})


test('ignores a document response after another session becomes active', async () => {
  const targetState = {
    sessionId: 'assistant_session_1',
    lazyArtifacts: {}
  }
  let activeSessionId = targetState.sessionId
  let resolveFetch
  let applyCount = 0
  const fetchPromise = new Promise(resolve => {
    resolveFetch = resolve
  })

  const refresh = refreshDurableDocumentResources({
    terminalData: durableTerminalData(4),
    sessionId: targetState.sessionId,
    targetState,
    fetchDocuments: async () => fetchPromise,
    applyDocuments: () => {
      applyCount += 1
    },
    isSessionActive: () => activeSessionId === targetState.sessionId,
    logger: silentLogger
  })
  activeSessionId = 'assistant_session_2'
  resolveFetch({ resources: [spreadsheetResource] })
  await refresh

  assert.equal(applyCount, 0)
  assert.equal(targetState.documentResourceRefresh.appliedVersion, 0)
})


test('loads every document resource page before applying a durable version', async () => {
  const targetState = {
    sessionId: 'assistant_session_1',
    lazyArtifacts: {}
  }
  const cursors = []
  let appliedDocuments = null

  await refreshDurableDocumentResources({
    terminalData: durableTerminalData(6),
    sessionId: targetState.sessionId,
    targetState,
    fetchDocuments: async (_sessionId, options = {}) => {
      cursors.push(options.cursor || null)
      if (!options.cursor) {
        return {
          resources: [spreadsheetResource],
          next_cursor: '200'
        }
      }
      return {
        resources: [{
          ...spreadsheetResource,
          ref_id: 'resource-2',
          locator: { path: '/data/latest.xlsx' }
        }],
        next_cursor: null
      }
    },
    applyDocuments: (documents) => {
      appliedDocuments = documents
    },
    logger: silentLogger
  })

  assert.deepEqual(cursors, [null, '200'])
  assert.deepEqual(
    appliedDocuments.map(document => document.file_path),
    ['/data/result.xlsx', '/data/latest.xlsx']
  )
})


test('allows a durable resource version to retry after a failed request', async () => {
  const targetState = {
    sessionId: 'assistant_session_1',
    lazyArtifacts: {}
  }
  let fetchCount = 0
  const fetchDocuments = async () => {
    fetchCount += 1
    if (fetchCount === 1) throw new Error('temporary failure')
    return { resources: [spreadsheetResource] }
  }
  const options = {
    terminalData: durableTerminalData(5),
    sessionId: targetState.sessionId,
    targetState,
    fetchDocuments,
    applyDocuments() {},
    logger: silentLogger
  }

  await refreshDurableDocumentResources(options)
  await refreshDurableDocumentResources(options)

  assert.equal(fetchCount, 2)
  assert.equal(targetState.documentResourceRefresh.appliedVersion, 5)
})
