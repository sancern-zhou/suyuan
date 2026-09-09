export function finiteObservation(value) {
  if (typeof value !== 'number' && typeof value !== 'string') return null
  if (typeof value === 'string' && !value.trim()) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function observationValue(row, keys, allowFallback = false) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row || {}, key)) return finiteObservation(row[key])
  }
  if (allowFallback) {
    for (const [key, raw] of Object.entries(row || {})) {
      if (/id|code|time|rank|mark|status|type|name/i.test(key)) continue
      const value = finiteObservation(raw)
      if (value !== null) return value
    }
  }
  return null
}

export function normalizeReviewPoints(points, granularity = '') {
  const step = { '5min': 300000, hour: 3600000 }[granularity]
  const values = new Map()
  for (const point of points || []) {
    if (!point?.time) continue
    const time = Date.parse(String(point.time).replace(' ', 'T'))
    if (Number.isFinite(time)) values.set(time, finiteObservation(point.value))
  }
  const sorted = [...values].sort((a, b) => a[0] - b[0])
  const result = []
  for (const point of sorted) {
    const previous = result.at(-1)
    if (step && previous) {
      for (let time = previous[0] + step; time < point[0]; time += step) result.push([time, null])
    }
    result.push(point)
  }
  return result
}
