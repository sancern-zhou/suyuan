/**
 * 现场巡查快报的纯展示模型：把快照字段换算成图形/列表所需的几何与配色。
 * 与 Vue 解耦，便于 node --test 直接校验（坐标、排序、空值兜底）。
 */
import { aqiLevelName } from '../../components/xuchang/bigscreen/aqiLevels.js'

const FALLBACK_COLOR = '#5b7684'
const MUTED_COLOR = '#8a8f99'
const POLLUTANT_LABELS = {
  pm25: 'PM2.5', pm10: 'PM10', o3: 'O3', no2: 'NO2', so2: 'SO2', co: 'CO'
}

/** HJ 633-2026 附录 A 六级等级色（优 → 严重污染） */
export const LEVEL_COLORS_2026 = ['#00E400', '#FFFF00', '#FF7E00', '#FF0000', '#99004C', '#7E0023']
const AQI_LEVEL_BREAKS = [50, 100, 150, 200, 300]

/**
 * HJ 633-2026 六项污染物 1 小时平均 IAQI 折点（μg/m³，CO 为 mg/m³），
 * 是 backend/config/environment_chart_standards.json 的前端副本（单测逐项比对）。
 * 区县值是小时值，一律查 1 小时表；SO2 的 1 小时表只到 IAQI 200，超出按末档处理。
 */
export const IAQI_2026_1H = {
  so2: [0, 150, 500, 650, 800],
  no2: [0, 100, 200, 700, 1200, 2340, 3090, 3840],
  co: [0, 5, 10, 35, 60, 90, 120, 150],
  o3: [0, 160, 200, 300, 400, 800, 1000, 1200],
  pm10: [0, 50, 120, 250, 350, 420, 500, 600],
  pm25: [0, 35, 60, 115, 150, 250, 350, 500]
}

/** 区县实况可选指标：AQI + 六项污染物（CO 为 mg/m³，其余 μg/m³）+ 首要污染物 */
export const COUNTY_METRICS = [
  { key: 'aqi', label: 'AQI', unit: '' },
  { key: 'pm25', label: 'PM2.5', unit: 'μg/m³', digits: 0 },
  { key: 'pm10', label: 'PM10', unit: 'μg/m³', digits: 0 },
  { key: 'o3', label: 'O3', unit: 'μg/m³', digits: 0 },
  { key: 'so2', label: 'SO2', unit: 'μg/m³', digits: 0 },
  { key: 'no2', label: 'NO2', unit: 'μg/m³', digits: 0 },
  { key: 'co', label: 'CO', unit: 'mg/m³', digits: 1 },
  { key: 'primary', label: '首要污染物', unit: '' }
]

