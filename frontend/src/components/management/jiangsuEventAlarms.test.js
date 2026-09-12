import assert from 'node:assert/strict'
import test from 'node:test'
import { eventAlarmRows } from './jiangsuEventAlarms.js'

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
