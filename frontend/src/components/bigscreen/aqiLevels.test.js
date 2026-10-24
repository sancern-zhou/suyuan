import test from 'node:test'
import assert from 'node:assert/strict'

import {
  LEVEL_PALETTE,
  aqiColor,
  aqiLevelName,
  formatDateTime,
  formatHour,
  windDirectionLabel
} from './aqiLevels.js'

test('aqi level names follow the six-band standard', () => {
  assert.equal(aqiLevelName(32), '优')
  assert.equal(aqiLevelName(50), '优')
  assert.equal(aqiLevelName(82), '良')
  assert.equal(aqiLevelName(151), '中度污染')
  assert.equal(aqiLevelName(320), '严重污染')
  assert.equal(aqiLevelName(null), '—')
  assert.equal(aqiLevelName('not-a-number'), '—')
})

test('aqi colors map to the shared palette', () => {
  assert.equal(aqiColor(40), LEVEL_PALETTE[0])
  assert.equal(aqiColor(120), LEVEL_PALETTE[2])
  assert.equal(aqiColor(undefined), '#5b7684')
})

test('wind direction converts degrees to 16-point labels', () => {
  assert.equal(windDirectionLabel(0), '北')
  assert.equal(windDirectionLabel(90), '东')
  assert.equal(windDirectionLabel(180), '南')
  assert.equal(windDirectionLabel(270), '西')
  assert.equal(windDirectionLabel(45), '东北')
  assert.equal(windDirectionLabel(-90), '西')
  assert.equal(windDirectionLabel('x'), '—')
})

test('time helpers format ISO strings for screen display', () => {
  assert.equal(formatHour('2026-10-24T14:00:00.000'), '24日 14:00')
  assert.equal(formatDateTime('2026-10-24 14:05:00'), '2026-10-24 14:05')
  assert.equal(formatHour(''), '—')
  assert.equal(formatDateTime(null), '—')
})
