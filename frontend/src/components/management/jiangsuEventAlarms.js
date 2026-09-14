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

// 仪器参数告警：解析「XX的值为30.375In-Hg-A，超过限定值【30.000】」
const INSTRUMENT_VALUE_RE = /^(.+?)的值为\s*([+-]?\d+(?:\.\d+)?)\s*([^，]*)/
const BRACKET_LIMIT_RE = /【\s*([+-]?\d+(?:\.\d+)?)\s*】/
// 线索文案：解析「数据：恒值异常（SO2 连续 5 小时几乎不变）」括号内备注
const CLUE_NOTE_RE = /^[^（(）)]*[：:][^（(）)]*[（(](.+)[）)]\s*$/
// 突变线索备注压缩：「PM10 由 56 变为 91」→「PM10 56→91」
const SPIKE_NOTE_RE = /^(.+?)\s*由\s*([+-]?\d+(?:\.\d+)?)\s*变为\s*([+-]?\d+(?:\.\d+)?)$/
const SUBJECT_RE = /^[\w.\-]+/

const timestamp = value => Date.parse(value) || 0
const formatNumber = value => (value == null || Number.isNaN(value)) ? '' : String(value)
const shortNote = note => {
  const spike = String(note).trim().match(SPIKE_NOTE_RE)
  return spike ? `${spike[1].trim()} ${formatNumber(Number(spike[2]))}→${formatNumber(Number(spike[3]))}` : String(note).trim()
}

const parseRow = row => {
  const content = String(row.content || '')
  const instrument = content.match(INSTRUMENT_VALUE_RE)
  const clueNote = content.match(CLUE_NOTE_RE)
  const note = (clueNote?.[1] || content).trim()
  const limit = content.match(BRACKET_LIMIT_RE)?.[1]
  return {
    ...row,
    note,
    object: (instrument?.[1] || (note.match(SUBJECT_RE)?.[0] || '')).trim(),
    value: instrument ? Number(instrument[2]) : null,
    unit: (instrument?.[3] || '').trim(),
    limit: limit != null ? Number(limit) : null,
  }
}

const recurringSummary = rows => {
  const instrument = rows.every(row => row.value != null && row.limit != null && row.object)
  if (!instrument) {
    const notes = [...new Set(rows.map(row => shortNote(row.note)))].filter(Boolean)
    return notes.length ? notes : [`${rows[0].object || rows[0].type} 相关告警 ×${rows.length}`]
  }
  const first = rows[rows.length - 1]
  const last = rows[0]
  const trend = rows.length >= 3 && last.value > first.value ? '，持续走高' : (rows.length >= 3 && last.value < first.value ? '，持续走低' : '')
  const unit = first.unit ? ` ${first.unit}` : ''
  return [`${first.object} ${formatNumber(first.value)}→${formatNumber(last.value)}${unit}（限值 ${formatNumber(first.limit)}${trend}）`]
}

const typeTallies = rows => {
  const counts = new Map()
  for (const row of rows) counts.set(row.type, (counts.get(row.type) || 0) + 1)
  return [...counts.entries()].map(([name, count]) => count > 1 ? `${name} ×${count}` : name).join(' · ')
}

const buildGroup = (kind, rows, title, summaries) => ({
  key: `${kind}:${rows.map(row => row.key).join('|')}`,
  kind,
  count: rows.length,
  title,
  summaries,
  rows,
  startTime: rows[rows.length - 1].time,
  endTime: rows[0].time,
})

// 归组展示：同类型同对象复发合并为一条（含首末值趋势），同时刻多条合并为时刻聚类，其余保持单条。
export function groupAlarmRows(rows) {
  const parsed = (rows || []).map(parseRow)
  const byTimeDesc = (a, b) => timestamp(b.time) - timestamp(a.time)

  const buckets = new Map()
  const clustered = []
  for (const row of parsed) {
    if (!row.object) { clustered.push(row); continue }
    const key = `${row.type}::${row.object}`
    const bucket = buckets.get(key) || []
    bucket.push(row)
    buckets.set(key, bucket)
  }

  const groups = []
  for (const bucket of buckets.values()) {
    const rowsInBucket = [...bucket].sort(byTimeDesc)
    if (rowsInBucket.length < 2) { clustered.push(...rowsInBucket); continue }
    groups.push(buildGroup('recurring', rowsInBucket, rowsInBucket[0].type, recurringSummary(rowsInBucket)))
  }

  const hourBuckets = new Map()
  for (const row of clustered) {
    const stamp = timestamp(row.time)
    const key = stamp ? `hour:${Math.floor(stamp / 3600000)}` : `row:${row.key}`
    const bucket = hourBuckets.get(key) || []
    bucket.push(row)
    hourBuckets.set(key, bucket)
  }
  for (const bucket of hourBuckets.values()) {
    const rowsInBucket = [...bucket].sort(byTimeDesc)
    if (rowsInBucket.length < 2) { groups.push(buildGroup('single', rowsInBucket, rowsInBucket[0].type, [])); continue }
    const typeCount = new Set(rowsInBucket.map(row => row.type)).size
    if (typeCount === 1) {
      groups.push(buildGroup('cluster', rowsInBucket, typeTallies(rowsInBucket),
        [rowsInBucket.map(row => shortNote(row.note)).filter(Boolean).join('、')].filter(Boolean)))
    } else {
      groups.push(buildGroup('cluster', rowsInBucket, typeTallies(rowsInBucket),
        [...new Set(rowsInBucket.map(row => row.type))].map(type => {
          const notes = rowsInBucket.filter(row => row.type === type).map(row => shortNote(row.note)).filter(Boolean)
          return notes.length ? `${type}：${notes.join('；')}` : ''
        }).filter(Boolean)))
    }
  }

  return groups.sort((a, b) => timestamp(b.endTime) - timestamp(a.endTime))
}
