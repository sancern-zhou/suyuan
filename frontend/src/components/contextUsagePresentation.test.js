import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CONTEXT_RING_CIRCUMFERENCE,
  buildContextUsageSegments,
  contextUsagePercent,
  formatContextCacheHitRate,
  formatContextTokens,
  normalizeContextBreakdown,
  ringDashOffset
} from './contextUsagePresentation.js'

test('breakdown normalization keeps known sources with positive tokens', () => {
  const rows = normalizeContextBreakdown({
    messages: 4000,
    system_prompt: 3000,
    tools: 800,
    unknown_source: 999,
    empty: 0
  })
  assert.deepEqual(rows.map(row => row.source), ['messages', 'system_prompt', 'tools'])
})

test('breakdown segments are percentages of their own total with tiered colors', () => {
  const segments = buildContextUsageSegments({ messages: 4000, system_prompt: 1000, tools: 1000 })
  assert.deepEqual(segments.map(row => row.source), ['messages', 'system_prompt', 'tools'])
  assert.deepEqual(segments.map(row => row.percent), [0.6666666666666666, 0.16666666666666666, 0.16666666666666666])
  assert.equal(segments[0].color, '#2878ff')
  assert.notEqual(segments[2].color, segments[0].color)
})

test('breakdown segments handle missing or empty breakdowns', () => {
  assert.deepEqual(buildContextUsageSegments(null), [])
  assert.deepEqual(buildContextUsageSegments({}), [])
})

test('context usage percent requires positive usage and window', () => {
  assert.equal(contextUsagePercent(3900, 200000), 2)
  assert.equal(contextUsagePercent(0, 200000), null)
  assert.equal(contextUsagePercent(5000, 0), null)
  assert.equal(contextUsagePercent(1e9, 100), 100)
})

test('ring dash offset maps percent onto circumference', () => {
  assert.equal(ringDashOffset(0), CONTEXT_RING_CIRCUMFERENCE)
  assert.equal(ringDashOffset(null), CONTEXT_RING_CIRCUMFERENCE)
  assert.ok(Math.abs(ringDashOffset(50) - CONTEXT_RING_CIRCUMFERENCE / 2) < 1e-9)
  assert.ok(Math.abs(ringDashOffset(100)) < 1e-9)
})

test('token formatting compacts to K/M without trailing zeros', () => {
  assert.equal(formatContextTokens(880), '880')
  assert.equal(formatContextTokens(3900), '3.9K')
  assert.equal(formatContextTokens(200000), '200K')
  assert.equal(formatContextTokens(1_500_000), '1.5M')
})

test('cache hit rate only surfaces above the display threshold', () => {
  assert.equal(formatContextCacheHitRate(0.9), '90%')
  assert.equal(formatContextCacheHitRate(0.5), null)
  assert.equal(formatContextCacheHitRate(null), null)
})
