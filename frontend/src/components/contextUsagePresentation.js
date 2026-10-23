// 上下文占用指示器的展示计算：环形进度、分段占比与格式化。
// breakdown 语义对齐 ZCode：分项占比在分项内部归一化，不与总量口径混合。

export const CONTEXT_BREAKDOWN_ORDER = [
  { source: 'messages', label: '消息' },
  { source: 'system_prompt', label: '系统提示词' },
  { source: 'tools', label: '工具' }
]

// 同色系由深到浅，与分段条/明细行共用
export const CONTEXT_BREAKDOWN_COLORS = [
  '#2878ff',
  'rgba(40, 120, 255, 0.6)',
  'rgba(40, 120, 255, 0.3)'
]

export const CONTEXT_RING_RADIUS = 10
export const CONTEXT_RING_CIRCUMFERENCE = 2 * Math.PI * CONTEXT_RING_RADIUS

export function normalizeContextBreakdown(breakdown) {
  const rows = []
  if (!breakdown || typeof breakdown !== 'object') return rows
  for (const { source, label } of CONTEXT_BREAKDOWN_ORDER) {
    const tokens = Number(breakdown[source])
    if (Number.isFinite(tokens) && tokens > 0) {
      rows.push({ source, label, tokens })
    }
  }
  return rows
}

export function buildContextUsageSegments(breakdown) {
  const rows = normalizeContextBreakdown(breakdown)
  const total = rows.reduce((sum, row) => sum + row.tokens, 0)
  if (total <= 0) return []
  return rows.map((row, index) => ({
    ...row,
    percent: row.tokens / total,
    color: CONTEXT_BREAKDOWN_COLORS[Math.min(index, CONTEXT_BREAKDOWN_COLORS.length - 1)]
  }))
}

export function contextUsagePercent(used, size) {
  const usedTokens = Number(used)
  const windowTokens = Number(size)
  if (!Number.isFinite(usedTokens) || !Number.isFinite(windowTokens) || windowTokens <= 0 || usedTokens <= 0) {
    return null
  }
  return Math.min(100, Math.round((usedTokens / windowTokens) * 100))
}

export function ringDashOffset(percent) {
  if (percent === null || !Number.isFinite(percent)) return CONTEXT_RING_CIRCUMFERENCE
  return CONTEXT_RING_CIRCUMFERENCE * (1 - Math.min(Math.max(percent, 0), 100) / 100)
}

export function formatContextTokens(value) {
  const tokens = Number(value)
  if (!Number.isFinite(tokens) || tokens <= 0) return '0'
  if (tokens < 1000) return String(Math.round(tokens))
  if (tokens < 1_000_000) {
    const k = tokens / 1000
    return `${Number.isInteger(k) ? k : k.toFixed(1).replace(/\.0$/, '')}K`
  }
  const m = tokens / 1_000_000
  return `${Number.isInteger(m) ? m : m.toFixed(1).replace(/\.0$/, '')}M`
}

export function formatContextCacheHitRate(hitRate, { threshold = 0.78 } = {}) {
  const rate = Number(hitRate)
  if (!Number.isFinite(rate) || rate < threshold) return null
  return `${Math.round(rate * 100)}%`
}
