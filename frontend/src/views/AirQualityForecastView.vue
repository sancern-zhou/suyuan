<template>
  <main class="forecast-page" :class="{ embedded }">
    <header v-if="!embedded" class="page-header">
      <div>
        <p class="eyebrow">空气质量预报</p>
        <h1>许昌市逐小时预报预测</h1>
      </div>
    </header>

    <section v-if="dailyForecasts.length" class="daily-forecast" aria-label="未来五天逐日AQI预报">
      <div
        v-for="item in dailyForecasts"
        :key="item.date"
        class="daily-card"
        :style="{ borderTopColor: aqiColor(item.aqi) }"
      >
        <p class="daily-date">{{ formatDailyDate(item.date) }}</p>
        <p class="daily-weekday">{{ formatDailyWeekday(item.date) }}</p>
        <p class="daily-aqi" :style="{ color: aqiColor(item.aqi) }">{{ aqiRangeText(item) }}</p>
        <p class="daily-level">{{ dailyLevelName(item) }}</p>
        <p class="daily-pollutant" v-if="item.primary_pollutant">首要污染物：{{ item.primary_pollutant }}</p>
      </div>
    </section>

    <section class="toolbar" aria-label="预报筛选">
      <label class="field-label">
        <span>指标</span>
        <select v-model="metric">
          <option v-for="item in metrics" :key="item.key" :value="item.key">{{ item.label }}</option>
        </select>
      </label>
      <div class="legend" aria-label="浓度等级图例">
        <span v-for="level in legendLevels" :key="level.label"><i :style="{ background: level.color }"></i>{{ level.label }}</span>
      </div>
      <div class="source-time" v-if="data.reference_time">更新基准：{{ formatTime(data.reference_time) }} 北京时间</div>
    </section>

    <section class="chart-section">
      <div v-if="loading" class="status">正在加载逐小时数据...</div>
      <div v-else-if="error" class="status error">{{ error }}</div>
      <template v-else>
        <div ref="chartEl" class="forecast-chart" aria-label="空气质量逐小时预报和观测图"></div>
        <div class="series-key">
          <span><i class="forecast-key"></i>预报</span>
          <span><i class="observed-key"></i>观测</span>
          <span>{{ visibleRangeText }}</span>
          <span class="zoom-hint">滚轮缩放 · 拖拽平移</span>
        </div>
      </template>
    </section>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { fetchXuchangHourlyForecast } from '@/api/airQualityForecast.js'

defineProps({
  embedded: {
    type: Boolean,
    default: false
  }
})
const chartEl = ref(null)
const chart = ref(null)
const loading = ref(true)
const error = ref('')
const data = ref({ observations: [], forecasts: [], reference_time: '' })
const dailyForecasts = ref([])
const metric = ref('aqi')
const visibleRangeText = ref('暂无可展示时段')
const zoomWindow = { start: 0, end: 100 }
let chartResizeObserver = null

const metrics = [
  { key: 'aqi', label: 'AQI', unit: '' },
  { key: 'pm25', label: 'PM2.5', unit: 'μg/m³' },
  { key: 'pm10', label: 'PM10', unit: 'μg/m³' },
  { key: 'o3', label: 'O3', unit: 'μg/m³' },
  { key: 'no2', label: 'NO2', unit: 'μg/m³' }
]
const activeMetric = computed(() => metrics.find(item => item.key === metric.value) || metrics[0])

const thresholds = {
  aqi: [50, 100, 150, 200, 300],
  pm25: [35, 75, 115, 150, 250],
  pm10: [50, 150, 250, 350, 420],
  o3: [160, 200, 300, 400, 800],
  no2: [80, 200, 700, 1200, 2340]
}
const levelPalette = ['#21a366', '#e5ae22', '#ee7d32', '#d85245', '#914c95', '#7a2432']
const legendLevels = computed(() => [
  { label: '优', color: levelPalette[0] }, { label: '良', color: levelPalette[1] },
  { label: '轻度', color: levelPalette[2] }, { label: '中度', color: levelPalette[3] },
  { label: '重度', color: levelPalette[4] }, { label: '严重', color: levelPalette[5] }
])

const timeline = computed(() => {
  const merged = new Map()
  data.value.observations.forEach(row => merged.set(row.time, { time: row.time, observation: row, forecast: null }))
  data.value.forecasts.forEach(row => {
    const item = merged.get(row.time) || { time: row.time, observation: null, forecast: null }
    item.forecast = row
    merged.set(row.time, item)
  })
  return [...merged.values()].sort((a, b) => new Date(a.time) - new Date(b.time))
})

