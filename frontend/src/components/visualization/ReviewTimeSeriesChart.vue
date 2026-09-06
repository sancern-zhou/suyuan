<template>
  <article class="review-timeseries-card">
    <header class="chart-head">
      <div>
        <strong>{{ title }}</strong>
        <span v-if="subtitle">{{ subtitle }}</span>
      </div>
      <em>{{ summaryText }}</em>
    </header>

    <div v-if="normalizedMarkAreas.length" class="mark-area-list" aria-label="剔除候选区间">
      <span v-for="area in normalizedMarkAreas" :key="`${area.name}-${area.start}-${area.end}`" class="mark-area-pill">
        <b>{{ area.name }}</b>
        <em>{{ area.rangeText }}</em>
      </span>
    </div>

    <div
      v-if="hasData"
      ref="chartRef"
      class="chart-surface"
      :style="{ height: `${height}px` }"
    ></div>
    <div v-else class="chart-empty">无可绘制曲线</div>
  </article>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  TooltipComponent
} from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  TooltipComponent,
  LineChart,
  CanvasRenderer
])

const props = defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  unit: { type: String, default: '' },
  height: { type: Number, default: 260 },
  series: { type: Array, default: () => [] },
  markAreas: { type: Array, default: () => [] }
})

const chartRef = ref(null)
let chart = null
let resizeObserver = null

const colors = ['#62c6ff', '#61d394', '#f6bd4a', '#ff8a75', '#9b8cff', '#56d6c9', '#d7a84e', '#8fb4ff']

const parseTimeValue = value => {
  if (!value) return null
  const raw = String(value).trim()
  const timestamp = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'))
  return Number.isFinite(timestamp) ? timestamp : null
}

