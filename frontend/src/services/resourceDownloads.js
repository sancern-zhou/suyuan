const FORMAT_NAMES = {
  doc: 'DOC',
  docx: 'DOCX',
  html: 'HTML',
  md: 'Markdown',
  pdf: 'PDF',
  qmd: 'QMD',
  xls: 'Excel',
  xlsx: 'Excel'
}

export const formatName = resource => (
  FORMAT_NAMES[String(resource?.format || '').toLowerCase()]
  || String(resource?.format || '文件').toUpperCase()
)

export const downloadFileName = resource => {
  const label = String(resource?.label || 'download')
  const format = String(resource?.format || '').toLowerCase()
  if (!format || label.toLowerCase().endsWith(`.${format}`)) return label
  return `${label}.${format}`
}

export const downloadResource = async resource => {
  if (!resource?.download_url) throw new Error('该资源不支持下载')
  const link = document.createElement('a')
  link.href = resource.download_url
  link.download = downloadFileName(resource)
  document.body.appendChild(link)
  link.click()
  link.remove()
}

export const activeRendition = (group, format) => (
  (group?.resources || []).find(resource => (
    resource.status === 'active'
    && resource.relation === 'rendition'
    && resource.format === format
    && resource.download_url
  )) || null
)
