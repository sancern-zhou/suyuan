/**
 * AQI 等级色与等级名（与 AirQualityForecastView 的调色板保持一致）。
 */
export const LEVEL_PALETTE = ['#21a366', '#e5ae22', '#ee7d32', '#d85245', '#914c95', '#7a2432']
export const LEVEL_NAMES = ['优', '良', '轻度污染', '中度污染', '重度污染', '严重污染']

function levelIndex(value) {
  // Number(null) 与 Number('') 均为 0，须先挡掉空值再转数值
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  if (!Number.isFinite(num)) return null
  if (num <= 50) return 0
  if (num <= 100) return 1
  if (num <= 150) return 2
  if (num <= 200) return 3
  if (num <= 300) return 4
  return 5
}

export function aqiLevelName(value) {
  const index = levelIndex(value)
  return index === null ? '—' : LEVEL_NAMES[index]
}

export function aqiColor(value) {
  const index = levelIndex(value)
  return index === null ? '#5b7684' : LEVEL_PALETTE[index]
}

/** 风向角度转十六方位缩写 */
export function windDirectionLabel(degrees) {
  const num = Number(degrees)
  if (!Number.isFinite(num)) return '—'
  const dirs = ['北', '北东北', '东北', '东东北', '东', '东东南', '东南', '南东南',
    '南', '南西南', '西南', '西西南', '西', '西西北', '西北', '北西北']
  return dirs[Math.round(((num % 360) + 360) % 360 / 22.5) % 16]
}

export function formatHour(iso) {
  if (!iso) return '—'
  const text = String(iso)
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):/)
  return match ? `${match[3]}日 ${match[4]}:00` : text
}

export function formatDateTime(iso) {
  if (!iso) return '—'
  const text = String(iso)
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})/)
  return match ? `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}` : text
}
