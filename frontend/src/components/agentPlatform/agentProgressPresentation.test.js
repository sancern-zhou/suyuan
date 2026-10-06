import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatRunningElapsed,
  getAgentProgressStatus,
  getAgentProgressTips,
  selectAgentProgressTip
} from './agentProgressPresentation.js'

test('progress status favors the latest real process event', () => {
  assert.equal(getAgentProgressStatus([], 'query'), '正在准备查询和核验数据')
  assert.equal(getAgentProgressStatus([], 'query_monitoring'), '正在准备查询和核验数据')
  assert.equal(getAgentProgressStatus([{ kind: 'thought' }], 'query'), '正在梳理分析思路')
  assert.equal(getAgentProgressStatus([{ kind: 'tool', toolName: 'execute_sql', status: 'running' }]), '正在查询并核验数据')
  assert.equal(getAgentProgressStatus([{ kind: 'tool', toolName: 'create_report_chart', status: 'running' }]), '正在生成可视化结果')
  assert.equal(getAgentProgressStatus([{ kind: 'tool', toolName: 'unknown_internal_tool', status: 'running' }]), '正在执行分析步骤')
})

test('progress tips are mode-aware and rotate without immediate repetition', () => {
  const queryTips = getAgentProgressTips('query')
  assert.match(queryTips[0], /时间范围/)
  assert.deepEqual(getAgentProgressTips('query_forecast'), queryTips)
  assert.notEqual(selectAgentProgressTip('query', 0, 3), selectAgentProgressTip('query', 1, 3))
  assert.equal(selectAgentProgressTip('query', queryTips.length, 3), selectAgentProgressTip('query', 0, 3))
})

test('running elapsed time stays factual without estimating completion', () => {
  assert.equal(formatRunningElapsed(8.9), '已进行 8 秒')
  assert.equal(formatRunningElapsed(60), '已进行 1 分')
  assert.equal(formatRunningElapsed(75), '已进行 1 分 15 秒')
})
