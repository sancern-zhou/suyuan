import test from 'node:test'
import assert from 'node:assert/strict'
import { hourlyWeatherPoints, weatherTime } from './jiangsuWeatherSeries.js'

test('weather timeline retains missing hours and null values without inventing zero', () => {
  const points = hourlyWeatherPoints({
    start: '2026-09-01 00:00:00', end: '2026-09-01 03:59:59',
    data: [
      { timePoint: '2026-09-01T00:00:00', windSpeed: 0 },
      { timePoint: '2026-09-01T02:00:00', windSpeed: null },
      { timePoint: '2026-09-01T03:00:00', windSpeed: 2.5 }
    ]
  }, 'windSpeed')
  assert.deepEqual(points.map(point => point[1]), [0, null, null, 2.5])
  assert.equal(points[0][0], weatherTime('2026-09-01T00:00:00'))
})

test('legacy evidence without a weather window has no timeline', () => {
  assert.deepEqual(hourlyWeatherPoints({}, 'rain'), [])
})
