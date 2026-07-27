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


test('keeps Draw.io resources out of Office preview even when legacy preview fields exist', () => {
  const document = mapSessionDocumentResource({
    locator: { path: '/data/board.drawio' },
    presentation: {
      format: 'drawio',
      preview_type: 'html',
      preview: { html_url: '/api/file/board.html' }
    }
  })

  assert.equal(document.preview_type, 'none')
  assert.equal(document.html_preview, undefined)
  assert.equal(document.html_url, undefined)

  const nestedDocument = mapSessionDocumentResource({
    locator: { path: '/data/legacy-board.drawio' },
    presentation: {
      format: 'drawio',
      preview: {
        html_preview: { html_url: '/api/file/legacy-board.html' }
      }
    }
  })

  assert.equal(nestedDocument.preview_type, 'none')
  assert.equal(nestedDocument.html_preview, undefined)
  assert.equal(nestedDocument.html_url, undefined)
})


test('maps a canonical DOCX resource to a Word PDF preview', () => {
  const document = mapSessionDocumentResource({
    label: '合同',
    locator: { path: '/data/contract.docx' },
    presentation: {
      format: 'docx',
      preview_type: 'pdf',
      preview: { pdf_id: 'word-1', pdf_url: '/api/office/pdf/word-1' }
    }
  })

  assert.equal(document.doc_type, 'word')
  assert.equal(document.pdf_preview.pdf_id, 'word-1')
  assert.equal(document.pdf_url, '/api/office/pdf/word-1')
})


test('maps a canonical native PPTX preview and exposes browser-safe slide URLs', () => {
  const document = mapSessionDocumentResource({
    label: '汇报',
    locator: { path: '/data/deck.pptx' },
    presentation: {
      format: 'pptx',
      preview_type: 'presentation',
      preview: {
        pages: [
          { slide: 1, png_path: '/tmp/deck/page-001.png' },
          { slide: 2, image_url: '/api/presentations/deck/page-002.png' }
        ]
      }
    }
  })

  assert.equal(document.doc_type, 'ppt')
  assert.equal(document.pdf_preview, undefined)
  assert.equal(document.ppt_preview.pages.length, 2)
  assert.deepEqual(document.ppt_preview.pages, [
    { slide: 1, png_path: '/tmp/deck/page-001.png', image_url: '/api/file/%2Ftmp%2Fdeck%2Fpage-001.png' },
    { slide: 2, image_url: '/api/presentations/deck/page-002.png' }
  ])
})


test('keeps PDF as the preferred PPTX preview when the canonical type is PDF', () => {
  const document = mapSessionDocumentResource({
    locator: { path: '/data/deck.pptx' },
    presentation: {
      format: 'pptx',
      preview_type: 'pdf',
      preview: {
        pdf_url: '/api/file/deck.pdf',
        pages: [{ slide: 1, png_path: '/tmp/deck/page-001.png' }]
      }
    }
  })

  assert.equal(document.pdf_url, '/api/file/deck.pdf')
  assert.equal(document.ppt_preview, undefined)
})


test('maps canonical QMD and image preview types without format guessing', () => {
  const report = mapSessionDocumentResource({
    locator: { path: '/data/report.qmd' },
    presentation: {
      format: 'qmd',
      preview_type: 'html',
      preview: { html_url: '/api/reports/report-1' }
    }
  })
  const image = mapSessionDocumentResource({
    locator: { path: '/data/chart.png' },
    presentation: {
      format: 'png',
      preview_type: 'image',
      preview: { html_url: '/api/file/chart.png' }
    }
  })

  assert.equal(report.doc_type, 'report')
  assert.equal(report.html_url, '/api/reports/report-1')
  assert.equal(image.doc_type, 'image')
  assert.equal(image.html_url, '/api/file/chart.png')
})


test('maps generic typed preview URLs from the canonical resource contract', () => {
  const html = mapSessionDocumentResource({
    locator: { path: '/data/report.html' },
    presentation: {
      format: 'html',
      preview: { type: 'html', url: '/api/reports/report-2' }
    }
  })
  const pdf = mapSessionDocumentResource({
    locator: { path: '/data/report.pdf' },
    presentation: {
      format: 'pdf',
      preview: { type: 'pdf', url: '/api/file/report.pdf' }
    }
  })

  assert.equal(html.html_url, '/api/reports/report-2')
  assert.equal(pdf.pdf_url, '/api/file/report.pdf')
})


test('maps legacy native PPTX resources without a preview type', () => {
  const document = mapSessionDocumentResource({
    locator: { path: '/data/legacy.pptx' },
    presentation: {
      format: 'pptx',
      preview: { pages: [{ slide: 1, png_path: '/tmp/legacy/page-001.png' }] }
    }
  })

  assert.equal(document.ppt_preview.pages.length, 1)
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
