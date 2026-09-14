import assert from 'node:assert/strict'
import test from 'node:test'
import { eventAlarmRows, groupAlarmRows } from './jiangsuEventAlarms.js'

test('merged alarms show full content newest first without duplicating the primary record or tags', () => {
  const long = '完整告警内容'.repeat(100)
  const early = { id: 1, alarmtime: '2026-09-09T08:00:00+08:00', content: long }
  const late = { alarmId: 2, alarmTime: '2026-09-09T15:00:00+08:00', alarmContent: '后续告警', ruleType: '供电报警' }
  const rows = eventAlarmRows({ evidence: { alarm: early, alarms: [early, late] },
    clue_tags: [{ clue_id: '1', tag_source: '子站报警', tag_display_text: '截断摘要' }] })
  assert.equal(rows.length, 2)
  assert.equal(rows[0].content, '后续告警')
  assert.equal(rows[0].type, '供电报警')
  assert.equal(rows[1].content, long)
})

test('equal contents from different alarms remain separate', () => {
  assert.equal(eventAlarmRows({ evidence: { alarms: [{ id: 1, content: '断数' }, { id: 2, content: '断数' }] } }).length, 2)
})

test('legacy events fall back to retained alarm clues or single content', () => {
  assert.equal(eventAlarmRows({ clue_tags: [{ tag_id: 'a', tag_category: '报警', tag_display_text: '历史告警' }] })[0].content, '历史告警')
  assert.equal(eventAlarmRows({ alarm_content: '旧内容' })[0].content, '旧内容')
  assert.deepEqual(eventAlarmRows(null), [])
  assert.deepEqual(eventAlarmRows({}), [])
})

const pressureAlarm = (id, hour, value) => ({
  id, alarmtime: `2026-09-14T${hour}:00:00+08:00`, ddRuleType: '仪器状态超上下限报警',
  content: `NO2-API-M200-采样压力的值为${value}In-Hg-A，超过限定值【30.000】`,
})
const clueTag = (id, name, text, hour) => ({
  clue_id: id, tag_name: name, tag_display_text: text, tag_start_time: `2026-09-14T${hour}:00:00+08:00`,
})

const bucketEvent = () => ({
  evidence: { alarms: [
    pressureAlarm(1, '17', '30.050'), pressureAlarm(2, '18', '30.017'), pressureAlarm(3, '19', '30.142'),
    pressureAlarm(4, '20', '30.242'), pressureAlarm(5, '21', '30.267'), pressureAlarm(6, '22', '30.375'),
  ] },
  clue_tags: [
    clueTag('c1', '浓度超限', '超限：浓度超限（PM2.5 最高 87 超过阈值 75）', '17'),
    clueTag('c2', '恒值异常', '数据：恒值异常（SO2 连续 5 小时几乎不变）', '17'),
    clueTag('c3', '恒值异常', '数据：恒值异常（CO 连续 7 小时几乎不变）', '17'),
    clueTag('c4', '数据突升', '数据：数据突升（PM10 由 56 变为 91）', '07'),
    clueTag('c5', '数据突升', '数据：数据突升（PM2.5 由 50 变为 80）', '07'),
    clueTag('c6', '数据突升', '数据：数据突升（SO2 由 6 变为 17）', '07'),
    clueTag('c7', '数据突降', '数据：数据突降（NO2 由 71 变为 46）', '03'),
    clueTag('c8', '数据突升', '数据：数据突升（O3 由 6 变为 25）', '03'),
  ],
})

test('recurring instrument alarms collapse into one group with first/last values and limit', () => {
  const groups = groupAlarmRows(eventAlarmRows(bucketEvent()))
  const recurring = groups.find(group => group.kind === 'recurring')
  assert.equal(recurring.count, 6)
  assert.equal(recurring.title, '仪器状态超上下限报警')
  assert.equal(recurring.endTime, '2026-09-14T22:00:00+08:00')
  assert.equal(recurring.startTime, '2026-09-14T17:00:00+08:00')
  assert.equal(recurring.summaries.length, 1)
  assert.equal(recurring.summaries[0], 'NO2-API-M200-采样压力 30.05→30.375 In-Hg-A（限值 30，持续走高）')
  assert.equal(recurring.rows.length, 6)
})

test('same-hour clues cluster with type tallies and shortened spike notes', () => {
  const groups = groupAlarmRows(eventAlarmRows(bucketEvent()))
  const spike = groups.find(group => group.endTime === '2026-09-14T07:00:00+08:00')
  assert.equal(spike.kind, 'cluster')
  assert.equal(spike.title, '数据突升 ×3')
  assert.deepEqual(spike.summaries, ['PM10 56→91、PM2.5 50→80、SO2 6→17'])
  const mixed = groups.find(group => group.endTime === '2026-09-14T03:00:00+08:00')
  assert.equal(mixed.title, '数据突降 · 数据突升')
  assert.deepEqual(mixed.summaries, ['数据突降：NO2 71→46', '数据突升：O3 6→25'])
  const mixedHour = groups.find(group => group.endTime === '2026-09-14T17:00:00+08:00')
  assert.equal(mixedHour.title, '浓度超限 · 恒值异常 ×2')
  assert.deepEqual(mixedHour.summaries, ['浓度超限：PM2.5 最高 87 超过阈值 75', '恒值异常：SO2 连续 5 小时几乎不变；CO 连续 7 小时几乎不变'])
})

test('grouping keeps every original row and leaves unrelated alarms as singles', () => {
  const rows = eventAlarmRows(bucketEvent())
  const groups = groupAlarmRows(rows)
  assert.equal(groups.length, 4)
  assert.equal(groups.reduce((sum, group) => sum + group.count, 0), rows.length)
  assert.equal(groups[0].endTime, '2026-09-14T22:00:00+08:00')
  const scattered = groupAlarmRows(eventAlarmRows({ evidence: { alarms: [
    { id: 1, alarmtime: '2026-09-14T06:00:00+08:00', content: '零星告警甲', ddRuleType: '其他报警' },
    { id: 2, alarmtime: '2026-09-14T09:00:00+08:00', content: '零星告警乙', ddRuleType: '其他报警' },
  ] } }))
  assert.deepEqual(scattered.map(group => group.kind), ['single', 'single'])
  assert.deepEqual(groupAlarmRows([]), [])
})
