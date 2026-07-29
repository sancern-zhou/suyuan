<template>
  <main class="forecast-page" :class="{ embedded }">
    <header v-if="!embedded" class="page-header">
      <div>
        <p class="eyebrow">空气质量预报</p>
        <h1>许昌市逐小时预报预测</h1>
      </div>
    </header>

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
        </div>
        <div class="range-control">
          <div class="range-labels"><span>展示时段</span><strong>{{ visibleRangeText }}</strong></div>
          <div class="range-sliders">
            <input v-model.number="rangeStart" type="range" :min="0" :max="maxIndex" step="1" aria-label="展示起始时间" />
            <input v-model.number="rangeEnd" type="range" :min="0" :max="maxIndex" step="1" aria-label="展示结束时间" />
          </div>
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
const metric = ref('aqi')
const rangeStart = ref(0)
const rangeEnd = ref(0)
let chartResizeObserver = null

const metrics = [
  { key: 'aqi', label: 'AQI', unit: '' },
  { key: 'pm25', label: 'PM2.5', unit: 'μg/m³' },
  { key: 'pm10', label: 'PM10', unit: 'μg/m³' },
  { key: 'o3', label: 'O3', unit: 'μg/m³' },
  { key: 'no2', label: 'NO2', unit: 'μg/m³' },
  { key: 'so2', label: 'SO2', unit: 'μg/m³' },
  { key: 'co', label: 'CO', unit: 'μg/m³' }
]
const activeMetric = computed(() => metrics.find(item => item.key === metric.value) || metrics[0])

const thresholds = {
  aqi: [50, 100, 150, 200, 300],
  pm25: [35, 75, 115, 150, 250],
  pm10: [50, 150, 250, 350, 420],
  o3: [160, 200, 300, 400, 800],
  no2: [80, 200, 700, 1200, 2340],
  so2: [150, 500, 650, 800, 1600],
  co: [2000, 4000, 14000, 24000, 36000]
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
const maxIndex = computed(() => Math.max(timeline.value.length - 1, 0))
const displayedRows = computed(() => timeline.value.slice(rangeStart.value, rangeEnd.value + 1))
const visibleRangeText = computed(() => {
  const rows = displayedRows.value
  return rows.length ? `${formatTime(rows[0].time)} 至 ${formatTime(rows.at(-1).time)}` : '暂无可展示时段'
})

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

function renderChart() {
  if (!chartEl.value || !timeline.value.length) return
  if (!chart.value) chart.value = echarts.init(chartEl.value)
  const rows = displayedRows.value
  const hourLabels = rows.map(row => formatHour(row.time))
  const dates = rows.map(row => formatDate(row.time))
  const dateLabels = dates.map((date, index) => index === 0 || dates[index - 1] !== date ? date : '')
  const currentIndex = rows.findIndex(row => row.time === data.value.reference_time)
  chart.value.setOption({
    animationDuration: 180,
    grid: { left: 60, right: 28, top: 36, bottom: 102 },
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
        axisLabel: { color: '#64747d', interval: Math.max(0, Math.ceil(rows.length / 24) - 1), margin: 10 }
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
    rangeStart.value = Math.max(0, timeline.value.length - 96)
    rangeEnd.value = maxIndex.value
    loading.value = false
    await nextTick()
    await new Promise(resolve => requestAnimationFrame(resolve))
    renderChart()
  } catch (err) {
    error.value = err.message || '预报数据加载失败'
  } finally {
    loading.value = false
  }
}

watch([metric, rangeStart, rangeEnd], () => {
  if (rangeStart.value > rangeEnd.value) [rangeStart.value, rangeEnd.value] = [rangeEnd.value, rangeStart.value]
  renderChart()
})
watch(chartEl, (element) => {
  if (element && chartResizeObserver) chartResizeObserver.observe(element)
})
const onResize = () => chart.value?.resize()
onMounted(() => {
  load()
  window.addEventListener('resize', onResize)
  chartResizeObserver = new ResizeObserver(() => chart.value?.resize())
  if (chartEl.value) chartResizeObserver.observe(chartEl.value)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chartResizeObserver?.disconnect()
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
.chart-section { margin-top: 16px; padding: 18px 20px 20px; }
.forecast-chart { height: min(57vh, 560px); min-height: 360px; }
.embedded .chart-section { margin: 0; padding: 0; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.embedded .forecast-chart { height: clamp(470px, calc(100vh - 250px), 820px); min-height: 470px; flex: 1; }
.series-key { border-top: 1px solid #edf1f0; padding: 12px 2px 0; display: flex; gap: 22px; color: #596a72; font-size: 12px; }
.forecast-key, .observed-key { display: inline-block; width: 16px; height: 9px; }.forecast-key { background: #e5ae22; }.observed-key { background: #176f89; height: 3px; }
.range-control { margin-top: 16px; padding-top: 15px; border-top: 1px solid #edf1f0; }.range-labels { display: flex; justify-content: space-between; color: #52636a; font-size: 13px; }.range-labels strong { color: #234d55; font-weight: 600; }.range-sliders { position: relative; height: 28px; margin-top: 8px; }.range-sliders input { position: absolute; width: 100%; accent-color: #267a70; pointer-events: none; }.range-sliders input::-webkit-slider-thumb { pointer-events: auto; }.range-sliders input::-moz-range-thumb { pointer-events: auto; }
.status { min-height: 430px; display: grid; place-items: center; color: #64747d; }.error { color: #b4403a; }
@media (max-width: 760px) { .forecast-page { padding: 18px 14px; }.page-header { align-items: center; }.page-header h1 { font-size: 21px; }.toolbar { align-items: flex-start; flex-direction: column; gap: 12px; }.source-time { margin-left: 0; }.forecast-chart { height: 420px; min-height: 0; }.series-key { flex-wrap: wrap; gap: 12px; }.range-labels { flex-direction: column; gap: 5px; } }
</style>
