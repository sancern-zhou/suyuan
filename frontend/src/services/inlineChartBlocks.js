// A chart reference is layout information, not executable HTML or JavaScript.
import { chartReferenceRegex } from './chartReferencePattern.js'

export function inlineChartBlocks(content, resources = []) {
  const byId = new Map(resources.filter(r => r.resource_key === 'chart-spec' && r.interactive === true && r.status === 'active')
    .flatMap(r => [[r.visual_id, r], [r.resource_id, r]]))
  const blocks = []
  const text = String(content ?? '')
  let start = 0
  for (const match of text.matchAll(chartReferenceRegex())) {
    const resource = byId.get(match[1])
    if (!resource?.content_url) continue
    if (match.index > start) blocks.push({ kind: 'text', content: text.slice(start, match.index) })
    blocks.push({ kind: 'chart', resource })
    start = match.index + match[0].length
  }
  if (start < text.length || !blocks.length) blocks.push({ kind: 'text', content: text.slice(start) })
  return blocks
}
