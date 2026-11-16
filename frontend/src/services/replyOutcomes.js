import { getUnifiedProcessMessages } from '../components/reactAnalysis/messageProcessGrouping.js'
import { buildResourceGroups, preferredPreview } from './resourceGroups.js'
import { chartReferenceRegex } from './chartReferencePattern.js'

// execute_python 对同名文件再次写出时会追加 _<秒级时间戳> 后缀；按去掉该
// 后缀的逻辑文件名合并重复卡片，只保留最新版本。
const VERSIONED_LABEL = /_(\d{9,})(\.[A-Za-z0-9]+)?$/i

const logicalLabel = resource => (
  String(resource?.label || '').replace(VERSIONED_LABEL, '$2').toLowerCase()
)

const versionRank = resource => {
  const updated = Date.parse(resource?.updated_at || '')
  if (Number.isFinite(updated)) return updated
  const suffix = String(resource?.label || '').match(VERSIONED_LABEL)
  return suffix ? Number(suffix[1]) * 1000 : 0
}

// 交互式 HTML 报告（html_artifact / 报告包的 HTML 预览）：目录型产物
// （kind=artifact + entrypoint）的 preview 关系资源，直接内嵌对话区展示，
// 不折叠进“文件成果”。metadata 不外泄（DTO 无该字段），以三字段组合判定。
const isInlineHtmlReport = resource => (
  resource.renderer === 'html'
  && resource.kind === 'artifact'
  && resource.relation === 'preview'
  && resource.format === 'html'
)

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
  const matched = []
  for (const group of groups) {
    if (!ownedGroups.has(group.group_id) && !group.resources.some(r => ids.has(r.resource_id) || (r.run_id && runs.has(r.run_id)))) continue
    if (group.resources.some(r => referenced.has(r.visual_id) || referenced.has(r.resource_id) || (r.content_url && content.includes(r.content_url)))) continue
    const resource = preferredPreview(group)
    if (!resource || !['output', 'report', 'attachment'].includes(resource.role)) continue
    if (resource.kind === 'data' || ['json', 'qmd', 'yaml', 'yml', 'log', 'sql', 'parquet'].includes(resource.format) && resource.renderer !== 'chart') continue
    matched.push({ group, resource })
  }
  const latest = new Map()
  for (const item of matched) {
    const key = logicalLabel(item.resource)
    const current = latest.get(key)
    if (!current || versionRank(item.resource) > current.rank) {
      latest.set(key, { ...item, rank: versionRank(item.resource) })
    }
  }
  const outcomes = { reports: [], files: [], others: [] }
  for (const { group, resource } of latest.values()) {
    if (isInlineHtmlReport(resource)) outcomes.reports.push({ group, resource })
    else if (resource.renderer === 'chart' || resource.renderer === 'image') outcomes.others.push({ group, resource })
    else outcomes.files.push({ group, resource })
  }
  return outcomes
}
