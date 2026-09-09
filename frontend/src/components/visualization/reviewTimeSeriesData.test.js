import test from 'node:test'
import assert from 'node:assert/strict'
import { finiteObservation, observationValue, normalizeReviewPoints } from './reviewTimeSeriesData.js'

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
