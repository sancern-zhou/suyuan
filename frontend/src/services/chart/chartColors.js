// 图表色板常量表 —— 与 src/styles/tokens.css 同步（UI_DESIGN_SPEC.md §3.1.5 / §7 / D11）
// ECharts option 为纯 JS 对象，无法消费 CSS 变量；本文件镜像令牌值，
// 禁止在 option 中写规范外色字面量，禁止 getComputedStyle 运行时读取。

// 序列色板（--chart-1..10），主序列始终第一
export const CHART_COLORS = Object.freeze([
  '#1890ff', // --chart-1
  '#52c41a', // --chart-2
  '#faad14', // --chart-3
  '#f5222d', // --chart-4
  '#722ed1', // --chart-5
  '#13c2c2', // --chart-6
  '#eb2f96', // --chart-7
  '#fa8c16', // --chart-8
  '#2f54eb', // --chart-9
  '#a0d911', // --chart-10
])

// 常用单色（镜像令牌）
export const CHART_PRIMARY = '#1890ff' // --color-primary
export const CHART_PRIMARY_LIGHT = '#69c0ff' // --color-primary-light
export const CHART_CONTRAST = '#bfbfbf' // 对比类衬色（--text-disabled）
export const CHART_PRIMARY_FILL = 'rgba(24, 144, 255, 0.15)' // 主色 15% 透明填充（--color-primary-ring 同源）
export const CHART_SUCCESS = '#52c41a' // --color-success
export const CHART_WARNING = '#faad14' // --color-warning
export const CHART_DANGER = '#f5222d' // --color-danger
export const CHART_ALARM = '#d4380d' // 业务告警比对色（antd volcano-6，§7.7 登记专用于告警差值序列）

// 文本/辅助（镜像中性令牌）
export const CHART_TEXT_1 = '#333333' // --text-1
export const CHART_TEXT_2 = '#666666' // --text-2（轴/图例/tooltip 文字）
export const CHART_TEXT_3 = '#999999' // --text-3
export const CHART_AXIS_LINE = '#d9d9d9' // --border-3（坐标轴线）
export const CHART_GRID_LINE = '#e8e8e8' // --border-2（网格线）
export const CHART_SPLIT_LINE = '#e8e8e8' // --border-2（分隔线）

// 公共片段（按 §7 约定组装）
export const AXIS_LABEL_STYLE = Object.freeze({ color: CHART_TEXT_2, fontSize: 12 })
export const AXIS_LINE_STYLE = Object.freeze({ lineStyle: { color: CHART_AXIS_LINE } })
export const SPLIT_LINE_STYLE = Object.freeze({ lineStyle: { type: 'dashed', color: CHART_GRID_LINE } })
export const LEGEND_STYLE = Object.freeze({
  top: 0,
  icon: 'roundRect',
  itemWidth: 10,
  itemHeight: 10,
  textStyle: { color: CHART_TEXT_2, fontSize: 12 },
})
export const TOOLTIP_STYLE = Object.freeze({
  backgroundColor: '#ffffff',
  borderColor: CHART_GRID_LINE,
  borderWidth: 1,
  textStyle: { color: CHART_TEXT_1, fontSize: 12 },
  extraCssText: 'box-shadow: 0 2px 8px rgba(31, 42, 68, 0.10);',
})

export default CHART_COLORS
