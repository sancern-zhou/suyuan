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
    event_attributes: { station_code: '1002A', station_name: '玄武湖站', alarm_type: '断数', severity: 'high' },
    steps: [{ agent_response: '**初判**\n采集链路异常' }]
  })
  assert.equal(item.title, '玄武湖站 · 断数')
  assert.equal(item.status, 'awaiting_review')
  assert.equal(item.summary, '小值已完成初步分析，已整理证据、可能原因和处置建议，等待人工审核。')
})

test('attention item hides internal station codes and rule identifiers', () => {
  const item = executionToAttentionItem({
    execution_id: 'exec-2',
    status: 'running',
    event_attributes: {
      source_type: 'monitoring_anomaly',
      station_code: '1785A',
      station_name: '1785A',
      alarm_type: 'peer_aggregate_deviation,persistent_peer_bias,trend_inconsistency'
    },
    steps: [{ agent_response: '1785A 命中 persistent_peer_bias，等待补充证据。' }]
  })

  assert.equal(item.title, '监测站点 · 监测数据与周边站点对比异常（整体水平偏离、持续偏离、变化趋势不一致）')
  assert.equal(item.summary, '小值正在收集证据并形成初步判断。')
  assert.doesNotMatch(`${item.title}${item.summary}`, /1785A|peer_|trend_/)
})

test('demo attention items are normalized without inventing fields', () => {
  const item = normalizeAttentionItem({ id: 'a', title: '测试', evidence: ['告警记录'] })
  assert.equal(item.severity, 'info')
  assert.deepEqual(item.evidence, ['告警记录'])
})
