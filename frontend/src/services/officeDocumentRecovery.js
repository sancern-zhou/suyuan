const hasOfficePreview = (data = {}) => Boolean(
  data.pdf_preview ||
  data.markdown_preview ||
  data.html_preview ||
  data.svg_preview ||
  data.spreadsheet_preview ||
  data.ppt_preview
)


export const extractOfficeDocumentsFromMessages = (messages = []) => {
  const documents = []

  for (const message of messages) {
    if (message?.type !== 'tool_result') continue
    const result = message.data?.result
    const data = result?.data
    if (!data || !hasOfficePreview(data)) continue

    documents.push({
      pdf_preview: data.pdf_preview,
      markdown_preview: data.markdown_preview,
      html_preview: data.html_preview,
      svg_preview: data.svg_preview,
      spreadsheet_preview: data.spreadsheet_preview,
      ppt_preview: data.ppt_preview,
      file_path: data.file_path || data.path || data.pdf_preview?.pdf_path || data.svg_preview?.svg_path || data.ppt_preview?.pptx_path,
      file_type: data.file_type || data.html_preview?.file_type || data.svg_preview?.file_type,
      related_files: data.related_files,
      artifacts: data.artifacts,
      refs: data.refs,
      assets: data.assets,
      generator: data.generator || result?.metadata?.generator,
      summary: result.summary
    })
  }

  return documents
}
