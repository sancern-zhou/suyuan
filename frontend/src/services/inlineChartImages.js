import { getUnifiedProcessMessages, getMessageType } from '../components/reactAnalysis/messageProcessGrouping.js'

export function inlineChartImages(finalMessage, messages, resources, content = '') {
  const imageByVisualId = new Map((resources || [])
    .filter(resource => resource.resource_key === 'chart-image' && resource.status === 'active')
    .map(resource => [resource.visual_id, resource]))
  const seen = new Set()
  const processMessages = getUnifiedProcessMessages(finalMessage, messages)
  const hasReportPackage = processMessages.some(message =>
    message.data?.tool_name === 'create_report_package'
  )
  return processMessages
    .filter(message => getMessageType(message) === 'tool_result'
      && message.data?.tool_name !== 'create_report_package'
      && Array.isArray(message.data?.result?.visuals))
    .flatMap(message => message.data?.result?.visuals || [])
    .filter(visual => visual?.id && (
      !hasReportPackage || content.includes(`[[chart:${visual.id}]]`)
    ))
    .map(visual => ({ visual, resource: imageByVisualId.get(visual.id) }))
    .filter(({ visual, resource }) =>
      !(visual.image_url && content.includes(visual.image_url))
      && !(resource?.content_url && content.includes(resource.content_url))
    )
    .map(({ resource }) => resource)
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
