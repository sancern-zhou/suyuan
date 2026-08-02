const FORMAT_LABELS = {
  doc: 'Word', docx: 'Word', html: 'HTML', md: 'Markdown', pdf: 'PDF',
  png: '图片', jpg: '图片', jpeg: '图片', ppt: 'PPT', pptx: 'PPT',
  xls: 'Excel', xlsx: 'Excel'
}

export function derivativeLabel(resource = {}) {
  const format = String(resource.format || '').toLowerCase()
  const name = FORMAT_LABELS[format] || String(resource.format || '文件').toUpperCase()
  if (resource.relation === 'preview') return `${name} 预览`
  if (resource.relation === 'rendition') return `${name} 导出版`
  return name
}