function updateVisibleRange() {
  const rows = timeline.value
  if (!chart.value || !rows.length) {
    visibleRangeText.value = '暂无可展示时段'
    return
  }
  const zoom = chart.value.getOption()?.dataZoom?.[0]
  if (zoom) {
    zoomWindow.start = zoom.start ?? 0
    zoomWindow.end = zoom.end ?? 100
  }
  const lastIndex = rows.length - 1
  const startIndex = Math.round((zoomWindow.start / 100) * lastIndex)
  const endIndex = Math.round((zoomWindow.end / 100) * lastIndex)
  const from = rows[startIndex]?.time
  const to = rows[endIndex]?.time
  visibleRangeText.value = from && to ? `${formatTime(from)} 至 ${formatTime(to)}` : '暂无可展示时段'
}

function applyZoomWindow(start, end) {
  zoomWindow.start = start
  zoomWindow.end = end
  chart.value?.dispatchAction({ type: 'dataZoom', start, end })
}

function onWheel(event) {
  if (!chart.value || !timeline.value.length) return
  event.preventDefault()
  const rect = chartEl.value.getBoundingClientRect()
  if (!rect.width) return
  const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1)
  const span = zoomWindow.end - zoomWindow.start
  const minSpan = Math.max((8 / timeline.value.length) * 100, 1)
  const factor = event.deltaY > 0 ? 1.25 : 1 / 1.25
  const newSpan = Math.min(100, Math.max(minSpan, span * factor))
  const anchor = (zoomWindow.start + ratio * span) / 100
  let newStart = anchor * 100 - ratio * newSpan
  newStart = Math.min(Math.max(newStart, 0), 100 - newSpan)
  applyZoomWindow(newStart, newStart + newSpan)
}

let dragState = null

function onDragStart(event) {
  if (!chart.value || event.button !== 0) return
  event.preventDefault()
  dragState = { x: event.clientX, start: zoomWindow.start, end: zoomWindow.end }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function onDragMove(event) {
  if (!dragState || !chartEl.value) return
  const rect = chartEl.value.getBoundingClientRect()
  if (!rect.width) return
  const span = dragState.end - dragState.start
  const shift = -((event.clientX - dragState.x) / rect.width) * span
  let newStart = dragState.start + shift
  newStart = Math.min(Math.max(newStart, 0), 100 - span)
  applyZoomWindow(newStart, newStart + span)
}

function onDragEnd() {
  dragState = null
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
}

function formatTime(value) {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', hour12: false
  }).format(new Date(value)).replace(/\//g, '-').replace(' ', ' ')
}

function formatHour(value) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', hour: '2-digit', hourCycle: 'h23'
  }).format(new Date(value))
}

function formatDate(value) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit'
  }).format(new Date(value)).replace(/\//g, '-')
}

function colorFor(value) {
  if (value === null || value === undefined) return '#9aa5ad'
  const index = thresholds[metric.value].findIndex(limit => value <= limit)
  return levelPalette[index === -1 ? levelPalette.length - 1 : index]
}

function aqiColor(value) {
  if (value === null || value === undefined) return '#9aa5ad'
  const index = thresholds.aqi.findIndex(limit => value <= limit)
  return levelPalette[index === -1 ? levelPalette.length - 1 : index]
}

const aqiLevelNames = ['优', '良', '轻度污染', '中度污染', '重度污染', '严重污染']

function dailyLevelName(item) {
  if (item.aqi === null || item.aqi === undefined) return item.level || '暂无等级'
  const index = thresholds.aqi.findIndex(limit => item.aqi <= limit)
  return aqiLevelNames[index === -1 ? aqiLevelNames.length - 1 : index]
}

function aqiRangeText(item) {
  if (item.min_aqi != null && item.max_aqi != null) return `${item.min_aqi}~${item.max_aqi}`
  return item.aqi ?? '--'
}

function formatDailyDate(value) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit'
  }).format(new Date(value)).replace(/\//g, '-')
}

function formatDailyWeekday(value) {
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', weekday: 'long' }).format(new Date(value))
}

