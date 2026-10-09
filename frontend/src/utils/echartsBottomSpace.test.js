import assert from 'node:assert/strict'
import test from 'node:test'

import {
  estimateLegendHeight,
  estimateTextWidth,
  estimateXAxisLabelHeight
} from './echartsBottomSpace.js'

test('rotated time labels need far more than the 24px fallback', () => {
  const axis = {
    type: 'time',
    axisLabel: { rotate: 45, fontSize: 12 }
  }
  const series = [{ type: 'line', data: [['2026-10-09 10:00:00', 1], ['2026-10-10 11:00:00', 2]] }]
  const height = estimateXAxisLabelHeight(axis, series)
  assert.ok(height > 60, `expected > 60, got ${height}`)
})

test('horizontal short category labels keep the 24px fallback', () => {
  const axis = { type: 'category', data: ['1月', '2月', '3月'] }
  assert.equal(estimateXAxisLabelHeight(axis), 24)
})

test('explicit hidden labels reserve nothing', () => {
  const axis = { type: 'category', data: ['a', 'b'], axisLabel: { show: false } }
  assert.equal(estimateXAxisLabelHeight(axis), 0)
})

test('wrapped labels (width + overflow break) count lines', () => {
  const axis = {
    type: 'category',
    data: ['许昌市建安区监测站点', '郑州市中原区站点'],
    axisLabel: { width: 60, overflow: 'break', fontSize: 12 }
  }
  const height = estimateXAxisLabelHeight(axis)
  assert.ok(height > 24, `expected wrapped height > 24, got ${height}`)
})

test('long legend names wrap into multiple rows on narrow containers', () => {
  const option = {
    series: [
      { name: '许昌市国控站点PM2.5浓度', type: 'line' },
      { name: '郑州市国控站点PM2.5浓度', type: 'line' },
      { name: '开封市国控站点PM2.5浓度', type: 'line' },
      { name: '洛阳市国控站点PM2.5浓度', type: 'line' }
    ]
  }
  const singleRow = estimateLegendHeight(option.legend ?? {}, option, 1000)
  const narrow = estimateLegendHeight({}, option, 320)
  assert.ok(narrow > 25, `expected multi-row legend > 25, got ${narrow}`)
  assert.ok(narrow > singleRow, 'narrow container should need more legend rows')
})

test('scroll legend stays a single row', () => {
  const option = {
    legend: { type: 'scroll' },
    series: [{ name: '超长名称'.repeat(20), type: 'line' }]
  }
  assert.ok(estimateLegendHeight(option.legend, option, 300) <= 25)
})

test('estimateTextWidth treats CJK as full-width', () => {
  assert.equal(estimateTextWidth('ab', 10), 12)
  assert.equal(estimateTextWidth('中文', 10), 20)
})
