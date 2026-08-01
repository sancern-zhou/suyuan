const SUPPORTED = new Set([
  'pdf', 'html', 'markdown', 'spreadsheet', 'presentation',
  'image', 'chart', 'board', 'file'
])

export const rendererKey = (resource = {}) => {
  if (resource.status && resource.status !== 'active') return 'file'
  return SUPPORTED.has(resource.renderer) ? resource.renderer : 'file'
}

export const RESOURCE_RENDERERS = Object.freeze({
  pdf: () => import('../components/resources/renderers/PdfResourceRenderer.vue'),
  html: () => import('../components/resources/renderers/HtmlResourceRenderer.vue'),
  markdown: () => import('../components/resources/renderers/MarkdownResourceRenderer.vue'),
  spreadsheet: () => import('../components/resources/renderers/SpreadsheetResourceRenderer.vue'),
  presentation: () => import('../components/resources/renderers/PresentationResourceRenderer.vue'),
  image: () => import('../components/resources/renderers/ImageResourceRenderer.vue'),
  chart: () => import('../components/resources/renderers/ChartResourceRenderer.vue'),
  board: () => import('../components/resources/renderers/BoardResourceRenderer.vue'),
  file: () => import('../components/resources/renderers/FileDetailRenderer.vue')
})
