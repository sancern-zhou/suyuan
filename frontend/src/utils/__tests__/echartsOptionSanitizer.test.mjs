import assert from 'node:assert/strict'
import { cloneEChartsOption, sanitizeCompleteRadarOption } from '../echartsOptionSanitizer.js'

const option = {
  title: { text: '雷达图' },
  radar: {
    indicator: [
      { name: 'PM2.5', max: 60 },
      { name: 'PM10', max: 80 }
    ]
  },
  grid: { top: 60 },
  xAxis: { type: 'category', data: ['A', 'B'] },
  yAxis: [
    { type: 'value', min: 0, max: 60, alignTicks: true },
    { type: 'value', min: 0, max: 80, alignTicks: true }
  ],
  dataZoom: [{ type: 'inside' }],
  series: [
    {
      name: '站点A',
      type: 'radar',
      data: [{ value: [20, 30], name: '站点A' }]
    }
  ]
}

const sanitized = sanitizeCompleteRadarOption(option)

assert.equal(sanitized.radar, option.radar)
assert.equal(sanitized.series, option.series)
assert.equal('xAxis' in sanitized, false)
assert.equal('yAxis' in sanitized, false)
assert.equal('grid' in sanitized, false)
assert.equal('dataZoom' in sanitized, false)
assert.equal('xAxis' in option, true)
assert.equal('yAxis' in option, true)

const nestedOption = {
  baseOption: option,
  options: [
    {
      xAxis: { type: 'category' },
      yAxis: { type: 'value', min: 0, max: 4, alignTicks: true },
      radar: { indicator: [{ name: 'NO2', max: 4 }] },
      series: [{ type: 'radar', data: [{ value: [1] }] }]
    }
  ]
}

const sanitizedNested = sanitizeCompleteRadarOption(nestedOption)

assert.equal('xAxis' in sanitizedNested.baseOption, false)
assert.equal('yAxis' in sanitizedNested.baseOption, false)
assert.equal('xAxis' in sanitizedNested.options[0], false)
assert.equal('yAxis' in sanitizedNested.options[0], false)

const withFormatter = {
  tooltip: {
    formatter: value => value
  },
  radar: {
    center: ['50%', '60%']
  },
  series: [{ type: 'radar', data: [{ value: [1] }] }]
}

const cloned = cloneEChartsOption(withFormatter)
cloned.radar.center = ['50%', '65%']

assert.notEqual(cloned, withFormatter)
assert.notEqual(cloned.radar, withFormatter.radar)
assert.notEqual(cloned.series, withFormatter.series)
assert.equal(cloned.tooltip.formatter, withFormatter.tooltip.formatter)
assert.deepEqual(withFormatter.radar.center, ['50%', '60%'])

console.log('echartsOptionSanitizer tests passed')
