// Use original alarm records so merged contents are never truncated to chip labels.
export function eventAlarmRows(event) {
  if (!event) return []
  const first = (record, keys) => keys.map(key => record[key]).find(value => value != null && String(value).trim() !== '')
  const rows = new Map()
  const records = [...(Array.isArray(event.evidence?.alarms) ? event.evidence.alarms : []), event.evidence?.alarm]
  for (const record of records) {
    if (!record || typeof record !== 'object') continue
    const id = first(record, ['id', 'alarmId', 'callId'])
    const time = first(record, ['alarmtime', 'alarmTime', 'timePoint', 'createTime', 'occurredAt']) || ''
    const content = String(first(record, ['content', 'alarmContent', 'description']) || '')
    const type = first(record, ['ddRuleType', 'ddruletype', 'ruleType']) || '平台告警'
    const key = id != null ? String(id) : JSON.stringify([time, type, content])
    if (!rows.has(key)) rows.set(key, { key, time, type, content: content || '暂无具体告警内容' })
  }
  for (const tag of event.clue_tags || []) {
    if (!tag) continue
    const key = String(tag.clue_id || tag.tag_id || tag.tag_name)
    if (!rows.has(key)) rows.set(key, {
      key, time: tag.tag_start_time || '', type: tag.tag_name || '线索',
      content: tag.alarm_content || tag.tag_display_text || tag.tag_object || '暂无具体告警内容',
    })
  }
  if (!rows.size && event.alarm_content) rows.set('legacy', {
    key: 'legacy', time: event.event_start_time || '',
    type: event.source_alarm_rule_type || '平台告警', content: event.alarm_content,
  })
  const timestamp = value => Date.parse(value) || 0
  return [...rows.values()].sort((a, b) => timestamp(b.time) - timestamp(a.time))
}
