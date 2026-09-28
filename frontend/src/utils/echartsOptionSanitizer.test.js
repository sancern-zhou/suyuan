import assert from 'node:assert/strict'
import test from 'node:test'

import { ensureEChartsLegend } from './echartsOptionSanitizer.js'

test('named multi-city series gain a bottom legend and grid space', () => {
  const option = {
    xAxis: { type: 'category', data: ['09-27', '09-28'] },
    yAxis: { type: 'value' },
    series: [
      { type: 'line', name: '许昌市', data: [20, 30] },
      { type: 'line', name: '郑州市', data: [25, 35] }
    ]
  }
  ensureEChartsLegend(option)
  assert.deepEqual(option.legend.data, ['许昌市', '郑州市'])
  assert.equal(option.legend.bottom, 35)
  assert.equal(option.grid.bottom, 84)
})

test('explicit hidden legend and unlabeled series remain unchanged', () => {
  const hidden = { xAxis: {}, yAxis: {}, legend: { show: false },
    series: [{ name: 'A' }, { name: 'B' }] }
  ensureEChartsLegend(hidden)
  assert.deepEqual(hidden.legend, { show: false })

  const unnamed = { xAxis: {}, yAxis: {}, series: [{ data: [1] }, { data: [2] }] }
  ensureEChartsLegend(unnamed)
  assert.equal('legend' in unnamed, false)
})
