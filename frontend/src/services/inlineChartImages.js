import { getUnifiedProcessMessages, getMessageType } from '../components/reactAnalysis/messageProcessGrouping.js'
import { chartReferenceRegex } from './chartReferencePattern.js'

function interactiveVisualIds(resources) {
  return new Set((resources || [])
    .filter(resource => resource.resource_key === 'chart-spec' && resource.interactive === true)
    .map(resource => resource.visual_id))
}

export function inlineChartImages(finalMessage, messages, resources, content = '') {
  const processMessages = getUnifiedProcessMessages(finalMessage, messages)
  const interactiveIds = interactiveVisualIds(resources)
  processMessages
    .filter(message => message.data?.tool_name === 'execute_echarts_python')
    .flatMap(message => message.data?.result?.visuals || [])
    .forEach(visual => interactiveIds.add(visual.id))
  const imageByVisualId = new Map((resources || [])
    .filter(resource => resource.resource_key === 'chart-image'
      && resource.status === 'active' && !interactiveIds.has(resource.visual_id))
    .map(resource => [resource.visual_id, resource]))
  const seen = new Set()
  // Restored messages omit bulky tool-result visuals. Explicit placeholders
  // still identify their image through the session resource catalog.
  const referencedResources = [...String(content).matchAll(chartReferenceRegex())]
    .map(([, visualId]) => imageByVisualId.get(visualId))
  const hasReportPackage = processMessages.some(message =>
    message.data?.tool_name === 'create_report_package'
  )
  const processResources = processMessages
    .filter(message => getMessageType(message) === 'tool_result'
      && message.data?.tool_name !== 'create_report_package'
      && message.data?.tool_name !== 'execute_echarts_python'
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
  return [...referencedResources, ...processResources]
    .filter(resource => {
      if (!resource?.content_url || seen.has(resource.resource_id)) return false
      seen.add(resource.resource_id)
      return true
    })
}

export function renderChartPlaceholders(content, chartResources, sessionResources = []) {
  const interactiveIds = interactiveVisualIds(sessionResources)
  const byVisualId = new Map((chartResources || []).map(resource => [resource.visual_id, resource]))
  const usedResourceIds = new Set()
  const rendered = String(content ?? '').replace(
    chartReferenceRegex(),
    (placeholder, visualId) => {
      if (interactiveIds.has(visualId)) return ''
      const resource = byVisualId.get(visualId)
      if (!resource?.content_url) return placeholder
      usedResourceIds.add(resource.resource_id)
      const label = String(resource.label || visualId).replace(/[\[\]\\]/g, '')
      return `![${label}](${resource.content_url})`
    }
  )
  return { content: rendered, usedResourceIds }
}
