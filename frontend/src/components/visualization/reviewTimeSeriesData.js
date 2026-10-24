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

// 目标/对照之外的污染物曲线用色（避开同城带的灰/绿/黄三色）。
export const EXTRA_POLLUTANT_COLORS = ['#ff8a75', '#56d6c9', '#d7a84e', '#8fb4ff']
// 曲线单位覆盖：CO 与常规 μg/m³ 不同，其余与目标污染物一致。
export const POLLUTANT_UNIT_OVERRIDES = { CO: 'mg/m³' }
// 时序图对照配对（与后端 review_evidence.COMPARISON_POLLUTANTS 保持一致）：
// 每张图保留该污染物最有诊断意义的对照曲线（颗粒物互证倒挂、NO/NO2 同仪、O3↔NO2）。
export const CHART_COMPARISON_PAIRS = {
  PM10: 'PM2.5',
  'PM2.5': 'PM10',
  NO: 'NO2',
  NO2: 'NO',
  O3: 'NO2',
}

// 小时时序图按污染物拆图的共享装配。多目标污染物同图叠加时，目标曲线、对照曲线与
// 剔除区间互相遮挡难以辨认；这里为每个目标污染物各装配一张图（本站曲线 + 配对对照曲线 +
// 它自己的剔除区间），并保证同一污染物跨图同色。同城对比带只随主目标图显示
// （取证侧仅对主目标污染物取同城带）。
//
// 入参：data = 证据包 station_hour.data（pollutant/pollutants/comparison_*/points/extra_points），
// fallbackPollutant = 索引里的工单目标污染物（旧包 data.pollutant 缺失时兜底），
// markAreas = 审核回写的剔除区间，bandRows/bandComparisonCollapsed/bandDistrictName = 同城带叠加。
// 返回：{ charts, colorMap, stationPollutantSeries }：
// - charts: [{ pollutant, unit, series, markAreas }]，首项恒为主目标图（含同城带叠加）；
// - colorMap: 污染物 → 曲线色（气象图污染物面板与区间着色复用）；
// - stationPollutantSeries: 主目标图的站内曲线（剔除同城带叠加），气象图复用。
export function buildPollutantCharts({
  data = {},
  fallbackPollutant = '',
  markAreas = [],
  bandRows = [],
  bandComparisonCollapsed = false,
  bandDistrictName = '同域',
} = {}) {
  const targetCode = String(data.pollutant || fallbackPollutant || 'PM10').toUpperCase()
  const targetPoints = (data.points || []).map(point => ({ time: point.time, value: point.value }))
  if (!targetPoints.length) return { charts: [], colorMap: {}, stationPollutantSeries: [] }

  // 污染物 → 本站逐时序列：主目标取 points，包内对照取 comparison_points（旧包回落
  // pm25_points），其余取 extra_points；三处皆无则该污染物无曲线可画。
  const comparisonName = data.comparison_pollutant || (data.pm25_points?.length ? 'PM2.5' : '')
  const comparisonCode = String(comparisonName || '').toUpperCase()
  const seriesPoints = {}
  const put = (pollutant, points) => {
    if (!points?.length) return
    const code = String(pollutant || '').toUpperCase()
    if (code && !seriesPoints[code]) seriesPoints[code] = points
  }
  put(targetCode, data.points)
  if (comparisonCode && comparisonCode !== targetCode) {
    put(comparisonCode, data.comparison_points?.length
      ? data.comparison_points
      : (comparisonCode === 'PM2.5' ? data.pm25_points : []))
  }
  for (const [pollutant, points] of Object.entries(data.extra_points || {})) put(pollutant, points)

  // 出图污染物（保序）：主目标恒为首页；剔除区间涉及的污染物按 AI 提及顺序紧随；
  // 工单文本识别的其余目标污染物殿后。无曲线的污染物不占位。
  // 旧证据包无 pollutants 清单时只有主目标 + 剔除区间污染物。
  const areaOwnerPollutants = []
  for (const area of markAreas) {
    const owner = areaPollutant(area)
    if (owner && !areaOwnerPollutants.includes(owner)) areaOwnerPollutants.push(owner)
  }
  const chartPollutants = []
  for (const pollutant of [...areaOwnerPollutants, ...(Array.isArray(data.pollutants) ? data.pollutants : [])]) {
    const code = String(pollutant || '').trim().toUpperCase()
    if (code && !chartPollutants.includes(code) && (seriesPoints[code] || []).length) {
      chartPollutants.push(code)
    }
  }

  // 污染物 → 曲线色：目标/对照固定色，其余从补画色板取；各图的对照污染物也预占颜色，
  // 同一污染物在所有图里同色，与剔除区间标注的着色一致。
  const colorMap = { [targetCode]: '#2f86e0' }
  if (comparisonCode) colorMap[comparisonCode] = '#9b8cff'
  let extraIndex = 0
  const nextExtraColor = () => EXTRA_POLLUTANT_COLORS[extraIndex++ % EXTRA_POLLUTANT_COLORS.length]
  for (const pollutant of chartPollutants) {
    if (!colorMap[pollutant]) colorMap[pollutant] = nextExtraColor()
  }
  for (const pollutant of chartPollutants) {
    const pair = CHART_COMPARISON_PAIRS[pollutant]
    if (!pair || colorMap[pair] || !(seriesPoints[pair] || []).length) continue
    colorMap[pair] = nextExtraColor()
  }

  const pointsOf = pollutant => (pollutant === targetCode
    ? targetPoints
    : (seriesPoints[pollutant] || [])).map(point => ({ time: point.time, value: point.value }))
  const unitOf = pollutant => POLLUTANT_UNIT_OVERRIDES[pollutant] || data.unit || 'μg/m³'
  const seriesEntry = (pollutant, points, role) => ({
    name: `${pollutant}（${role}）`,
    unit: unitOf(pollutant),
    color: colorMap[pollutant] || '#2f86e0',
    points,
  })
  const withComparison = (pollutant, series) => {
    const pair = CHART_COMPARISON_PAIRS[pollutant]
    const points = pair && pair !== pollutant ? pointsOf(pair) : []
    if (points.length) series.push(seriesEntry(pair, points, '对照'))
    return series
  }
  // 区间归属：标注了污染物 → 该污染物的图；无归属或归属污染物无曲线（旧包无 extra_points）
  // → 落在主目标图，由图表回退默认琥珀色。
  const areasOf = pollutant => markAreas
    .filter(area => {
      const owner = areaPollutant(area)
      if (!owner) return pollutant === targetCode
      return owner === pollutant
        || (pollutant === targetCode && !(seriesPoints[owner] || []).length)
    })
    .map(area => {
      const color = colorMap[areaPollutant(area)]
      return color ? { ...area, color } : { ...area }
    })

  const mainSeries = withComparison(targetCode, [seriesEntry(targetCode, targetPoints, '本站')])
  if (bandRows.length) {
    const pick = key => bandRows.filter(row => row[key] != null).map(row => ({ time: row.time, value: row[key] }))
    // 同域只有 1 个对比站时最低/中位/最高三值相同，合并为一条线，避免三条重合曲线。
    const overlays = bandComparisonCollapsed
      ? [[`同城对比站（${bandDistrictName || '同域'}）`, '#f6bd4a', 'median']]
      : [['同城最低', '#94a3b8', 'min'], ['同城中位', '#61d394', 'median'], ['同城最高', '#f6bd4a', 'max']]
    overlays.forEach(([name, color, key]) => {
      const points = pick(key)
      if (points.length) mainSeries.push({ name, unit: data.unit || 'μg/m³', color, points })
    })
  }
  const charts = [{
    pollutant: targetCode,
    unit: unitOf(targetCode),
    series: mainSeries,
    markAreas: areasOf(targetCode),
  }]
  for (const pollutant of chartPollutants) {
    if (pollutant === targetCode) continue
    charts.push({
      pollutant,
      unit: unitOf(pollutant),
      series: withComparison(pollutant, [seriesEntry(pollutant, pointsOf(pollutant), '本站')]),
      markAreas: areasOf(pollutant),
    })
  }
  return {
    charts,
    colorMap,
    stationPollutantSeries: charts[0].series.filter(item => !String(item.name || '').startsWith('同城')),
  }
}
