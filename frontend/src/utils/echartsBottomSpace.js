/**
 * ECharts 底部空间估算
 *
 * 图例（底部）与 x 轴刻度文字重叠的根因是布局预留用固定常量
 * （刻度 24px / 图例 25px）。以下三种情形实际高度会超过常量：
 *  1. x 轴刻度旋转（rotate 45° 的长时间标签垂直投影远超 24px）
 *  2. x 轴刻度设置了 width + overflow:'break' 换行成多行
 *  3. 图例项多/名字长，横向图例换行成多行（bottom 锚定时向上生长）
 *
 * 这里按 option 内容启发式估算实际高度，调用方应取
 * max(常量, 估算值) 作为布局预留，保证不缩水。
 */

export const X_AXIS_LABEL_FALLBACK = 24
export const LEGEND_HEIGHT_FALLBACK = 25
const TIME_LABEL_SAMPLE = '2026-10-09 10:00'

export function estimateTextWidth(text, fontSize = 12) {
  let width = 0
  for (const ch of String(text ?? '')) {
    width += ch.codePointAt(0) > 0x2e7f ? fontSize : fontSize * 0.6
  }
  return width
}

const asList = (value) => (Array.isArray(value) ? value : (value ? [value] : []))

/**
 * 从轴定义与 series 数据里收集用于估宽的刻度文本样本。
 * category 轴直接用 data；time/value 轴从 series 数据点抽首/中/尾样本。
 */
export function collectAxisLabelSamples(xAxis, series = []) {
  const type = xAxis?.type || 'category'
  if (type === 'category' && Array.isArray(xAxis?.data) && xAxis.data.length) {
    return xAxis.data.map(v => (v == null ? '' : String(v)))
  }
  const samples = []
  for (const s of asList(series)) {
    if (!s || !Array.isArray(s.data)) continue
    for (const index of [0, Math.floor(s.data.length / 2), s.data.length - 1]) {
      const item = s.data[index]
      if (item == null) continue
      const x = Array.isArray(item)
        ? item[0]
        : (typeof item === 'object' ? (Array.isArray(item.value) ? item.value[0] : (item.name ?? item.value)) : item)
      if (x != null) samples.push(x instanceof Date ? x.toISOString() : String(x))
    }
  }
  if (!samples.length && type === 'time') samples.push(TIME_LABEL_SAMPLE)
  return samples
}

/**
 * 估算单个 x 轴刻度文字的垂直占用（px），不会低于 fallback。
 */
export function estimateXAxisLabelHeight(xAxis, series = [], fallback = X_AXIS_LABEL_FALLBACK) {
  if (!xAxis || typeof xAxis !== 'object') return fallback
  const label = (xAxis.axisLabel && typeof xAxis.axisLabel === 'object') ? xAxis.axisLabel : {}
  if (label.show === false) return 0
  const fontSize = Number(label.fontSize) || 12
  const rotate = Math.abs(Number(label.rotate) || 0)
  const samples = collectAxisLabelSamples(xAxis, series)
  if (!samples.length) return fallback
  const longest = samples.reduce((m, s) => (s.length > m.length ? s : m), '')
  const textWidth = estimateTextWidth(longest, fontSize)
  let height
  if (rotate > 0) {
    const rad = (rotate * Math.PI) / 180
    height = textWidth * Math.sin(rad) + fontSize * 1.25 * Math.cos(rad)
  } else {
    const wrapWidth = Number(label.width) || 0
    const breaks = wrapWidth > 0 && /break/i.test(String(label.overflow || ''))
    const lines = breaks ? Math.max(1, Math.ceil(textWidth / wrapWidth)) : 1
    height = lines * fontSize * 1.25
  }
  return Math.max(fallback, Math.ceil(height))
}

function legendItemNames(legend, option) {
  if (Array.isArray(legend?.data) && legend.data.length) {
    return legend.data
      .map(v => (typeof v === 'object' && v !== null ? String(v.name ?? '') : String(v)))
      .filter(Boolean)
  }
  return [...new Set(asList(option?.series)
    .map(s => (typeof s?.name === 'string' ? s.name : ''))
    .filter(Boolean))]
}

/**
 * 估算底部图例块的总高度（px），不会低于 fallback。
 * scroll 图例恒为单行；普通横向图例按总宽度与容器可用宽度折算行数。
 */
export function estimateLegendHeight(legend, option = {}, containerWidth = 800, fallback = LEGEND_HEIGHT_FALLBACK) {
  let max = fallback
  for (const item of asList(legend)) {
    if (!item || typeof item !== 'object' || item.show === false) continue
    const names = legendItemNames(item, option)
    if (!names.length) continue
    const fontSize = (item.textStyle && Number(item.textStyle.fontSize)) || 12
    if (item.type === 'scroll') {
      max = Math.max(max, Math.ceil(fontSize * 1.7))
      continue
    }
    const itemGap = Number(item.itemGap ?? 10)
    const totalWidth = names.reduce((sum, name) => sum + 25 + estimateTextWidth(name, fontSize) + itemGap, 0)
    const usable = Math.max(Number(containerWidth) - 60, 180)
    const rows = Math.max(1, Math.ceil(totalWidth / usable))
    const height = rows * (fontSize + 7) + (rows - 1) * itemGap
    max = Math.max(max, Math.ceil(height))
  }
  return max
}
