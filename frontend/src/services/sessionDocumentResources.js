export const mapSessionDocumentResource = (resource = {}) => {
  const locator = resource.locator || {}
  const presentation = resource.presentation || {}
  const preview = presentation.preview?.pdf_preview || presentation.preview || {}
  const pdfId = preview.pdf_id || preview.pdfId
  const pdfUrl = preview.pdf_url || (pdfId
    ? `/api/office/pdf/${encodeURIComponent(pdfId)}`
    : undefined)
  const format = String(presentation.format || '').toLowerCase()

  return {
    ...resource,
    file_name: resource.label,
    file_path: locator.path,
    format,
    doc_type: format === 'qmd'
      ? 'report'
      : (format === 'md' || format === 'markdown' ? 'markdown' : undefined),
    pdf_preview: preview.pdf_preview || preview,
    pdf_url: pdfUrl,
    html_preview: preview.html_preview,
    html_url: preview.html_url,
    markdown_preview: preview.markdown_preview,
    markdown_content: preview.content || preview.markdown_content,
    svg_preview: preview.svg_preview,
    spreadsheet_preview: preview.spreadsheet_preview
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
    const response = await fetchDocuments(sessionId)
    if (
      targetState.sessionId !== sessionId ||
      refreshState.requestedVersion !== version
    ) {
      return false
    }

    const documents = mapSessionDocumentResources(response?.resources)
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