function renderChart() {
  if (!chartEl.value || !timeline.value.length) return
  if (!chart.value) {
    chart.value = echarts.init(chartEl.value)
    chart.value.on('dataZoom', updateVisibleRange)
  }
  const rows = timeline.value
  const hourLabels = rows.map(row => formatHour(row.time))
  const dates = rows.map(row => formatDate(row.time))
  const dateLabels = dates.map((date, index) => index === 0 || dates[index - 1] !== date ? date : '')
  const currentIndex = rows.findIndex(row => row.time === data.value.reference_time)
  chart.value.setOption({
    animationDuration: 180,
    grid: { left: 8, right: 8, top: 36, bottom: 102, containLabel: true },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        zoomOnMouseWheel: false,
        moveOnMouseMove: false,
        moveOnMouseWheel: false,
        filterMode: 'none',
        start: zoomWindow.start,
        end: zoomWindow.end
      }
    ],
    tooltip: {
      show: true,
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
        shadowStyle: { color: 'rgba(41, 101, 94, 0.08)' }
      },
      backgroundColor: '#18232b', borderWidth: 0, padding: [9, 12], textStyle: { color: '#fff' },
      formatter(params) {
        const point = rows[params[0]?.dataIndex] || {}
        const unit = activeMetric.value.unit ? ` ${activeMetric.value.unit}` : ''
        const lines = [`<strong>${formatTime(point.time)} 北京时间</strong>`]
        params.forEach(item => {
          if (item.value !== null && item.value !== undefined) lines.push(`${item.marker}${item.seriesName}：${item.value}${unit}`)
        })
        return lines.join('<br>')
      }
    },
    xAxis: [
      {
        type: 'category', data: hourLabels,
        axisLine: { lineStyle: { color: '#aeb9bf' } }, axisTick: { alignWithLabel: true },
        axisLabel: { color: '#64747d', margin: 10 }
      },
      {
        type: 'category', data: dateLabels, position: 'bottom', offset: 31,
        axisLine: { lineStyle: { color: '#cbd4d3' } }, axisTick: { show: false },
        axisLabel: { color: '#52636a', fontWeight: 600, margin: 9, interval: 0 }
      }
    ],
    yAxis: { type: 'value', name: `${activeMetric.value.label}${activeMetric.value.unit ? ` (${activeMetric.value.unit})` : ''}`, nameTextStyle: { color: '#60717a' }, axisLabel: { color: '#64747d' }, splitLine: { lineStyle: { color: '#e8edef' } } },
    series: [
      {
        name: '预报', type: 'bar', barMaxWidth: 20,
        data: rows.map(row => row.forecast?.[metric.value] == null ? null : ({ value: row.forecast[metric.value], itemStyle: { color: colorFor(row.forecast[metric.value]) } })),
        emphasis: { focus: 'series' },
        markLine: currentIndex < 0 ? undefined : {
          silent: true, symbol: 'none', lineStyle: { color: '#6d7880', type: 'dashed', width: 1.5 },
          label: { show: true, formatter: '当前时间', color: '#53646c', position: 'insideEndTop' },
          data: [{ xAxis: currentIndex }]
        }
      },
      {
        name: '观测', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5, connectNulls: false,
        itemStyle: { color: '#176f89' }, lineStyle: { width: 2.5, color: '#176f89' },
        data: rows.map(row => row.observation?.[metric.value] ?? null)
      }
    ]
  }, true)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchXuchangHourlyForecast()
    dailyForecasts.value = data.value.daily_forecasts || []
    loading.value = false
    await nextTick()
    await new Promise(resolve => requestAnimationFrame(resolve))
    renderChart()
    updateVisibleRange()
  } catch (err) {
    error.value = err.message || '预报数据加载失败'
  } finally {
    loading.value = false
  }
}

watch(metric, () => {
  renderChart()
  updateVisibleRange()
})
watch(chartEl, (element, previous) => {
  if (previous) {
    previous.removeEventListener('wheel', onWheel)
    previous.removeEventListener('mousedown', onDragStart)
    chartResizeObserver?.unobserve(previous)
  }
  if (element) {
    chartResizeObserver?.observe(element)
    element.addEventListener('wheel', onWheel, { passive: false })
    element.addEventListener('mousedown', onDragStart)
  }
})
const onResize = () => chart.value?.resize()
const onTransitionEnd = (event) => {
  if (event.target === chartEl.value) return
  requestAnimationFrame(() => chart.value?.resize())
}
onMounted(() => {
  load()
  window.addEventListener('resize', onResize)
  window.addEventListener('transitionend', onTransitionEnd)
  chartResizeObserver = new ResizeObserver(() => {
    chart.value?.resize()
    updateVisibleRange()
  })
  if (chartEl.value) chartResizeObserver.observe(chartEl.value)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('transitionend', onTransitionEnd)
  chartResizeObserver?.disconnect()
  onDragEnd()
  const el = chartEl.value
  if (el) {
    el.removeEventListener('wheel', onWheel)
    el.removeEventListener('mousedown', onDragStart)
  }
  chart.value?.dispose()
})
</script>

