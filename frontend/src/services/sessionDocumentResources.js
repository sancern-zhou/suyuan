const SPREADSHEET_FORMATS = new Set(['xls', 'xlsx', 'xlsm', 'csv', 'ods'])
const MARKDOWN_FORMATS = new Set(['md', 'markdown', 'qmd'])
const HTML_FORMATS = new Set(['html', 'htm'])
const IMAGE_FORMATS = new Set(['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'])
const PRESENTATION_FORMATS = new Set(['ppt', 'pptx'])
const WORD_FORMATS = new Set(['doc', 'docx'])
const PREVIEW_TYPES = new Set(['none', 'pdf', 'html', 'markdown', 'image', 'spreadsheet', 'presentation'])


const inferPreviewType = ({ presentation, preview, format, fileType }) => {
  if (format === 'drawio') return 'none'
  const explicitType = String(presentation.preview_type || preview.type || '').toLowerCase()
  if (PREVIEW_TYPES.has(explicitType)) return explicitType
  if (!preview || Object.keys(preview).length === 0) return 'none'
  if (preview.pdf_preview || preview.pdf_url || preview.pdf_id || preview.pdf_path || WORD_FORMATS.has(format)) return 'pdf'
  if (preview.spreadsheet_preview || SPREADSHEET_FORMATS.has(format) || fileType === 'spreadsheet') return 'spreadsheet'
  if (IMAGE_FORMATS.has(format) || fileType === 'image') return 'image'
  if (preview.html_preview || preview.html_url || preview.html_id || HTML_FORMATS.has(format) || fileType === 'html_artifact') return 'html'
  if (preview.markdown_preview || preview.content || MARKDOWN_FORMATS.has(format) || fileType === 'markdown') return 'markdown'
  if (PRESENTATION_FORMATS.has(format) && (preview.pages || preview.montage_path)) return 'presentation'
  return 'none'
}


const filePreviewUrl = (path = '') => path ? `/api/file/${encodeURIComponent(path)}` : undefined


export const getPresentationPreviewPages = (preview = {}) => {
  if (!Array.isArray(preview.pages)) return []
  return preview.pages.map((page, index) => ({
    ...page,
    slide: page.slide || page.page_number || index + 1,
    image_url: page.image_url || page.png_url || page.url || filePreviewUrl(page.png_path)
  }))
}


const normalizePresentationPreview = (preview = {}) => ({
  ...preview,
  pages: getPresentationPreviewPages(preview),
  montage_url: preview.montage_url || filePreviewUrl(preview.montage_path)
})


const getDocumentType = (format, fileType) => {
  if (format === 'qmd' || ['report', 'html_report', 'quarto_report'].includes(fileType)) return 'report'
  if (MARKDOWN_FORMATS.has(format)) return 'markdown'
  if (WORD_FORMATS.has(format)) return 'word'
  if (PRESENTATION_FORMATS.has(format)) return 'ppt'
  if (SPREADSHEET_FORMATS.has(format)) return 'excel'
  if (IMAGE_FORMATS.has(format) || fileType === 'image') return 'image'
  if (format === 'pdf' || fileType === 'pdf') return 'pdf'
  if (HTML_FORMATS.has(format) || fileType === 'html_artifact') return fileType === 'html_artifact' ? 'html_artifact' : 'html'
  return undefined
}


