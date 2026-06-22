import assert from 'node:assert/strict'
import test from 'node:test'

import {
  extractCityMetricMarkers,
  extractStationMarkers
} from './guangdongMapData.js'

test('extractCityMetricMarkers prefers month-to-date city metrics and marks focused cities', () => {
  const overview = {
    modules: {
      month_to_date: {
        city_metrics: [
          { city: '广州', avg_aqi: 68 },
          { city_name: '深圳', lng: 114.0579, lat: 22.5431, aqi: 45 }
        ]
      },
      realtime: {
        cities: [
          { city: '佛山', avg_aqi: 80 }
        ]
      }
    }
  }

  const markers = extractCityMetricMarkers(overview, { cities: ['深圳'] })

  assert.equal(markers.length, 2)
  assert.deepEqual(markers.map(marker => marker.name), ['广州', '深圳'])
  assert.deepEqual(markers[0].position, [113.2668, 23.1333])
  assert.equal(markers[0].value, 68)
  assert.equal(markers[1].focused, true)
})

test('extractCityMetricMarkers falls back to realtime cities when monthly metrics are absent', () => {
  const overview = {
    modules: {
      realtime: {
        cities: [
          { city: '佛山', average: 72 }
        ]
      }
    }
  }

  const markers = extractCityMetricMarkers(overview, { cities: [] })

  assert.equal(markers.length, 1)
  assert.equal(markers[0].name, '佛山')
  assert.equal(markers[0].value, 72)
})

test('extractCityMetricMarkers reads AQI from nested measurements', () => {
  const overview = {
    modules: {
      month_to_date: {
        city_metrics: [
          { city: '广州', measurements: { AQI: 77 } }
        ]
      }
    }
  }

  const markers = extractCityMetricMarkers(overview, { cities: [] })

  assert.equal(markers.length, 1)
  assert.equal(markers[0].name, '广州')
  assert.equal(markers[0].value, 77)
})

test('extractCityMetricMarkers averages duplicate city records into one marker', () => {
  const overview = {
    modules: {
      month_to_date: {
        city_metrics: [
          { city: '广州', measurements: { AQI: 60 } },
          { city: '广州', measurements: { AQI: 80 } },
          { city: '深圳', measurements: { AQI: 45 } }
        ]
      }
    }
  }

  const markers = extractCityMetricMarkers(overview, { cities: ['广州'] })

  assert.equal(markers.length, 2)
  assert.equal(markers[0].name, '广州')
  assert.equal(markers[0].value, 70)
  assert.equal(markers[0].focused, true)
})

test('extractStationMarkers reads layer stations and ignores records without coordinates', () => {
  const overview = {
    modules: {
      layers: {
        stations: [
          { station_name: '麓湖', longitude: '113.292', latitude: '23.151', aqi: '52' },
          { station_name: '缺坐标', aqi: 99 }
        ]
      }
    }
  }

  const markers = extractStationMarkers(overview, { stations: ['麓湖'] })

  assert.equal(markers.length, 1)
  assert.equal(markers[0].name, '麓湖')
  assert.deepEqual(markers[0].position, [113.292, 23.151])
  assert.equal(markers[0].value, 52)
  assert.equal(markers[0].focused, true)
})