<style scoped>
.forecast-page { min-height: 100vh; padding: 30px 38px 42px; background: #f4f7f6; color: #18262d; }
.forecast-page.embedded { min-height: 100%; height: 100%; overflow: auto; box-sizing: border-box; padding: 18px 26px 22px; background: #fff; display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; max-width: 1480px; margin: 0 auto 24px; border-bottom: 1px solid #d9e1df; padding-bottom: 20px; }
.eyebrow { margin: 0 0 7px; font-size: 13px; color: #38756b; font-weight: 700; letter-spacing: 0; }
h1 { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: 0; }
.back-button { border: 1px solid #9ab1ac; border-radius: 4px; background: #fff; padding: 8px 12px; color: #245c54; cursor: pointer; font-size: 14px; }
.toolbar, .chart-section { max-width: 1480px; margin: 0 auto; background: #fff; border: 1px solid #dbe4e2; border-radius: 6px; }
.toolbar { min-height: 72px; display: flex; align-items: center; gap: 28px; padding: 12px 20px; }
.embedded .toolbar, .embedded .chart-section { width: 100%; max-width: none; margin: 0; background: transparent; border: 0; border-radius: 0; }
.embedded .toolbar { min-height: 48px; padding: 0 0 12px; border-bottom: 1px solid #e3eae8; }
.field-label { display: flex; align-items: center; gap: 10px; font-size: 14px; color: #4d5e66; }
select { height: 34px; min-width: 120px; border: 1px solid #aebfbb; border-radius: 4px; background: #fff; color: #1f2d33; padding: 0 8px; }
.legend { display: flex; flex-wrap: wrap; gap: 13px; font-size: 12px; color: #607079; }
.legend span, .series-key span { display: inline-flex; gap: 5px; align-items: center; white-space: nowrap; }
.legend i { width: 10px; height: 10px; border-radius: 50%; }
.source-time { margin-left: auto; font-size: 12px; color: #718087; white-space: nowrap; }
.chart-section { margin-top: 16px; padding: 18px 8px 20px; }
.forecast-chart { height: min(57vh, 560px); min-height: 360px; cursor: grab; }
.embedded .chart-section { margin: 0; padding: 0; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.embedded .forecast-chart { height: clamp(470px, calc(100vh - 250px), 820px); min-height: 470px; flex: 1; }
.series-key { border-top: 1px solid #edf1f0; padding: 12px 2px 0; display: flex; gap: 22px; color: #596a72; font-size: 12px; }
.forecast-key, .observed-key { display: inline-block; width: 16px; height: 9px; }.forecast-key { background: #2f9e63; }.observed-key { background: #176f89; height: 3px; }
.daily-forecast { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.daily-card { background: #fff; border: 1px solid #dbe4e2; border-top: 4px solid #9aa5ad; border-radius: 6px; padding: 14px 16px 12px; text-align: center; }
.daily-date { margin: 0; font-size: 15px; font-weight: 700; color: #1f2d33; }
.daily-weekday { margin: 2px 0 10px; font-size: 12px; color: #718087; }
.daily-aqi { margin: 0; font-size: 30px; font-weight: 700; line-height: 1.1; }
.daily-level { margin: 6px 0 0; font-size: 13px; color: #4d5e66; }
.daily-pollutant { margin: 4px 0 0; font-size: 12px; color: #8a979e; }
.zoom-hint { margin-left: auto; color: #8a979e; }
.status { min-height: 430px; display: grid; place-items: center; color: #64747d; }.error { color: #b4403a; }
@media (max-width: 760px) { .forecast-page { padding: 18px 14px; }.page-header { align-items: center; }.page-header h1 { font-size: 21px; }.daily-forecast { grid-template-columns: repeat(2, 1fr); }.toolbar { align-items: flex-start; flex-direction: column; gap: 12px; }.source-time { margin-left: 0; }.forecast-chart { height: 420px; min-height: 0; }.series-key { flex-wrap: wrap; gap: 12px; } }
</style>
