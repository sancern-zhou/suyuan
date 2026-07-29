const hasDocumentPreview = (doc = {}) => {
  return !!(
    doc?.pdf_preview ||
    doc?.markdown_preview ||
    doc?.html_preview ||
    doc?.svg_preview ||
    doc?.spreadsheet_preview ||
    doc?.ppt_preview
  )
}

export const getPanelDocumentIdentity = (doc = {}) => {
  if (!doc || typeof doc !== 'object') return ''

  return doc.file_path ||
    doc.path ||
    doc.pdf_preview?.pdf_id ||
    doc.pdf_preview?.pdf_url ||
    doc.pdf_preview?.pdf_path ||
    doc.html_preview?.html_id ||
    doc.html_preview?.html_url ||
    doc.svg_preview?.svg_url ||
    doc.svg_preview?.svg_path ||
    doc.markdown_preview?.content ||
    ''
}

export const shouldAutoSwitchToDocument = ({ doc, previousDoc, activeTab } = {}) => {
  if (!hasDocumentPreview(doc)) return false

  const nextIdentity = getPanelDocumentIdentity(doc)
  const previousIdentity = getPanelDocumentIdentity(previousDoc)
  const isReplay = !!nextIdentity && !!previousIdentity && nextIdentity === previousIdentity

  if (isReplay) return false
  if (activeTab === 'board' && previousDoc && isReplay) return false

  return true
}
