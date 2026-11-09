import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildFiveMinuteSeries,
  fiveMinuteFlagLabel,
  fiveMinuteTableRows,
  fiveMinuteWindow,
} from './reviewFiveMinuteData.js'

const data = {
  units: { NO: 'μg/m³', NO2: 'μg/m³', CO: 'mg/m³' },
  coverage: {
    query_start: '2026-11-06 00:00:00', query_end: '2026-11-07 23:59:59',
    actual_start: '2026-11-06 00:00:00', actual_end: '2026-11-07T17:35:00',
    default_anchor: { time: '2026-11-07 11:03:40' },
    default_window: ['2026-11-07 07:04:56', '2026-11-07 12:03:40'],
  },
  points_by_pollutant: {
    NO: [
      { time: '2026-11-06T00:00:00', value: 1 },
      { time: '2026-11-07T08:10:00', value: 401, flag: 'PS' },
      { time: '2026-11-07T08:15:00', value: 458, flag: 'PS' },
      { time: '2026-11-07T10:45:00', value: 428, flag: 'PZ' },
      { time: '2026-11-07T11:05:00', value: 2 },
    ],
    NO2: [{ time: '2026-11-07T08:10:00', value: -2, flag: 'PS' }],
    CO: [{ time: '2026-11-07T08:10:00', value: 0.645 }],
  },
  rows: [
    { timePoint: '2026-11-07T08:10:00', no: '401(PS)', nO2: '-2(PS)', co: '0.645' },
    { timePoint: '2026-11-07T10:45:00', no: '428(PZ)', nO2: '12(PZ)' },
    { timePoint: '2026-11-07T11:05:00', no: '2', nO2: '10' },
  ],
}

test('five-minute default window includes first QC failure and later recovery', () => {
  const { series, group, window } = buildFiveMinuteSeries(data, {
    target: 'NO', colorMap: { NO: '#2f86e0', NO2: '#9b8cff' },
  })
  assert.deepEqual(group.members, ['NO', 'NO2'])
  assert.equal(series.length, 2)
  assert.equal(series[0].points.length, 4)
  assert.equal(series[0].points[0].flag, 'PS')
  assert.equal(series[0].color, '#2f86e0')
  assert.equal(series[1].color, '#9b8cff')
  assert.equal(window[0], Date.parse('2026-11-07T07:04:56'))
  assert.equal(window[1], Date.parse('2026-11-07T12:03:40'))
})

test('five-minute full/day windows and flagged-only mode are independent of hour exclusions', () => {
  assert.equal(fiveMinuteWindow(data, 'full')[1], Date.parse('2026-11-07T23:59:59'))
  assert.equal(fiveMinuteWindow(data, 'day')[0], Date.parse('2026-11-07T00:00:00'))
  const { series } = buildFiveMinuteSeries(data, { target: 'NO', flaggedOnly: true })
  assert.deepEqual(series[0].points.filter(point => point.value !== null).map(point => point.flag), ['PS', 'PS', 'PZ'])
  assert.equal(series[0].points[0].value, 401)
  assert.equal(series[0].points.at(-1).value, null)
})

test('CO keeps its own unit and raw table preserves original flags', () => {
  const { series } = buildFiveMinuteSeries(data, { selected: 'CO', target: 'NO' })
  assert.equal(series[0].unit, 'mg/m³')
  const rows = fiveMinuteTableRows(data, ['NO', 'NO2'])
  assert.equal(rows[0].values.NO, '401(PS)')
  assert.equal(fiveMinuteTableRows(data, ['NO'], { flaggedOnly: true }).length, 2)
})

test('missing data and flag labels have explicit empty/unknown behavior', () => {
  assert.deepEqual(fiveMinuteWindow({}, 'handling'), [null, null])
  assert.deepEqual(buildFiveMinuteSeries({}, {}).series, [])
  assert.equal(fiveMinuteFlagLabel('PS'), '跨度检查')
  assert.equal(fiveMinuteFlagLabel('PZ'), '零点检查')
  assert.equal(fiveMinuteFlagLabel('OTHER'), '原始监测标识')
})

test('fault day is independent of later processing day and full window retains the missing tail', () => {
  const crossDay = { ...data, coverage: { ...data.coverage,
    fault_time: '2026-11-06 10:41:30', default_anchor: { time: '2026-11-07 11:03:40' },
  } }
  assert.equal(fiveMinuteWindow(crossDay, 'day')[0], Date.parse('2026-11-06T00:00:00'))
  const full = buildFiveMinuteSeries(data, { target: 'NO', mode: 'full' })
  assert.equal(full.window[1], Date.parse('2026-11-07T23:59:59'))
  assert.ok(full.window[1] > Date.parse(data.coverage.actual_end))
})

test('one-way comparison and flag-only missing observations stay accessible', () => {
  const withOzone = { ...data, points_by_pollutant: { ...data.points_by_pollutant,
    O3: [{ time: '2026-11-07T08:10:00', value: 73 }],
  } }
  const ozone = buildFiveMinuteSeries(withOzone, { selected: 'O3' })
  assert.deepEqual(ozone.series.map(item => item.code), ['O3', 'NO2'])
  assert.notEqual(ozone.series[0].color, ozone.series[1].color)
  const missing = { available_pollutants: ['NO'], rows: [
    { timePoint: '2026-11-07T08:10:00', NO: '--(PS)' },
    { timePoint: '2026-11-07T08:15:00', NO: '-999（PZ）' },
  ] }
  const bundle = buildFiveMinuteSeries(missing, { target: 'NO' })
  assert.deepEqual(bundle.group.members, ['NO'])
  assert.equal(fiveMinuteTableRows(missing, bundle.group.members, { flaggedOnly: true }).length, 2)
})
