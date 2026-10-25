import test from 'node:test'
import assert from 'node:assert/strict'
import {
  areaPollutant,
  buildPollutantCharts,
  finiteObservation,
  hexWithAlpha,
  observationValue,
  normalizeReviewPoints
} from './reviewTimeSeriesData.js'

test('empty observations stay null while real zero is preserved', () => {
  for (const raw of [null, undefined, '', '  ', '--', NaN, Infinity, false, [], {}]) {
    assert.equal(finiteObservation(raw), null)
  }
  assert.equal(finiteObservation(0), 0)
  assert.equal(finiteObservation('0'), 0)
  assert.equal(finiteObservation(' 12.5 '), 12.5)
  assert.equal(observationValue({ pM10: null, value: 9 }, ['pM10', 'value']), null)
  assert.equal(observationValue({ value: 9 }, ['pM10', 'value']), 9)
})

for (const [granularity, times] of [
  ['5min', ['00:00', '00:05', '00:10', '00:15']],
  ['hour', ['00:00', '01:00', '02:00', '03:00']]
]) {
  test(`${granularity} retains explicit nulls and fills absent timestamps`, () => {
    const result = normalizeReviewPoints([
      { time: `2026-09-01 ${times[3]}:00`, value: 20 },
      { time: `2026-09-01 ${times[0]}:00`, value: 0 },
      { time: `2026-09-01 ${times[1]}:00`, value: null }
    ], granularity)
    assert.deepEqual(result.map(point => point[1]), [0, null, null, 20])
    assert.equal(result[2][0], Date.parse(`2026-09-01T${times[2]}:00`))
  })
}

test('each comparison station gets its own gaps', () => {
  const stationA = normalizeReviewPoints([
    { time: '2026-09-01 00:00:00', value: 10 },
    { time: '2026-09-01 02:00:00', value: 12 }
  ], 'hour')
  const stationB = normalizeReviewPoints([
    { time: '2026-09-01 00:00:00', value: 20 },
    { time: '2026-09-01 01:00:00', value: 21 },
    { time: '2026-09-01 02:00:00', value: 22 }
  ], 'hour')
  assert.deepEqual(stationA.map(point => point[1]), [10, null, 12])
  assert.deepEqual(stationB.map(point => point[1]), [20, 21, 22])
})

test('irregular QC series is not assigned an invented cadence', () => {
  assert.equal(normalizeReviewPoints([
    { time: '2026-09-01 00:00:00', value: 1 },
    { time: '2026-09-01 00:23:00', value: 2 }
  ]).length, 2)
})

test('mark area pollutant comes from explicit field or legacy name prefix', () => {
  assert.equal(areaPollutant({ pollutant: 'pm10', name: '任意名' }), 'PM10')
  assert.equal(areaPollutant({ name: 'NO2剔除区间' }), 'NO2')
  assert.equal(areaPollutant({ name: '剔除候选' }), '')
  assert.equal(areaPollutant(null), '')
})

test('hex colors convert to translucent rgba and junk falls back to null', () => {
  assert.equal(hexWithAlpha('#2f86e0', 0.14), 'rgba(47, 134, 224, 0.14)')
  assert.equal(hexWithAlpha('#2F86E0'), 'rgba(47, 134, 224, 0.14)')
  for (const bad of [null, '', 'rgba(1,2,3,.5)', '#2f86e', 'yellow']) {
    assert.equal(hexWithAlpha(bad), null)
  }
})

const _hour = (time, value) => ({ time: `2026-09-14 ${time}:00`, value })