const formatTime = value => {
  const timestamp = typeof value === 'number' ? value : parseTimeValue(value)
  if (!Number.isFinite(timestamp)) return String(value || '-')
  const date = new Date(timestamp)
  const pad = number => String(number).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const formatFullTime = value => {
  const timestamp = typeof value === 'number' ? value : parseTimeValue(value)
  if (!Number.isFinite(timestamp)) return String(value || '-')
  const date = new Date(timestamp)
  const pad = number => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const numberText = value => {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return Math.abs(number) >= 100 ? number.toFixed(0) : number.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
}

const normalizedSeries = computed(() => props.series
  .map((item, index) => {
    const points = (Array.isArray(item?.points) ? item.points : [])
      .map(point => {
        const time = parseTimeValue(point?.time)
        const value = Number(point?.value)
        if (!Number.isFinite(time) || !Number.isFinite(value)) return null
        return [time, value]
      })
      .filter(Boolean)
      .sort((left, right) => left[0] - right[0])
    return {
      name: item?.name || `序列 ${index + 1}`,
      color: item?.color || colors[index % colors.length],
      unit: item?.unit || '',
      axis: item?.axis === 'right' ? 'right' : 'left',
      points
    }
  })
  .filter(item => item.points.length))

const totalPoints = computed(() => normalizedSeries.value.reduce((sum, item) => sum + item.points.length, 0))
const hasData = computed(() => totalPoints.value > 0)
const summaryText = computed(() => hasData.value ? `${normalizedSeries.value.length} 组 / ${totalPoints.value} 点` : '0 点')
const hasRightAxis = computed(() => normalizedSeries.value.some(item => item.axis === 'right'))
const seriesUnitMap = computed(() => Object.fromEntries(
  normalizedSeries.value.map(item => [item.name, item.unit]).filter(([, unit]) => unit)
))
const chartYAxis = computed(() => {
  const leftAxis = {
    type: 'value',
    name: props.unit,
    nameTextStyle: { color: '#111827', fontSize: 10, padding: [0, 0, 4, 0] },
    axisLabel: { color: '#111827', fontSize: 10 },
    splitLine: { lineStyle: { color: 'rgba(17, 24, 39, .12)' } }
  }
  if (!hasRightAxis.value) return leftAxis
  return [
    leftAxis,
    {
      type: 'value',
      name: 'O3',
      position: 'right',
      nameTextStyle: { color: '#111827', fontSize: 10, padding: [0, 0, 4, 0] },
      axisLabel: { color: '#111827', fontSize: 10 },
      splitLine: { show: false }
    }
  ]
})

const normalizedMarkAreas = computed(() => (Array.isArray(props.markAreas) ? props.markAreas : [])
  .map(area => {
    const start = parseTimeValue(area?.start)
    const end = parseTimeValue(area?.end)
    if (!Number.isFinite(start) || !Number.isFinite(end)) return null
    const orderedStart = Math.min(start, end)
    const orderedEnd = Math.max(start, end)
    const name = area?.name || '剔除候选'
    return {
      name,
      start: orderedStart,
      end: orderedEnd,
      rangeText: `${formatFullTime(orderedStart)} 至 ${formatFullTime(orderedEnd)}`,
      chartLabel: area?.label || `${name}\n${formatTime(orderedStart)} 至 ${formatTime(orderedEnd)}`
    }
  })
  .filter(Boolean))

const tooltipFormatter = params => {
  const rows = Array.isArray(params) ? params : [params]
  const timestamp = rows[0]?.value?.[0]
  const title = timestamp ? formatTime(timestamp) : ''
  const lines = rows
    .filter(item => Array.isArray(item?.value))
    .map(item => {
      const unit = seriesUnitMap.value[item.seriesName] || props.unit
      return `${item.marker}${item.seriesName}：${numberText(item.value[1])}${unit ? ` ${unit}` : ''}`
    })
  const activeAreas = Number.isFinite(timestamp)
    ? normalizedMarkAreas.value.filter(area => timestamp >= area.start && timestamp <= area.end)
    : []
  for (const area of activeAreas) {
    lines.push(`剔除候选：${area.name}（${area.rangeText}）`)
  }
  return [title, ...lines].filter(Boolean).join('<br/>')
}

const chartOption = computed(() => ({
  animationDuration: 260,
  color: normalizedSeries.value.map(item => item.color),
  tooltip: {
    trigger: 'axis',
    confine: true,
    backgroundColor: 'rgba(255, 255, 255, 0)',
    borderColor: 'rgba(17, 24, 39, .24)',
    textStyle: { color: '#111827', fontSize: 11 },
    formatter: tooltipFormatter
  },
  legend: {
    type: 'scroll',
    top: 8,
    left: 8,
    right: 8,
    itemWidth: 16,
    itemHeight: 3,
    textStyle: { color: '#111827', fontSize: 11 }
  },
  grid: { top: 54, right: hasRightAxis.value ? 48 : 18, bottom: 58, left: 48, containLabel: true },
  xAxis: {
    type: 'time',
    boundaryGap: false,
    axisLine: { lineStyle: { color: 'rgba(17, 24, 39, .24)' } },
    axisTick: { show: false },
    axisLabel: { color: '#111827', fontSize: 10, formatter: formatTime }
  },
  yAxis: chartYAxis.value,
  dataZoom: [
    { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
    {
      type: 'slider',
      xAxisIndex: 0,
      height: 20,
      bottom: 16,
      borderColor: 'rgba(17, 24, 39, .22)',
      fillerColor: 'rgba(17, 24, 39, .08)',
      handleStyle: { color: '#111827' },
      textStyle: { color: '#111827', fontSize: 10 },
      filterMode: 'none'
    }
  ],
  series: normalizedSeries.value.map((item, index) => ({
    name: item.name,
    type: 'line',
    smooth: 0.18,
    yAxisIndex: item.axis === 'right' ? 1 : 0,
    showSymbol: item.points.length <= 48,
    symbolSize: 4,
    connectNulls: false,
    lineStyle: { width: index === 0 ? 2.4 : 1.8 },
    emphasis: { focus: 'series' },
    data: item.points,
    markArea: index === 0 && normalizedMarkAreas.value.length
      ? {
          silent: true,
          itemStyle: { color: 'rgba(246, 189, 74, .13)' },
          label: { color: '#111827', fontSize: 10, lineHeight: 14 },
          data: normalizedMarkAreas.value.map(area => [
            { name: area.chartLabel, xAxis: area.start },
            { xAxis: area.end }
          ])
        }
      : undefined
  }))
}))

const renderChart = () => {
  if (!chartRef.value || !hasData.value) return
  if (!chart) chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  chart.setOption(chartOption.value, true)
}

watch(chartOption, () => nextTick(renderChart), { deep: true })

onMounted(() => {
  renderChart()
  if (chartRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  } else {
    window.addEventListener('resize', renderChart)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', renderChart)
  chart?.dispose()
})
</script>

<style scoped>
.review-timeseries-card { display: grid; gap: 8px; min-width: 0; padding: 10px; border: 1px solid rgba(17, 24, 39, .16); border-radius: 4px; background: transparent; }
.chart-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; min-width: 0; }
.chart-head > div { display: grid; gap: 4px; min-width: 0; }
.chart-head strong { min-width: 0; color: #111827; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chart-head span { color: #111827; font-size: 11px; line-height: 1.45; overflow-wrap: anywhere; }
.chart-head em { flex: none; color: #111827; font-size: 11px; font-style: normal; }
.mark-area-list { display: flex; flex-wrap: wrap; gap: 6px; min-width: 0; }
.mark-area-pill { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 4px 7px; border: 1px solid rgba(180, 83, 9, .28); border-radius: 4px; background: rgba(246, 189, 74, .15); color: #111827; font-size: 11px; line-height: 1.35; }
.mark-area-pill b { flex: none; font-weight: 700; }
.mark-area-pill em { min-width: 0; color: #111827; font-style: normal; overflow-wrap: anywhere; }
.chart-surface { width: 100%; min-height: 220px; border: 1px solid rgba(17, 24, 39, .12); border-radius: 4px; background: transparent; }
.chart-empty { padding: 42px 10px; border: 1px dashed rgba(17, 24, 39, .2); border-radius: 4px; color: #111827; text-align: center; font-size: 12px; }
@media (max-width: 720px) {
  .chart-head { align-items: stretch; flex-direction: column; gap: 6px; }
  .chart-head em { flex: initial; }
}
</style>
