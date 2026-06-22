import assert from 'node:assert/strict'
import test from 'node:test'

import {
  extractDashboardFocusFromMessages,
  normalizeDashboardFocus,
  normalizeLayerState
} from './dashboardFocus.js'
import { fetchGuangdongOverview } from '../../api/queryDashboard.js'

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

test('normalizeDashboardFocus tolerates null input', () => {
  const focus = normalizeDashboardFocus(null)

  assert.equal(focus.scope, 'province')
  assert.deepEqual(focus.cities, [])
  assert.deepEqual(focus.stations, [])
  assert.deepEqual(focus.pollutants, [])
  assert.equal(focus.time_range, null)
  assert.deepEqual(focus.modules, [])
  assert.deepEqual(focus.layer_state, { city_metrics: false, stations: false, heatmap: false })
  assert.deepEqual(focus.source_data_ids, [])
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

test('extractDashboardFocusFromMessages reads final message metadata focus', () => {
  const focus = extractDashboardFocusFromMessages([
    { type: 'final', data: { metadata: { dashboard_focus: { scope: 'city', cities: ['深圳'] } } } }
  ])

  assert.equal(focus.scope, 'city')
  assert.deepEqual(focus.cities, ['深圳'])
})

test('normalizeLayerState only enables known layers', () => {
  assert.deepEqual(
    normalizeLayerState({ city_metrics: true, unknown: true }),
    { city_metrics: true, stations: false, heatmap: false }
  )
})

test('fetchGuangdongOverview only sends include query option', async () => {
  const originalFetch = globalThis.fetch
  let requestedUrl
  globalThis.fetch = async (url) => {
    requestedUrl = url
    return {
      ok: true,
      async json () {
        return { ok: true }
      }
    }
  }

  try {
    await fetchGuangdongOverview({ include: ['cities'], forceRefresh: true })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(requestedUrl, '/api/query-dashboard/guangdong-overview?include=cities')
})