test('single-pollutant package keeps one chart with target, comparison and band overlays', () => {
  const { charts, colorMap, stationPollutantSeries } = buildPollutantCharts({
    data: {
      pollutant: 'PM10', comparison_pollutant: 'PM2.5', unit: 'μg/m³',
      points: [_hour('10:00', 82), _hour('11:00', 91)],
      comparison_points: [_hour('10:00', 61), _hour('11:00', 58)],
      extra_points: { O3: [_hour('10:00', 80)] },
    },
    markAreas: [{ name: 'PM10剔除区间', pollutant: 'PM10', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' }],
    bandRows: [{ time: '2026-09-14 10:00:00', min: 60, median: 70, max: 90 }],
    bandComparisonCollapsed: false,
    bandDistrictName: '阜宁县',
  })

  assert.equal(charts.length, 1)
  assert.equal(charts[0].pollutant, 'PM10')
  assert.equal(charts[0].unit, 'μg/m³')
  assert.deepEqual(charts[0].series.map(item => item.name),
    ['PM10（本站）', 'PM2.5（对照）', '同城最低', '同城中位', '同城最高'])
  assert.equal(charts[0].markAreas.length, 1)
  assert.equal(charts[0].markAreas[0].color, colorMap.PM10)
  assert.deepEqual(stationPollutantSeries.map(item => item.name), ['PM10（本站）', 'PM2.5（对照）'])
  assert.equal(colorMap.PM10, '#2f86e0')
  assert.equal(colorMap['PM2.5'], '#9b8cff')
})

test('multi-target pollutants split into one chart each with paired comparison and no band', () => {
  const { charts } = buildPollutantCharts({
    data: {
      pollutant: 'PM10', comparison_pollutant: 'PM2.5', pollutants: ['PM10', 'NO2'], unit: 'μg/m³',
      points: [_hour('10:00', 82)],
      comparison_points: [_hour('10:00', 61)],
      extra_points: { NO2: [_hour('10:00', 44)], NO: [_hour('10:00', 12)] },
    },
    bandRows: [{ time: '2026-09-14 10:00:00', min: 60, median: 70, max: 90 }],
  })

  assert.deepEqual(charts.map(chart => chart.pollutant), ['PM10', 'NO2'])
  assert.deepEqual(charts[0].series.map(item => item.name),
    ['PM10（本站）', 'PM2.5（对照）', '同城最低', '同城中位', '同城最高'])
  assert.deepEqual(charts[1].series.map(item => item.name), ['NO2（本站）', 'NO（对照）'])
  assert.notEqual(charts[1].series[0].color, charts[1].series[1].color)
})

test('mark areas route to their own pollutant chart and unattributed ones stay on the main chart', () => {
  const { charts } = buildPollutantCharts({
    data: {
      pollutant: 'PM10', comparison_pollutant: 'PM2.5', unit: 'μg/m³',
      points: [_hour('10:00', 82)],
      comparison_points: [_hour('10:00', 61)],
      extra_points: { O3: [_hour('10:00', 80)] },
    },
    markAreas: [
      { name: 'PM10剔除区间', pollutant: 'PM10', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' },
      { name: 'O3剔除区间', pollutant: 'O3', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' },
      { name: '剔除候选', start: '2026-09-14 12:00:00', end: '2026-09-14 13:00:00' },
    ],
  })

  assert.deepEqual(charts.map(chart => chart.pollutant), ['PM10', 'O3'])
  assert.deepEqual(charts[0].markAreas.map(area => area.name), ['PM10剔除区间', '剔除候选'])
  assert.deepEqual(charts[1].markAreas.map(area => area.name), ['O3剔除区间'])
  assert.equal(charts[1].markAreas[0].color, charts[1].series[0].color)
})

test('areas for pollutants without curves fall back to the main chart uncolored', () => {
  const { charts } = buildPollutantCharts({
    data: {
      pollutant: 'PM10', comparison_pollutant: 'PM2.5', unit: 'μg/m³',
      points: [_hour('10:00', 82)],
      comparison_points: [_hour('10:00', 61)],
    },
    markAreas: [{ name: 'CO剔除区间', pollutant: 'CO', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' }],
  })

  assert.equal(charts.length, 1)
  assert.equal(charts[0].markAreas.length, 1)
  assert.equal(charts[0].markAreas[0].color, undefined)
})

test('mutual-pair pollutants marked by the review merge into one chart instead of duplicating curves', () => {
  const { charts } = buildPollutantCharts({
    data: {
      pollutant: 'NO', comparison_pollutant: 'NO2', unit: 'μg/m³',
      points: [_hour('10:00', 8), _hour('11:00', 9)],
      comparison_points: [_hour('10:00', 30), _hour('11:00', 28)],
    },
    markAreas: [
      { name: 'NO剔除区间', pollutant: 'NO', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' },
      { name: 'NO2剔除区间', pollutant: 'NO2', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' },
    ],
  })

  // NO↔NO2 互为配对且都在列：合并为一张"NO+NO2"图，两条都是本站曲线，双方区间同图
  assert.equal(charts.length, 1)
  assert.equal(charts[0].pollutant, 'NO+NO2')
  assert.equal(charts[0].title, 'NO+NO2 小时时序')
  assert.deepEqual(charts[0].series.map(item => item.name), ['NO（本站）', 'NO2（本站）'])
  assert.notEqual(charts[0].series[0].color, charts[0].series[1].color)
  assert.deepEqual(charts[0].markAreas.map(area => area.name), ['NO剔除区间', 'NO2剔除区间'])
  assert.equal(charts[0].markAreas[0].color, charts[0].series[0].color)
  assert.equal(charts[0].markAreas[1].color, charts[0].series[1].color)
})

test('one-way pair keeps reference curve; pair merge only when both are chart subjects', () => {
  // 目标 NO 与剔除区间里的 O3 出图；NO2 只是参考曲线不在出图列 → 各图独立、不合并
  const { charts } = buildPollutantCharts({
    data: {
      pollutant: 'NO', comparison_pollutant: 'NO2', unit: 'μg/m³',
      points: [_hour('10:00', 8)],
      comparison_points: [_hour('10:00', 30)],
      extra_points: { O3: [_hour('10:00', 80)], NO2: [_hour('10:00', 31)] },
    },
    markAreas: [
      { name: 'NO剔除区间', pollutant: 'NO', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' },
      { name: 'O3剔除区间', pollutant: 'O3', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' },
    ],
  })

  assert.deepEqual(charts.map(chart => chart.pollutant), ['NO', 'O3'])
  assert.deepEqual(charts[0].series.map(item => item.name), ['NO（本站）', 'NO2（对照）'])
  assert.deepEqual(charts[1].series.map(item => item.name), ['O3（本站）', 'NO2（对照）'])
  assert.deepEqual(charts[1].markAreas.map(area => area.name), ['O3剔除区间'])

  // 目标 SO2 无配对；O3 与 NO2 都因剔除区间入列且互为配对 → 合并为一张"O3+NO2"
  const merged = buildPollutantCharts({
    data: {
      pollutant: 'SO2', unit: 'μg/m³',
      points: [_hour('10:00', 9)],
      extra_points: { O3: [_hour('10:00', 80)], NO2: [_hour('10:00', 31)], NO: [_hour('10:00', 8)] },
    },
    markAreas: [
      { name: 'O3剔除区间', pollutant: 'O3', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' },
      { name: 'NO2剔除区间', pollutant: 'NO2', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' },
    ],
  })
  assert.deepEqual(merged.charts.map(chart => chart.pollutant), ['SO2', 'O3+NO2'])
  assert.deepEqual(merged.charts[0].series.map(item => item.name), ['SO2（本站）'])
  assert.deepEqual(merged.charts[1].series.map(item => item.name), ['O3（本站）', 'NO2（本站）'])
  assert.deepEqual(merged.charts[1].markAreas.map(area => area.name), ['O3剔除区间', 'NO2剔除区间'])
})

test('CO chart switches unit to mg/m3 and packages without target points render nothing', () => {
  const coBundle = buildPollutantCharts({
    data: {
      pollutant: 'CO', pollutants: ['CO'], unit: 'μg/m³',
      points: [_hour('10:00', 1.2)],
      extra_points: {},
    },
  })
  assert.equal(coBundle.charts[0].unit, 'mg/m³')
  assert.equal(coBundle.charts[0].series[0].name, 'CO（本站）')

  const empty = buildPollutantCharts({
    data: { pollutant: 'PM10', points: [], extra_points: { O3: [_hour('10:00', 80)] } },
    markAreas: [{ name: 'O3剔除区间', pollutant: 'O3', start: '2026-09-14 10:00:00', end: '2026-09-14 11:00:00' }],
  })
  assert.deepEqual(empty.charts, [])
})

test('legacy package without comparison fields falls back to pm25_points pairing', () => {
  const { charts } = buildPollutantCharts({
    data: {
      pollutant: 'PM10', unit: 'μg/m³',
      points: [_hour('10:00', 82)],
      pm25_points: [_hour('10:00', 61)],
    },
  })

  assert.equal(charts.length, 1)
  assert.equal(charts[0].series[1].name, 'PM2.5（对照）')
})

test('pollutants without valid curves never claim a chart slot', () => {
  const { charts } = buildPollutantCharts({
    data: {
      pollutant: 'PM10', pollutants: ['PM10', 'NOX', 'SO2'], unit: 'μg/m³',
      points: [_hour('10:00', 82)],
      extra_points: {},
    },
  })

  assert.deepEqual(charts.map(chart => chart.pollutant), ['PM10'])
})
