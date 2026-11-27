import MarkdownIt from 'markdown-it'
import markdownItKatex from '@traptitech/markdown-it-katex'
import markdownItMultimdTable from 'markdown-it-multimd-table'

const CHART_REFERENCE = /\[\[chart:([0-9a-f]{32})\]\]/y

// Let Markdown-It consume code fences, inline code, escapes and link destinations
// before interpreting chart references in ordinary Markdown content.
function chartReference(state, silent) {
  if (!state.env.chartReferences || state.linkLevel || state.src[state.pos] !== '[') return false
  CHART_REFERENCE.lastIndex = state.pos
  const match = CHART_REFERENCE.exec(state.src)
  if (!match || CHART_REFERENCE.lastIndex > state.posMax) return false
  if (!silent) {
    const token = state.push('chart_reference', '', 0)
    token.content = match[0]
    token.meta = { resourceId: match[1] }
  }
  state.pos += match[0].length
  return true
}

export function createChartMarkdown() {
  const md = new MarkdownIt({ html: true, linkify: true, typographer: true })
    .use(markdownItMultimdTable, { multiline: true, rowspan: true, headerless: true })
    .use(markdownItKatex, { throwOnError: false, errorColor: '#cc0000' })
  md.inline.ruler.before('link', 'chart_reference', chartReference)
  return md
}

const referenceParser = createChartMarkdown()

export function chartReferenceIds(content) {
  if (!content.includes('[[chart:')) return []
  const tokens = referenceParser.parse(content, { chartReferences: true })
  return tokens.flatMap(token => (token.children || [])
    .filter(child => child.type === 'chart_reference')
    .map(child => child.meta.resourceId))
}
