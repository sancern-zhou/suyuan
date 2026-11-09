import { CHART_COMPARISON_PAIRS, EXTRA_POLLUTANT_COLORS, switcherPollutantGroups } from './reviewTimeSeriesData.js'

export const FIVE_MINUTE_FLAG_LABELS = {
  PS: '跨度检查',
  PZ: '零点检查',
  Z: '零点校准',
  S: '跨度校准',
}

export function fiveMinuteFlagLabel(flag) {
  const code = String(flag || '').trim().toUpperCase()
  return FIVE_MINUTE_FLAG_LABELS[code] || (code ? '原始监测标识' : '')
}

export function fiveMinuteTime(value) {
  if (!value) return null
  const time = Date.parse(String(value).replace(' ', 'T'))
  return Number.isFinite(time) ? time : null
}

export function fiveMinuteWindow(data = {}, mode = 'handling') {
  const coverage = data.coverage || {}
  const actualStart = fiveMinuteTime(coverage.actual_start)
  const actualEnd = fiveMinuteTime(coverage.actual_end)
  if (actualStart === null || actualEnd === null) return [null, null]
  const queryStart = fiveMinuteTime(coverage.query_start) ?? actualStart
  const queryEnd = fiveMinuteTime(coverage.query_end) ?? actualEnd
  if (mode === 'full') return [queryStart, queryEnd]
  if (mode === 'day') {
    const anchor = fiveMinuteTime(coverage.fault_time) ?? fiveMinuteTime(coverage.default_anchor?.time) ?? actualEnd
    const day = new Date(anchor)
    return [
      new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime(),
      new Date(day.getFullYear(), day.getMonth(), day.getDate(), 23, 59, 59).getTime(),
    ]
  }
  const suggested = (coverage.default_window || []).map(fiveMinuteTime)
  if (suggested.length === 2 && suggested.every(time => time !== null)) return suggested
  const anchor = fiveMinuteTime(coverage.default_anchor?.time) ?? actualEnd
  return [Math.max(queryStart, anchor - 2 * 3600000), Math.min(queryEnd, anchor + 2 * 3600000)]
}

export function fiveMinuteColors(data = {}, inherited = {}) {
  const colors = { ...inherited }
  const target = data.available_pollutants || Object.keys(data.points_by_pollutant || {})
  const palette = ['#2f86e0', '#9b8cff', ...EXTRA_POLLUTANT_COLORS]
  for (const code of target) {
    if (!colors[code]) colors[code] = palette.find(color => !Object.values(colors).includes(color)) || palette[target.indexOf(code) % palette.length]
  }
  return colors
}

export function buildFiveMinuteSeries(data = {}, {
  selected = '',
  target = '',
  colorMap = {},
  mode = 'handling',
  flaggedOnly = false,
} = {}) {
  const pointsByPollutant = data.points_by_pollutant || {}
  const targetCode = String(target || data.pollutant || '').toUpperCase()
  const groups = switcherPollutantGroups(data.available_pollutants || Object.keys(pointsByPollutant))
  const group = groups.find(item => item.members.join('/') === selected)
    || groups.find(item => item.members.includes(targetCode))
    || groups[0]
  const [start, end] = fiveMinuteWindow(data, mode)
  const members = [...(group?.members || [])]
  const pair = members.length === 1 ? CHART_COMPARISON_PAIRS[members[0]] : null
  if (pair && pointsByPollutant[pair]?.length) members.push(pair)
  const colors = fiveMinuteColors(data, colorMap)
  const series = members.filter(code => pointsByPollutant[code]?.length).map(code => ({
    code,
    name: `${code}（${code === pair ? '同站互证' : '5分钟'}）`,
    unit: data.units?.[code] || 'μg/m³',
    color: colors[code],
    points: (pointsByPollutant[code] || []).filter(point => {
      const time = fiveMinuteTime(point.time)
      return time !== null && (start === null || time >= start) && (end === null || time <= end)
    }).map(point => flaggedOnly && !point.flag ? { ...point, value: null } : point),
  }))
  return { group: group ? { ...group, members } : undefined, series, window: [start, end] }
}

export function fiveMinuteTableRows(data = {}, members = [], { flaggedOnly = false, window = [] } = {}) {
  const codes = new Set(members)
  const keys = {
    PM10: ['pM10', 'PM10', 'pm10'], 'PM2.5': ['pM2_5', 'PM2.5', 'PM2_5', 'PM25', 'pm2_5'],
    SO2: ['sO2', 'SO2'], NO: ['no', 'NO'], NO2: ['nO2', 'NO2'],
    NOX: ['nOx', 'NOX', 'NOx', 'nox'], CO: ['co', 'CO'], O3: ['o3', 'O3'],
  }
  const [start, end] = window
  return (data.rows || []).filter(row => {
    const time = fiveMinuteTime(row?.timePoint || row?.time)
    return time !== null && (start == null || time >= start) && (end == null || time <= end)
  }).map(row => {
    const result = { time: row.timePoint || row.time, values: {} }
    for (const code of codes) {
      const key = (keys[code] || [code]).find(name => row[name] !== undefined && row[name] !== null && row[name] !== '')
      if (key) result.values[code] = row[key]
    }
    return result
  }).filter(row => Object.keys(row.values).length
    && (!flaggedOnly || Object.values(row.values).some(value => /[（(][^)）]+[)）]/.test(String(value)))))
}
