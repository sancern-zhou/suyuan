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

const internalIdentifierPattern = /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/gi

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

function sanitizeBusinessSummary(value, attributes) {
  let summary = text(value).replace(/[#*`>\n]+/g, ' ')
  const stationCode = text(attributes.station_code)
  if (stationCode) {
    summary = summary.replaceAll(stationCode, text(attributes.station_name) || '该监测站点')
  }
  summary = summary.replace(internalIdentifierPattern, identifier => (
    INTERNAL_ALARM_LABELS[identifier] || PEER_ALARM_DETAILS[identifier] || '异常规则'
  ))
  return summary.replaceAll('_', ' ').replace(/\s+/g, ' ').trim().slice(0, 150)
}

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
  const station = text(attributes.station_name)
  const issue = describeAlarmType(attributes.alarm_type, attributes.source_type)
  const running = ['pending', 'running'].includes(execution?.status)
  const failed = ['failed', 'timeout', 'cancelled'].includes(execution?.status)
  return {
    id: execution?.event_id || execution?.execution_id,
    executionId: execution?.execution_id,
    sessionId: execution?.session_id || '',
    title: `${station || '监测站点'} · ${issue}`,
    summary: sanitizeBusinessSummary(response, attributes) || (running ? '小值正在收集证据并形成初步判断。' : '自动分析已完成，可进入详情查看完整证据。'),
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
