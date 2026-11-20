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

// 污染物 IAQI 折点（HJ 633 实时发布规则，与后端 aqi.py 同口径）：
// SO2/NO2/O3/CO 用 1 小时浓度限值表，PM10/PM2.5 用 24 小时表；
// PM 折点已按 GB 3095—2026 过渡限值收严（PM10 150→120、PM2.5 75→60）。
// 单位 μg/m³（CO 为 mg/m³）。
const IAQI_LEVELS = [0, 50, 100, 150, 200, 300, 400, 500]
const POLLUTANT_BREAKPOINTS = {
  so2: [0, 150, 500, 650, 800, 1600, 2100, 2620],
  no2: [0, 100, 200, 700, 1200, 2340, 3090, 3840],
  o3: [0, 160, 200, 300, 400, 800, 1000, 1200],
  co: [0, 5, 10, 35, 60, 90, 120, 150],
  pm10: [0, 50, 120, 250, 350, 420, 500, 600],
  pm25: [0, 35, 60, 115, 150, 250, 350, 500]
}

/** 污染物浓度转 IAQI（无值或折点外返回 null） */
export function iaqi(pollutant, concentration) {
  const value = Number(concentration)
  if (!Number.isFinite(value) || value < 0) return null
  const points = POLLUTANT_BREAKPOINTS[pollutant]
  if (!points) return null
  if (value > points[points.length - 1]) return 500
  for (let i = 1; i < points.length; i += 1) {
    if (value <= points[i]) {
      const low = points[i - 1]
      const ratio = (IAQI_LEVELS[i] - IAQI_LEVELS[i - 1]) / (points[i] - low)
      return Math.round((ratio * (value - low) + IAQI_LEVELS[i - 1]) * 10) / 10
    }
  }
  return null
}

/** 按污染物 IAQI 取等级色（用于大屏图标按所选污染物上色） */
export function iaqiColor(pollutant, concentration) {
  const index = iaqi(pollutant, concentration)
  return index === null ? '#5b7684' : LEVEL_PALETTE[levelIndex(index)]
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
