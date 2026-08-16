import assert from 'node:assert/strict'
import test from 'node:test'

import {
  executionToAttentionItem,
  normalizeAttentionItem,
  normalizeWorkspaceBlocks,
  resolveCoordinatorMode
} from './coordinatorWorkspace.js'

test('workspace accepts only registered block types with unique ids', () => {
  assert.deepEqual(normalizeWorkspaceBlocks([
    { id: 'brief', type: 'briefing', items: [] },
    { id: 'brief', type: 'activity', items: [] },
    { id: 'unsafe', type: 'html', items: [] }
  ]), [{ id: 'brief', type: 'briefing', title: '', items: [] }])
})

test('coordinator routes natural language through configured professional modes', () => {
  const routes = [
    { mode: 'device_control', keywords: ['反控', '空调'] },
    { mode: 'station_fault_diagnosis', keywords: ['断数', '故障'] }
  ]
  assert.equal(resolveCoordinatorMode('帮我诊断站点断数', routes, 'ops'), 'station_fault_diagnosis')
  assert.equal(resolveCoordinatorMode('看看今天情况', routes, 'ops'), 'ops')
})

test('scheduled execution becomes a business attention item', () => {
  const item = executionToAttentionItem({
    execution_id: 'exec-1',
    event_id: 'event-1',
    task_name: '自动诊断',
    status: 'success',
    started_at: '2026-08-16T09:20:00',
    event_attributes: { station_code: '1002A', alarm_type: '断数', severity: 'high' },
    steps: [{ agent_response: '**初判**\n采集链路异常' }]
  })
  assert.equal(item.title, '1002A · 断数')
  assert.equal(item.status, 'awaiting_review')
  assert.match(item.summary, /采集链路异常/)
})

test('demo attention items are normalized without inventing fields', () => {
  const item = normalizeAttentionItem({ id: 'a', title: '测试', evidence: ['告警记录'] })
  assert.equal(item.severity, 'info')
  assert.deepEqual(item.evidence, ['告警记录'])
})
