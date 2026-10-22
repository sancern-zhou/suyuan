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

// 剔除区间标注 → 所属污染物：优先取后端给的 pollutant 字段（新包），
// 旧包只有 "{污染物}剔除区间" 形态的名称，按前缀解析，无污染物则返回空串。
export function areaPollutant(area) {
  const explicit = String(area?.pollutant || '').trim().toUpperCase()
  if (explicit) return explicit
  const match = /^(.+?)剔除/.exec(String(area?.name || '').trim())
  return match ? match[1].trim().toUpperCase() : ''
}

// 曲线色（#rrggbb）→ 同色半透明填充，用于 markArea 与曲线同色关联；非法输入返回 null。
export function hexWithAlpha(hex, alpha = 0.14) {
  const match = /^#([0-9a-f]{6})$/i.exec(String(hex || '').trim())
  if (!match) return null
  const value = parseInt(match[1], 16)
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
}