export const mapSessionDocumentResource = (resource = {}) => {
  const locator = resource.locator || {}
  const presentation = resource.presentation || {}
  const preview = presentation.preview || {}
  const format = String(presentation.format || '').toLowerCase()
  const fileType = String(resource.metadata?.file_type || '').toLowerCase()
  const hasPreview = preview && typeof preview === 'object' && Object.keys(preview).length > 0
  const previewType = inferPreviewType({ presentation, preview, format, fileType })
  let pdfPreview = preview.pdf_preview
  let htmlPreview = preview.html_preview
  let markdownPreview = preview.markdown_preview
  let svgPreview = preview.svg_preview
  let spreadsheetPreview = preview.spreadsheet_preview
  let pptPreview = preview.ppt_preview

  if (previewType === 'none') {
    pdfPreview = undefined
    htmlPreview = undefined
    markdownPreview = undefined
    svgPreview = undefined
    spreadsheetPreview = undefined
    pptPreview = undefined
  }

  if (hasPreview && !pdfPreview && !htmlPreview && !markdownPreview && !svgPreview && !spreadsheetPreview && !pptPreview) {
    if (previewType === 'pdf') {
      pdfPreview = preview
    } else if (previewType === 'spreadsheet') {
      spreadsheetPreview = preview
    } else if (previewType === 'image' && (preview.svg_url || preview.svg_path)) {
      svgPreview = preview
    } else if (previewType === 'html' || previewType === 'image') {
      htmlPreview = preview
    } else if (previewType === 'markdown') {
      markdownPreview = preview
    } else if (previewType === 'presentation') {
      pptPreview = normalizePresentationPreview(preview)
    }
  }

  const pdfId = pdfPreview?.pdf_id || pdfPreview?.pdfId
  const pdfUrl = pdfPreview?.pdf_url || pdfPreview?.url || (pdfId
    ? `/api/office/pdf/${encodeURIComponent(pdfId)}`
    : undefined)

  return {
    ...resource,
    file_name: resource.label,
    file_path: locator.path,
    format,
    preview_type: previewType,
    doc_type: getDocumentType(format, fileType),
    pdf_preview: pdfPreview,
    pdf_url: pdfUrl,
    html_preview: htmlPreview,
    html_url: htmlPreview?.html_url || htmlPreview?.url,
    markdown_preview: markdownPreview,
    markdown_content: markdownPreview?.content || markdownPreview?.markdown_content,
    svg_preview: svgPreview,
    spreadsheet_preview: spreadsheetPreview,
    ppt_preview: pptPreview
  }
}


export const mapSessionDocumentResources = (resources) => {
  if (!Array.isArray(resources)) return []
  return resources.map(mapSessionDocumentResource)
}


const getRefreshState = (targetState) => {
  if (!targetState.documentResourceRefresh) {
    targetState.documentResourceRefresh = {
      appliedVersion: 0,
      requestedVersion: 0,
      inFlightVersion: null
    }
  }
  return targetState.documentResourceRefresh
}


export const refreshDurableDocumentResources = async ({
  terminalData,
  sessionId,
  targetState,
  fetchDocuments,
  applyDocuments,
  isSessionActive = () => targetState?.sessionId === sessionId,
  logger = console
}) => {
  const version = Number(terminalData?.resource_version)
  if (
    terminalData?.resource_durable !== true ||
    !sessionId ||
    !targetState ||
    !Number.isFinite(version) ||
    version <= 0 ||
    typeof fetchDocuments !== 'function' ||
    typeof applyDocuments !== 'function'
  ) {
    return false
  }

  const refreshState = getRefreshState(targetState)
  if (
    version <= refreshState.appliedVersion ||
    version === refreshState.inFlightVersion ||
    version < refreshState.requestedVersion
  ) {
    return false
  }

  refreshState.requestedVersion = version
  refreshState.inFlightVersion = version
  targetState.lazyArtifacts = {
    ...(targetState.lazyArtifacts || {}),
    loadingOfficeDocuments: true
  }

  try {
    const resources = []
    const seenCursors = new Set()
    let cursor = null
    do {
      const response = await fetchDocuments(sessionId, { cursor, limit: 200 })
      if (!isSessionActive()) return false
      resources.push(...(Array.isArray(response?.resources) ? response.resources : []))
      const nextCursor = response?.next_cursor || null
      if (nextCursor && seenCursors.has(nextCursor)) {
        throw new Error(`repeated document resource cursor: ${nextCursor}`)
      }
      if (nextCursor) seenCursors.add(nextCursor)
      cursor = nextCursor
    } while (cursor)

    if (
      !isSessionActive() ||
      refreshState.requestedVersion !== version
    ) {
      return false
    }

    const documents = mapSessionDocumentResources(resources)
    applyDocuments(documents)
    refreshState.appliedVersion = version
    return true
  } catch (error) {
    if (refreshState.requestedVersion === version) {
      refreshState.requestedVersion = refreshState.appliedVersion
    }
    logger.error('[document-resources] durable refresh failed', {
      sessionId,
      resourceVersion: version,
      error: error?.message || error
    })
    return false
  } finally {
    if (refreshState.inFlightVersion === version) {
      refreshState.inFlightVersion = null
      targetState.lazyArtifacts = {
        ...(targetState.lazyArtifacts || {}),
        loadingOfficeDocuments: false
      }
    }
  }
}
