export const GUANGDONG_CENTER = [113.2668, 23.1333]
export const GUANGDONG_ZOOM = 7

const CITY_COORDINATES = {
  广州: [113.2668, 23.1333],
  深圳: [114.0579, 22.5431],
  珠海: [113.5767, 22.2707],
  汕头: [116.6819, 23.3541],
  佛山: [113.1214, 23.0218],
  韶关: [113.5975, 24.8104],
  河源: [114.7006, 23.7437],
  梅州: [116.1226, 24.2886],
  惠州: [114.4168, 23.1123],
  汕尾: [115.3753, 22.7862],
  东莞: [113.7518, 23.0207],
  中山: [113.3926, 22.5176],
  江门: [113.0819, 22.5787],
  阳江: [111.9826, 21.8579],
  湛江: [110.3594, 21.2707],
  茂名: [110.9255, 21.6627],
  肇庆: [112.4651, 23.0472],
  清远: [113.056, 23.682],
  潮州: [116.622, 23.6567],
  揭阳: [116.3727, 23.5509],
  云浮: [112.0445, 22.9151]
}

const CITY_NAME_KEYS = ['city', 'city_name', 'name', '城市', '地市', 'area', 'region']
const STATION_NAME_KEYS = ['station_name', 'station', 'name', '站点名称', '站点', 'monitor_name', 'point_name', 'site_name']
const VALUE_KEYS = ['aqi', 'avg_aqi', 'average', 'value', 'index', 'aqi_index', '综合指数', 'AQI']
const MEASUREMENT_KEYS = ['measurements', 'measurement', 'metrics', 'values', 'pollutants']

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function firstString(record, keys) {
  for (const key of keys) {
    const value = record?.[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

function firstNumber(record, keys) {
  for (const key of keys) {
    const number = toNumber(record?.[key])
    if (number !== null) return number
  }
  return null
}

function toNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const number = Number(value)
    if (Number.isFinite(number)) return number
  }
  return null
}

function coordinatePair(record) {
  const pair = Array.isArray(record?.coordinates)
    ? record.coordinates
    : Array.isArray(record?.location)
      ? record.location
      : null

  if (pair?.length >= 2) {
    const lng = toNumber(pair[0])
    const lat = toNumber(pair[1])
    if (lng !== null && lat !== null) return [lng, lat]
  }

  const lng = firstNumber(record, ['lng', 'lon', 'longitude', '经度', 'x'])
  const lat = firstNumber(record, ['lat', 'latitude', '纬度', 'y'])
  return lng !== null && lat !== null ? [lng, lat] : null
}

function focusSet(focus, key) {
  return new Set(asArray(focus?.[key]).filter(item => typeof item === 'string' && item.trim()))
}

function metricValue(record) {
  const topLevel = firstNumber(record, VALUE_KEYS)
  if (topLevel !== null) return topLevel

  for (const key of MEASUREMENT_KEYS) {
    const measurements = record?.[key]
    if (measurements && typeof measurements === 'object' && !Array.isArray(measurements)) {
      const nested = firstNumber(measurements, VALUE_KEYS)
      if (nested !== null) return nested
    }
  }

  return null
}

function normalizeCityMetric(record, focusedCities) {
  const name = firstString(record, CITY_NAME_KEYS)
  if (!name) return null

  const position = coordinatePair(record) || CITY_COORDINATES[name]
  if (!position) return null

  return {
    type: 'city',
    name,
    position,
    value: metricValue(record),
    focused: focusedCities.has(name)
  }
}

// Month/year city modules can contain one raw day record per city per date.
// Average valid AQI-like values so each city renders as one stable overview marker.
function aggregateCityMetricMarkers(records, focusedCities) {
  const byCity = new Map()

  for (const record of records) {
    const marker = normalizeCityMetric(record, focusedCities)
    if (!marker) continue

    const existing = byCity.get(marker.name)
    const value = marker.value
    if (!existing) {
      byCity.set(marker.name, {
        ...marker,
        valueTotal: value !== null ? value : 0,
        valueCount: value !== null ? 1 : 0
      })
      continue
    }

    if (value !== null) {
      existing.valueTotal += value
      existing.valueCount += 1
    }
    if (!existing.position && marker.position) {
      existing.position = marker.position
    }
    existing.focused = existing.focused || marker.focused
  }

  return Array.from(byCity.values()).map(({ valueTotal, valueCount, ...marker }) => ({
    ...marker,
    value: valueCount > 0 ? valueTotal / valueCount : null
  }))
}

function normalizeStation(record, focusedStations) {
  const name = firstString(record, STATION_NAME_KEYS)
  const position = coordinatePair(record)
  if (!name || !position) return null

  return {
    type: 'station',
    name,
    position,
    value: metricValue(record),
    focused: focusedStations.has(name)
  }
}

function firstNonEmpty(...collections) {
  return collections.find(collection => Array.isArray(collection) && collection.length > 0) || []
}

export function extractCityMetricMarkers(overview, focus = {}) {
  const modules = overview?.modules || {}
  const records = firstNonEmpty(
    modules.month_to_date?.city_metrics,
    modules.month_to_date?.cities,
    modules.realtime?.cities,
    modules.year_to_date?.city_metrics,
    modules.year_to_date?.cities
  )
  const focusedCities = focusSet(focus, 'cities')

  return aggregateCityMetricMarkers(records, focusedCities)
}

export function extractStationMarkers(overview, focus = {}) {
  const records = asArray(overview?.modules?.layers?.stations)
  const focusedStations = focusSet(focus, 'stations')

  return records
    .map(record => normalizeStation(record, focusedStations))
    .filter(Boolean)
}
