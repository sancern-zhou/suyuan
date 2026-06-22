import assert from 'node:assert/strict'
import test from 'node:test'

import {
  extractDashboardFocusFromMessages,
  normalizeDashboardFocus,
  normalizeLayerState
} from './dashboardFocus.js'

test('normalizeDashboardFocus fills stable defaults', () => {
  const focus = normalizeDashboardFocus({
    scope: 'city',
    cities: '广州',
    pollutants: ['O3_8h'],
    layer_state: { heatmap: true }
  })

  assert.equal(focus.scope, 'city')
  assert.deepEqual(focus.cities, ['广州'])
  assert.deepEqual(focus.stations, [])
  assert.deepEqual(focus.pollutants, ['O3_8h'])
  assert.deepEqual(focus.layer_state, { city_metrics: false, stations: false, heatmap: true })
})

test('extractDashboardFocusFromMessages prefers latest final message metadata', () => {
  const messages = [
    { type: 'final', data: { dashboard_focus: { scope: 'province' } } },
    { type: 'tool_result', data: { result: { dashboard_focus: { scope: 'station', stations: ['麓湖'] } } } },
    { type: 'final', data: { dashboard_focus: { scope: 'city', cities: ['广州'] } } }
  ]

  const focus = extractDashboardFocusFromMessages(messages)

  assert.equal(focus.scope, 'city')
  assert.deepEqual(focus.cities, ['广州'])
})

test('normalizeLayerState only enables known layers', () => {
  assert.deepEqual(
    normalizeLayerState({ city_metrics: true, unknown: true }),
    { city_metrics: true, stations: false, heatmap: false }
  )
})