function rgb(hex) {
  const match = /^#([0-9a-f]{6})$/i.exec(String(hex || ''))
  if (!match) return null
  const value = parseInt(match[1], 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

/** 把颜色按比例向黑压暗（amount=0 原色，=1 纯黑） */
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

function relativeLuminance(hex) {
  const channels = rgb(hex)
  if (!channels) return null
  const linear = channels.map(channel => {
    const s = channel / 255
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
}

/**
 * 白底上的文字色：把等级色逐级压暗，直到与白底的对比度达标。
 * 附录 A 的纯黄、纯绿直接当文字几乎看不清，而紫、褐两档本身够深——
 * 固定比例压暗照顾不了六档差异，按对比度收敛。
 */
export function readableText(hex, minContrast = 4.5) {
  for (let step = 0; step < 20; step += 1) {
    const color = step ? shadeColor(hex, step / 20) : hex
    const luminance = relativeLuminance(color)
    if (luminance !== null && 1.05 / (luminance + 0.05) >= minContrast) return color
  }
  return '#000000'
}

/** HJ 633-2026 等级下标（0 优 … 5 严重污染）；缺测返回 null */
function levelIndex(aqi) {
  const value = finite(aqi)
  if (value === null) return null
  const index = AQI_LEVEL_BREAKS.findIndex(upper => value <= upper)
  return index === -1 ? LEVEL_COLORS_2026.length - 1 : index
}

/**
 * GB/T 8170 修约（四舍六入五成双）到指定小数位。按十进制数字串逐位判断，
 * 与后端 Decimal(str(value)).quantize(...) 结果一致——浮点乘法在恰好 x.x5 处会失真。
 */
function roundHalfEven(value, decimals) {
  const text = String(value)
  if (/e/i.test(text)) return value // 只有 <1e-6 的极小值会走到这里，远低于任何折点
  const [whole, fraction = ''] = text.split('.')
  const digits = [0]
  for (const char of whole + fraction.slice(0, decimals).padEnd(decimals, '0')) digits.push(Number(char))
  const next = fraction[decimals]
  const tie = next === '5' && !/[1-9]/.test(fraction.slice(decimals + 1))
  if (next > '5' || (next === '5' && (!tie || digits[digits.length - 1] % 2 === 1))) {
    for (let index = digits.length - 1; index >= 0; index -= 1) {
      if (digits[index] < 9) {
        digits[index] += 1
        break
      }
      digits[index] = 0
    }
  }
  const splitAt = digits.length - decimals
  return Number(`${digits.slice(0, splitAt).join('')}${decimals ? `.${digits.slice(splitAt).join('')}` : ''}`)
}

/**
 * 污染物小时浓度的 HJ 633-2026 等级下标。浓度先按标准修约（CO 到 0.1，其余取整）
 * 再查 1 小时折点，定级结果与后端 environment_charts.pollutant_iaqi 一致。
 */
export function pollutantLevelIndex(pollutant, concentration) {
  const key = String(pollutant || '').toLowerCase()
  const points = IAQI_2026_1H[key]
  const value = finite(concentration)
  if (!points || value === null || value < 0) return null
  const rounded = roundHalfEven(value, key === 'co' ? 1 : 0)
  const segment = points.findIndex((point, order) => order > 0 && rounded <= point)
  // 超出折点表：满表封顶 IAQI 500，短表（SO2）停在末档
  const last = segment === -1 ? points.length - 2 : segment - 1
  return Math.min(last, LEVEL_COLORS_2026.length - 1)
}

/** 等级色（HJ 633-2026 附录 A）：AQI 按等级；污染物按 1 小时 IAQI 定级；缺测为灰 */
export function levelColor(aqi) {
  const index = levelIndex(aqi)
  return index === null ? FALLBACK_COLOR : LEVEL_COLORS_2026[index]
}

export function pollutantLevelColor(pollutant, concentration) {
  const index = pollutantLevelIndex(pollutant, concentration)
  return index === null ? FALLBACK_COLOR : LEVEL_COLORS_2026[index]
}

export function levelTextColor(aqi) {
  return readableText(levelColor(aqi))
}

/** 大号数字（54px）对比度要求低于小字，少压暗以保留等级色的辨识度 */
export function levelDisplayColor(aqi) {
  return readableText(levelColor(aqi), 3)
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

/** 页头"数据截至"：站点层是 5 分钟槽位，分钟不能省（整点仍显示 :00） */
export function dataClock(iso) {
  const match = /^\d{4}-\d{2}-(\d{2})[T\s](\d{2}):(\d{2})/.exec(String(iso || ''))
  return match ? `${match[1]}日 ${match[2]}:${match[3]}` : '—'
}

/** 区县小时值对应的小时；凌晨取到的可能是前一日末小时，故带日 */
export function dayHourLabel(iso) {
  const match = /^\d{4}-\d{2}-(\d{2})[T\s](\d{2}):/.exec(String(iso || ''))
  return match ? `${match[1]}日 ${Number(match[2])}时` : ''
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
      color: levelColor(value),
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

/** 省平台发布的首要污染物（多值时取首位）；优级没有首要污染物，平台给空 */
function primaryPollutantLabel(primary) {
  const first = String(primary ?? '').split(/[,，、/]/)[0].trim()
  return first && !['-', '—'].includes(first) ? pollutantLabel(first) : '—'
}

/**
 * 区县按所选指标升序（缺测排末尾，同值保持原始顺序），条形长度相对本组最大值归一。
 * 颜色一律按 HJ 633-2026 分级：AQI 按等级并标注等级名；污染物按 1 小时 IAQI 定级，
 * 副标注改为该区县 AQI（缺测也占一行，保持行高一致），切换指标后整体空气质量仍可见。
 * 首要污染物是定性列，没有大小可排：按 AQI 升序（AQI 正是由首要污染物决定）。
 */
export function buildCountyRows(counties, { metric = 'aqi' } = {}) {
  const option = COUNTY_METRICS.find(item => item.key === metric) || COUNTY_METRICS[0]
  const key = option.key
  const sortKey = key === 'primary' ? 'aqi' : key
  const list = (Array.isArray(counties) ? counties : [])
    .map((item, index) => ({ ...item, _value: finite(item?.[sortKey]), _index: index }))
    .sort((a, b) => {
      if (a._value === null || b._value === null) {
        if (a._value === b._value) return a._index - b._index
        return a._value === null ? 1 : -1
      }
      return a._value - b._value || a._index - b._index
    })
  const max = Math.max(0, ...list.map(item => item._value ?? 0))
  return list.map(item => {
    const value = item._value
    const color = sortKey === 'aqi' ? levelColor(value) : pollutantLevelColor(sortKey, value)
    const aqi = finite(item.aqi)
    return {
      name: item.station_name || '—',
      valueText: key === 'primary' ? primaryPollutantLabel(item.primary)
        : value === null ? '—' : value.toFixed(option.digits),
      level: key === 'aqi' ? (item.quality || aqiLevelName(value))
        : `AQI ${aqi === null ? '—' : Math.round(aqi)}`,
      levelColor: key === 'aqi' ? levelTextColor(value) : MUTED_COLOR,
      color,
      textColor: readableText(color),
      widthPct: value === null || !max ? 0 : Math.max(4, (value / max) * 100)
    }
  })
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
      color: levelColor(max),
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
