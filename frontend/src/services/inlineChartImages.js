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
