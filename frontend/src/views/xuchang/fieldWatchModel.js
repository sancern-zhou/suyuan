/**
 * 现场巡查快报的纯展示模型：把快照字段换算成图形/列表所需的几何与配色。
 * 与 Vue 解耦，便于 node --test 直接校验（坐标、排序、空值兜底）。
 */
import { aqiColor, aqiLevelName } from '../../components/xuchang/bigscreen/aqiLevels.js'

const FALLBACK_COLOR = '#5b7684'
const POLLUTANT_LABELS = {
  pm25: 'PM2.5', pm10: 'PM10', o3: 'O3', no2: 'NO2', so2: 'SO2', co: 'CO'
}

function rgb(hex) {
  const match = /^#([0-9a-f]{6})$/i.exec(String(hex || ''))
  if (!match) return null
  const value = parseInt(match[1], 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

/** 浅色底上的等级文字色：大屏调色板直接放白底偏亮，按比例压暗保证可读 */
export function shadeColor(hex, amount = 0.25) {
  const channels = rgb(hex)
  if (!channels) return FALLBACK_COLOR
  const mixed = channels.map(channel => Math.round(channel * (1 - amount)))
  return `#${mixed.map(channel => channel.toString(16).padStart(2, '0')).join('')}`
}

export function tintColor(hex, alpha = 0.12) {
  const channels = rgb(hex)
  if (!channels) return `rgba(91, 118, 132, ${alpha})`
  return `rgba(${channels.join(', ')}, ${alpha})`
}

export function levelTextColor(aqi) {
  return shadeColor(aqiColor(aqi))
}

/** 大号数字（54px）对比度要求低于小字，少压暗以保留等级色的辨识度 */
export function levelDisplayColor(aqi) {
  return shadeColor(aqiColor(aqi), 0.12)
}

export function pollutantLabel(key) {
  if (!key) return ''
  const text = String(key).trim()
  return POLLUTANT_LABELS[text.toLowerCase()] || text.toUpperCase()
}

function finite(value) {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

export function shortDateTime(iso) {
  const match = /^\d{4}-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})/.exec(String(iso || ''))
  return match ? `${match[1]}-${match[2]} ${match[3]}:${match[4]}` : '—'
}

export function clockTime(iso) {
  const match = /^\d{4}-\d{2}-\d{2}[T\s](\d{2}):(\d{2})/.exec(String(iso || ''))
  return match ? `${match[1]}:${match[2]}` : '—'
}

export function hourLabel(iso) {
  const match = /^\d{4}-\d{2}-\d{2}[T\s](\d{2}):/.exec(String(iso || ''))
  return match ? `${Number(match[1])}时` : ''
}

/**
 * 近 24 小时柱状图几何。返回 SVG 坐标系内的柱子、网格线与刻度，
 * 缺测小时保留位置但不画柱，避免把数据空洞连成"正常"。
 */
export function buildTrend(rows, { width = 320, height = 132 } = {}) {
  const list = Array.isArray(rows) ? rows : []
  if (!list.length) return null
  const padding = { top: 12, right: 4, bottom: 22, left: 26 }
  const innerWidth = width - padding.left - padding.right
  const innerHeight = height - padding.top - padding.bottom
  const values = list.map(row => finite(row?.aqi))
  const peak = Math.max(...values.map(value => value ?? 0))
  const yMax = Math.max(100, Math.ceil(peak / 50) * 50)
  const slot = innerWidth / list.length
  const barWidth = Math.min(9, slot * 0.62)
  const y = value => padding.top + innerHeight - (value / yMax) * innerHeight

  const bars = list.map((row, index) => {
    const value = values[index]
    if (value === null) return null
    return {
      x: padding.left + slot * index + (slot - barWidth) / 2,
      y: y(value),
      width: barWidth,
      height: Math.max(2, padding.top + innerHeight - y(value)),
      color: aqiColor(value),
      value
    }
  }).filter(Boolean)

  const grid = []
  for (let value = 50; value <= yMax; value += 50) {
    grid.push({ value, y: y(value), dashed: value === 100 })
  }
  const ticks = list.map((row, index) => ({ index, label: hourLabel(row?.data_time) }))
    .filter((tick, order) => tick.label && (order % 6 === 0 || order === list.length - 1))
    .map(tick => ({ x: padding.left + slot * tick.index + slot / 2, label: tick.label }))

  return {
    width,
    height,
    baseline: padding.top + innerHeight,
    grid,
    bars,
    ticks,
    yMax,
    peak
  }
}

/** 区县按 AQI 降序，缺测排末尾；条形长度相对本组最大值归一 */
export function buildCountyRows(counties) {
  const list = (Array.isArray(counties) ? counties : [])
    .map(item => ({ ...item, _aqi: finite(item?.aqi) }))
    .sort((a, b) => (b._aqi ?? -1) - (a._aqi ?? -1))
  const maxAqi = Math.max(0, ...list.map(item => item._aqi ?? 0))
  return list.map(item => ({
    name: item.station_name || '—',
    aqiText: item._aqi === null ? '—' : String(Math.round(item._aqi)),
    level: item.quality || aqiLevelName(item._aqi),
    color: aqiColor(item._aqi),
    textColor: levelTextColor(item._aqi),
    widthPct: item._aqi === null || !maxAqi ? 0 : Math.max(4, (item._aqi / maxAqi) * 100)
  }))
}

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/**
 * 未来数日预报：AQI 区间段在统一量尺（默认 0–150）上定位，
 * 颜色按区间上限定级，突出污染过程的高峰日。
 */
export function buildForecastRows(daily, today = new Date()) {
  const list = (Array.isArray(daily) ? daily : []).filter(item => item?.date)
  if (!list.length) return []
  const maxOf = item => finite(item.max_aqi) ?? finite(item.aqi)
  const minOf = item => finite(item.min_aqi) ?? finite(item.aqi)
  const scaleMax = Math.max(150, Math.ceil(Math.max(...list.map(item => maxOf(item) ?? 0)) / 50) * 50)
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())

  return list.map(item => {
    const min = minOf(item)
    const max = maxOf(item)
    const day = new Date(`${item.date}T00:00:00`)
    const diffDays = Math.round((day - startOfToday) / 86400000)
    const weekday = diffDays === 0 ? '今天' : diffDays === 1 ? '明天' : WEEKDAYS[day.getDay()]
    return {
      key: item.date,
      weekday,
      dateLabel: item.date.slice(5).replace('-', '/'),
      rangeText: min === null && max === null ? '—' : `${Math.round(min ?? max)}~${Math.round(max ?? min)}`,
      level: aqiLevelName(max),
      primary: pollutantLabel(item.primary_pollutant),
      color: aqiColor(max),
      textColor: levelTextColor(max),
      leftPct: min === null ? 0 : Math.min(100, (min / scaleMax) * 100),
      widthPct: min === null || max === null ? 0 : Math.max(3, ((max - min) / scaleMax) * 100)
    }
  })
}

