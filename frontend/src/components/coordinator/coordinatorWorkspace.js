export const COORDINATOR_BLOCK_TYPES = Object.freeze([
  'metric-grid',
  'briefing',
  'attention-list',
  'activity'
])

const blockTypes = new Set(COORDINATOR_BLOCK_TYPES)

const text = value => typeof value === 'string' ? value.trim() : ''

const INTERNAL_ALARM_LABELS = Object.freeze({
  data_missing: '监测数据缺失',
  data_stale: '监测数据停止更新',
  invalid_value: '监测数据出现异常值',
  quality_flag: '监测数据质量标记异常',
  flatline: '监测数据长时间无变化',
  peer_quality_inconsistency: '监测数据与周边站点对比异常'
})

const PEER_ALARM_DETAILS = Object.freeze({
  peer_aggregate_deviation: '整体水平偏离',
  persistent_peer_bias: '持续偏离',
  trend_inconsistency: '变化趋势不一致'
})

function describeAlarmType(value, sourceType = '') {
  const tokens = text(value).split(',').map(item => item.trim()).filter(Boolean)
  const peerDetails = [...new Set(tokens.map(item => PEER_ALARM_DETAILS[item]).filter(Boolean))]
  const labels = tokens
    .filter(item => !PEER_ALARM_DETAILS[item])
    .map(item => INTERNAL_ALARM_LABELS[item] || (/\p{Script=Han}/u.test(item) ? item : ''))
    .filter(Boolean)
  if (peerDetails.length) {
    labels.unshift(`监测数据与周边站点对比异常（${peerDetails.join('、')}）`)
  }
  if (labels.length) return [...new Set(labels)].join('、')
  if (sourceType === 'platform_alarm') return '设备或站房告警'
  if (sourceType === 'monitoring_anomaly') return '监测数据异常'
  return '业务异常待核查'
}

const isInternalStationCode = value => (
  /^(?=.*[a-z])(?=.*\d)[a-z0-9_-]+$/i.test(text(value))
)

const normalizeExecutionSeverity = value => ({
  critical: 'critical',
  high: 'high',
  major: 'high',
  warning: 'medium',
  medium: 'medium',
  low: 'low',
  info: 'info'
}[text(value).toLowerCase()] || 'medium')

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
  const candidateStation = text(attributes.station_name)
  const station = isInternalStationCode(candidateStation) ? '' : candidateStation
  const issue = describeAlarmType(attributes.alarm_type, attributes.source_type)
  const customSummary = text(attributes.summary)
  const running = ['pending', 'running'].includes(execution?.status)
  const failed = ['failed', 'timeout', 'cancelled'].includes(execution?.status)
  return {
    id: execution?.event_id || execution?.execution_id,
    executionId: execution?.execution_id,
    sessionId: execution?.session_id || '',
    title: `${station || '监测站点'} · ${issue}`,
    summary: failed
      ? '自动分析未完成，需要人工查看任务状态并决定后续处理。'
      : (running
          ? '小值正在收集证据并形成初步判断。'
          : (customSummary || '小值已完成初步分析，已整理证据、可能原因和处置建议，等待人工审核。')),
    severity: failed ? 'high' : normalizeExecutionSeverity(attributes.severity),
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
