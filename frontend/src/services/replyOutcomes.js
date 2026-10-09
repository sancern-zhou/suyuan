import { getUnifiedProcessMessages } from '../components/reactAnalysis/messageProcessGrouping.js'
import { buildResourceGroups, preferredPreview } from './resourceGroups.js'
import { chartReferenceRegex } from './chartReferencePattern.js'

export function replyOutcomes(message, messages, resources) {
  const runs = new Set(), ids = new Set(), ownedGroups = new Set()
  for (const event of [message, ...getUnifiedProcessMessages(message, messages)]) {
    for (const data of [event, event?.data, event?.metadata, event?.data?.result]) {
      if (data?.run_id) runs.add(data.run_id)
      for (const id of [...(data?.resource_ids || []), ...(data?.changed_resource_ids || [])]) ids.add(id)
      for (const run of data?.resource_run_ids || []) runs.add(run)
      for (const group of data?.resource_group_ids || []) ownedGroups.add(group)
    }
    for (const attachment of event?.attachments || []) {
      ids.add(attachment.resource_id || attachment.file_id)
      if (attachment.group_id) ownedGroups.add(attachment.group_id)
    }
  }
  const content = String(message?.content || '')
  const referenced = new Set([...content.matchAll(chartReferenceRegex())].map(match => match[1]))
  const groups = buildResourceGroups(resources.filter(resource => resource.status === 'active'))
  const outcomes = { files: [], others: [] }
  for (const group of groups) {
    if (!ownedGroups.has(group.group_id) && !group.resources.some(r => ids.has(r.resource_id) || (r.run_id && runs.has(r.run_id)))) continue
    if (group.resources.some(r => referenced.has(r.visual_id) || referenced.has(r.resource_id) || (r.content_url && content.includes(r.content_url)))) continue
    const resource = preferredPreview(group)
    if (!resource || !['output', 'report', 'attachment'].includes(resource.role)) continue
    if (resource.kind === 'data' || ['json', 'qmd', 'yaml', 'yml', 'log', 'sql', 'parquet'].includes(resource.format) && resource.renderer !== 'chart') continue
    if (resource.renderer === 'chart' || resource.renderer === 'image') outcomes.others.push({ group, resource })
    else outcomes.files.push({ group, resource })
  }
  return outcomes
}
