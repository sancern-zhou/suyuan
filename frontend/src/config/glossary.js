// 业务术语表（UI_DESIGN_SPEC.md §5.3 唯一真源）
// 规则：
// 1. 每个业务概念全平台只有一个中文名，组件只引用本表常量，禁止在模板写裸字符串业务名。
// 2. 新增业务概念必须先在此登记，再开发界面。
// 3. 枚举/状态码必须映射为业务中文后展示，禁止直接渲染后端原始值（§5.1）。

export const BUSINESS_TERMS = Object.freeze({
  dataSource: '数据源',
  scheduledTask: '定时任务',
  knowledgeBase: '知识库',
  sessionHistory: '会话历史',
  tool: '工具',
  skill: '技能',
  station: '站点',
  fence: '围栏',
  device: '设备',
  alarm: '告警',
  report: '报告',
  document: '文档',
  fetcher: '数据源',
  task: '任务',
  session: '会话',
})

export const EMPTY_TEXT = Object.freeze({
  noData: '暂无数据',
  notSet: '未设置',
  unknown: '未知',
  loading: '正在加载，请稍候…',
  noPermission: '暂无权限查看该内容，请联系管理员',
  networkError: '网络超时，请检查网络后重试',
  serverBusy: '系统繁忙，请稍后重试',
})

const NULL_LITERALS = new Set(['null', 'undefined', 'nan', '{}'])

// 空值不裸露（§5.1）：null/undefined/NaN/空串 → 统一业务文案
export function formatNullable(value, fallback = EMPTY_TEXT.noData) {
  if (value === null || value === undefined || value === '') return fallback
  if (typeof value === 'number' && Number.isNaN(value)) return fallback
  if (typeof value === 'string' && NULL_LITERALS.has(value.trim().toLowerCase())) return fallback
  return value
}

export function term(key) {
  return BUSINESS_TERMS[key] || key
}

export default BUSINESS_TERMS
