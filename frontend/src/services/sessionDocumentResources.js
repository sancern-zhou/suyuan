export const mapSessionDocumentResource = (resource = {}) => {
  const locator = resource.locator || {}
  const presentation = resource.presentation || {}
  const preview = presentation.preview || {}
  const format = String(presentation.format || '').toLowerCase()
  const fileType = String(resource.metadata?.file_type || '').toLowerCase()
  const hasPreview = preview && typeof preview === 'object' && Object.keys(preview).length > 0
  let pdfPreview = preview.pdf_preview
  let htmlPreview = preview.html_preview
  let markdownPreview = preview.markdown_preview
  let svgPreview = preview.svg_preview
  let spreadsheetPreview = preview.spreadsheet_preview

  if (hasPreview && !pdfPreview && !htmlPreview && !markdownPreview && !svgPreview && !spreadsheetPreview) {
    if (['xls', 'xlsx', 'xlsm', 'csv', 'ods'].includes(format) || fileType === 'spreadsheet') {
      spreadsheetPreview = preview
    } else if (preview.html_url || preview.html_id || ['html', 'html_artifact', 'image'].includes(fileType)) {
      htmlPreview = preview
    } else if (preview.svg_url || preview.svg_path) {
      svgPreview = preview
    } else if (preview.content || ['md', 'markdown', 'qmd'].includes(format) || fileType === 'markdown') {
      markdownPreview = preview
    } else if (
      preview.pdf_url ||
      preview.pdf_id ||
      preview.pdf_path ||
      ['pdf', 'doc', 'docx'].includes(format) ||
      ['pdf', 'document'].includes(fileType)
    ) {
      pdfPreview = preview
    }
  }

  const pdfId = pdfPreview?.pdf_id || pdfPreview?.pdfId
  const pdfUrl = pdfPreview?.pdf_url || (pdfId
    ? `/api/office/pdf/${encodeURIComponent(pdfId)}`
    : undefined)

  return {
    ...resource,
    file_name: resource.label,
    file_path: locator.path,
    format,
    doc_type: format === 'qmd'
      ? 'report'
      : (format === 'md' || format === 'markdown' ? 'markdown' : undefined),
    pdf_preview: pdfPreview,
    pdf_url: pdfUrl,
    html_preview: htmlPreview,
    html_url: htmlPreview?.html_url,
    markdown_preview: markdownPreview,
    markdown_content: markdownPreview?.content || markdownPreview?.markdown_content,
    svg_preview: svgPreview,
    spreadsheet_preview: spreadsheetPreview
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
