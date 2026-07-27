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
        spreadsheet_preview: {
          sheet_names: ['匹配结果']
        }
      }
    }
  }

  const document = mapSessionDocumentResource(resource)

  assert.equal(document.file_name, '回款请款匹配结果')
  assert.equal(document.file_path, '/data/回款请款匹配结果.xlsx')
  assert.equal(document.format, 'xlsx')
  assert.equal(document.pdf_preview.file_type, 'xlsx')
  assert.deepEqual(document.spreadsheet_preview, {
    sheet_names: ['匹配结果']
  })
})


test('maps missing resource arrays to an empty document list', () => {
  assert.deepEqual(mapSessionDocumentResources(undefined), [])
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


test('ignores a document response after the target state changes session', async () => {
  const targetState = {
    sessionId: 'assistant_session_1',
    lazyArtifacts: {}
  }
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
    logger: silentLogger
  })
  targetState.sessionId = 'assistant_session_2'
  resolveFetch({ resources: [spreadsheetResource] })
  await refresh

  assert.equal(applyCount, 0)
  assert.equal(targetState.documentResourceRefresh.appliedVersion, 0)
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
