import { getUnifiedProcessMessages, getMessageType } from '../components/reactAnalysis/messageProcessGrouping.js'

export function inlineChartImages(finalMessage, messages, resources) {
  const imageByVisualId = new Map((resources || [])
    .filter(resource => resource.resource_key === 'chart-image' && resource.status === 'active')
    .map(resource => [resource.visual_id, resource]))
  const seen = new Set()
  return getUnifiedProcessMessages(finalMessage, messages)
    .filter(message => getMessageType(message) === 'tool_result'
      && message.data?.tool_name === 'execute_echarts_python')
    .flatMap(message => message.data?.result?.visuals || [])
    .map(visual => imageByVisualId.get(visual.id))
    .filter(resource => {
      if (!resource?.content_url || seen.has(resource.resource_id)) return false
      seen.add(resource.resource_id)
      return true
    })
}

export function renderChartPlaceholders(content, chartResources) {
  const byVisualId = new Map((chartResources || []).map(resource => [resource.visual_id, resource]))
  const usedResourceIds = new Set()
  const rendered = String(content ?? '').replace(
    /\[\[chart:([A-Za-z0-9_-]{1,100})\]\]/g,
    (placeholder, visualId) => {
      const resource = byVisualId.get(visualId)
      if (!resource?.content_url) return placeholder
      usedResourceIds.add(resource.resource_id)
      const label = String(resource.label || visualId).replace(/[\[\]\\]/g, '')
      return `![${label}](${resource.content_url})`
    }
  )
  return { content: rendered, usedResourceIds }
}
