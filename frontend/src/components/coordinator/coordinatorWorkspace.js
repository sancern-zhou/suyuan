export const COORDINATOR_BLOCK_TYPES = Object.freeze([
  'metric-grid',
  'briefing',
  'attention-list',
  'activity'
])

const blockTypes = new Set(COORDINATOR_BLOCK_TYPES)

const text = value => typeof value === 'string' ? value.trim() : ''

export function normalizeWorkspaceBlocks(blocks = []) {
  const ids = new Set()
  return blocks.flatMap((block, index) => {
    if (!block || !blockTypes.has(block.type)) return []
    const id = text(block.id) || `block-${index + 1}`
    if (ids.has(id)) return []
    ids.add(id)
    return [{
      id,
      type: block.type,
      title: text(block.title),
      items: Array.isArray(block.items) ? block.items.filter(Boolean) : []
    }]
  })
}

export function resolveCoordinatorMode(query, routes = [], fallbackMode = 'assistant') {
  const normalizedQuery = text(query).toLocaleLowerCase('zh-CN')
  const route = routes.find(item => (
    item?.mode &&
    Array.isArray(item.keywords) &&
    item.keywords.some(keyword => normalizedQuery.includes(text(keyword).toLocaleLowerCase('zh-CN')))
  ))
  return route?.mode || fallbackMode
}

export function executionToAttentionItem(execution) {
  const attributes = execution?.event_attributes || {}
  const response = execution?.steps?.find(step => step?.agent_response)?.agent_response || ''
  const station = attributes.station_name || attributes.station_code || ''
  const running = ['pending', 'running'].includes(execution?.status)
  const failed = ['failed', 'timeout', 'cancelled'].includes(execution?.status)
  return {
    id: execution?.event_id || execution?.execution_id,
    executionId: execution?.execution_id,
    sessionId: execution?.session_id || '',
    title: station ? `${station} · ${attributes.alarm_type || '异常事件'}` : (execution?.task_name || '自动分析任务'),
    summary: text(response).replace(/[#*_`>\n]+/g, ' ').slice(0, 150) || (running ? '小值正在收集证据并形成初步判断。' : '自动分析已完成，可进入详情查看完整证据。'),
    severity: failed ? 'high' : (attributes.severity || 'medium'),
    status: failed ? 'needs_attention' : (running ? 'analyzing' : 'awaiting_review'),
    station,
    occurredAt: execution?.started_at || '',
    diagnosis: '',
    confidence: '',
    evidence: [],
    live: true,
    taskId: execution?.task_id || ''
  }
}
export function normalizeAttentionItem(item, index = 0) {
  if (!item) return null
  return {
    id: text(item.id) || `attention-${index + 1}`,
    title: text(item.title) || '待关注事项',
    summary: text(item.summary),
    severity: ['critical', 'high', 'medium', 'low', 'info'].includes(item.severity) ? item.severity : 'info',
    status: text(item.status) || 'new',
    station: text(item.station),
    occurredAt: item.occurredAt || item.occurred_at || '',
    diagnosis: text(item.diagnosis),
    confidence: text(item.confidence),
    evidence: Array.isArray(item.evidence) ? item.evidence.map(text).filter(Boolean) : [],
    actions: Array.isArray(item.actions) ? item.actions.filter(action => action?.label) : [],
    sessionId: text(item.sessionId || item.session_id),
    taskId: text(item.taskId || item.task_id),
    live: item.live === true
  }
}