/** 告警行附带的派发通报（快照按 episode_id 回挂）；正文为空视为无通报 */
function buildNotice(dispatch) {
  const text = String(dispatch?.text ?? '').trim()
  if (!text) return null
  return { time: shortDateTime(dispatch?.time), text }
}

/** 告警卡片文案：峰值/偏离/持续时长与起止时间，缺字段的片段直接省略 */
export function buildAlertView(alert) {
  const active = alert?.status === 'active'
  const metrics = []
  const peak = finite(alert?.peak_station_value)
  const deviation = finite(alert?.peak_deviation_ratio)
  const hours = finite(alert?.hour_count)
  if (peak !== null) metrics.push({ label: '峰值', value: String(peak), unit: 'μg/m³' })
  if (deviation !== null) metrics.push({ label: '偏离周边', value: `${deviation}`, unit: '倍' })
  if (hours !== null && hours > 0) metrics.push({ label: '已持续', value: String(hours), unit: '小时' })

  const started = alert?.started_at ? `${shortDateTime(alert.started_at)} 起` : ''
  const lastSeen = alert?.last_seen_at && alert?.last_seen_at !== alert?.started_at
    ? `最近 ${clockTime(alert.last_seen_at)}` : ''
  return {
    key: alert?.episode_id || `${alert?.station_id}-${alert?.started_at}`,
    name: alert?.station_name || alert?.station_id || '未知站点',
    active,
    statusText: active ? '进行中' : '已结束',
    pollutant: pollutantLabel(alert?.target_pollutant),
    metrics,
    timeText: [started, lastSeen].filter(Boolean).join(' · '),
    notice: buildNotice(alert?.dispatch)
  }
}
