<template>
  <div class="weather-comparison">
    <div class="weather-toolbar">
      <strong>{{ entry.title }}</strong>
      <label>气象参数
        <select v-model="parameterKey" aria-label="气象参数">
          <option v-for="item in weatherParameters" :key="item.key" :value="item.key">{{ item.label }} ({{ item.unit }})</option>
        </select>
      </label>
    </div>
    <div v-if="markAreas.length" class="weather-intervals">
      <span v-for="area in markAreas" :key="`${area.start}-${area.end}`">{{ area.name }}：{{ area.start }} 至 {{ area.end }}</span>
    </div>
    <div ref="surface" class="weather-chart" role="img" :aria-label="`${entry.title}与${parameter.label}时序图`"></div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkAreaComponent } from 'echarts/components'
import { LineChart, BarChart, ScatterChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { hourlyWeatherPoints, weatherParameters, weatherTime } from './jiangsuWeatherSeries.js'

echarts.use([GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkAreaComponent, LineChart, BarChart, ScatterChart, CanvasRenderer])
const props = defineProps({
  entry: { type: Object, required: true },
  weather: { type: Object, required: true },
  markAreas: { type: Array, default: () => [] }
})
const parameterKey = ref('windSpeed')
const parameter = computed(() => weatherParameters.find(item => item.key === parameterKey.value))
const surface = ref(null)
let chart
let observer
const option = computed(() => {
  const metric = parameter.value
  const points = hourlyWeatherPoints(props.weather, metric.key)
  const times = points.map(([time]) => time)
  const pollutantSeries = props.entry.series.map(item => {
    const values = new Map(item.points.map(point => [weatherTime(point.time), point.value]))
    return {
      name: item.name, type: 'line', yAxisIndex: 0, connectNulls: false,
      smooth: false, showSymbol: times.length <= 48,
      data: times.map(time => [time, values.get(time) ?? null])
    }
  })
  const series = [...pollutantSeries, {
    name: `${metric.label} (${metric.unit})`,
    type: metric.key === 'rain' ? 'bar' : metric.key === 'windDirection' ? 'scatter' : 'line',
    yAxisIndex: 1, connectNulls: false, smooth: false, showSymbol: times.length <= 48,
    data: points
  }]
  series[0].markArea = {
    silent: true, itemStyle: { color: 'rgba(220, 110, 40, 0.16)' },
    label: { show: false },
    data: props.markAreas.map(area => [{ name: area.name, xAxis: weatherTime(area.start) }, { xAxis: weatherTime(area.end) }])
  }
  return {
    animation: false, color: ['#2384c6', '#41976c', '#c67523'],
    tooltip: { trigger: 'axis', confine: true },
    legend: { type: 'scroll', top: 4, left: 0, right: 0 },
    grid: { left: 12, right: 12, top: 62, bottom: 60, containLabel: true },
    xAxis: { type: 'time', min: weatherTime(props.weather.start), max: weatherTime(props.weather.end) },
    yAxis: [
      { type: 'value', name: props.entry.unit, scale: true },
      { type: 'value', name: `${metric.label} (${metric.unit})`, scale: true, splitLine: { show: false },
        ...(metric.key === 'windDirection' ? { min: 0, max: 360 } : {}),
        ...(metric.key === 'humidity' ? { min: 0, max: 100 } : {}) }
    ],
    dataZoom: [{ type: 'inside', filterMode: 'none' }, { type: 'slider', bottom: 4, height: 22, filterMode: 'none' }],
    series
  }
})
watch(option, value => chart?.setOption(value, true))
onMounted(() => {
  chart = echarts.init(surface.value)
  chart.setOption(option.value)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(surface.value)
})
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>

<style scoped>
.weather-comparison { min-width: 0; border-top: 1px solid #d5d9df; padding-top: 12px; }
.weather-toolbar { display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; align-items: center; font-size: 12px; }
.weather-toolbar strong { overflow-wrap: anywhere; }
.weather-toolbar label { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.weather-toolbar select { max-width: 100%; padding: 5px; border: 1px solid #aeb6bf; border-radius: 4px; background: white; color: #222; }
.weather-intervals { display: grid; gap: 4px; font-size: 11px; margin: 8px 0; overflow-wrap: anywhere; color: #89501e; }
.weather-chart { width: 100%; height: 320px; min-width: 0; }
</style>
