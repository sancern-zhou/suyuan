<template>
  <div class="weather-comparison">
    <strong>{{ entry.title }}</strong>
    <div v-if="markAreas.length" class="weather-intervals"><span v-for="area in markAreas" :key="`${area.start}-${area.end}`">{{ area.name }}：{{ area.start }} 至 {{ area.end }}</span></div>
    <div ref="surface" class="weather-chart" role="img" :aria-label="`${entry.title}污染物、风速风向、温度湿度气压完整时序图`"></div>
  </div>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkAreaComponent } from 'echarts/components'
import { LineChart, ScatterChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { hourlyWeatherPoints, weatherTime } from './jiangsuWeatherSeries.js'
echarts.use([GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkAreaComponent, LineChart, ScatterChart, CanvasRenderer])
// 风向箭头：竖直细长，尾部贴轴，箭头指向风吹去的方向（气象风向为来向）。
const WIND_ARROW_SYMBOL = 'path://M-1,12 L-1,-5 L-4,-5 L0,-12 L4,-5 L1,-5 L1,12 Z'
const props = defineProps({ entry: { type: Object, required: true }, weather: { type: Object, required: true }, markAreas: { type: Array, default: () => [] } })
const surface = ref(null); let chart; let observer
const times = computed(() => hourlyWeatherPoints(props.weather, 'windSpeed').map(([time]) => time))
const valuesFor = key => hourlyWeatherPoints(props.weather, key)
const alignedPollutant = item => { const values = new Map((item.points || []).map(point => [weatherTime(point.time), point.value])); return times.value.map(time => [time, values.get(time) ?? null]) }
const option = computed(() => {
  const windSpeed = valuesFor('windSpeed'); const windDirection = valuesFor('windDirection'); const temperature = valuesFor('temperature'); const humidity = valuesFor('humidity'); const pressure = valuesFor('pressure')
  const series = props.entry.series.map(item => ({ name: item.name, type: 'line', xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, connectNulls: false, data: alignedPollutant(item) }))
  series.push({ name: '风速 (m/s)', type: 'line', xAxisIndex: 1, yAxisIndex: 1, showSymbol: false, data: windSpeed }, { name: '风向', type: 'scatter', xAxisIndex: 1, yAxisIndex: 2, symbol: WIND_ARROW_SYMBOL, symbolSize: [8, 26], data: windDirection.flatMap(([time, value]) => (value == null || value < 0 || value > 360) ? [] : [{ value: [time, 0.5, value], symbolRotate: 180 - value }]), encode: { x: 0, y: 1, tooltip: [2] }, tooltip: { valueFormatter: direction => `${direction}°（来向）` } }, { name: '温度 (°C)', type: 'line', xAxisIndex: 2, yAxisIndex: 3, showSymbol: false, data: temperature }, { name: '湿度 (%)', type: 'line', xAxisIndex: 2, yAxisIndex: 3, showSymbol: false, data: humidity }, { name: '大气压 (hPa)', type: 'line', xAxisIndex: 2, yAxisIndex: 4, showSymbol: false, data: pressure })
  if (series[0]) series[0].markArea = { silent: true, itemStyle: { color: 'rgba(220, 110, 40, 0.16)' }, label: { show: false }, data: props.markAreas.map(area => [{ name: area.name, xAxis: weatherTime(area.start) }, { xAxis: weatherTime(area.end) }]) }
  const x = { type: 'time', min: weatherTime(props.weather.start), max: weatherTime(props.weather.end), axisLabel: { hideOverlap: true } }
  return { animation: false, tooltip: { trigger: 'axis', confine: true }, legend: { type: 'scroll', top: 4, left: 0, right: 0 }, grid: [{ left: 58, right: 58, top: 50, height: '23%' }, { left: 58, right: 58, top: '37%', height: '23%' }, { left: 58, right: 58, top: '70%', height: '20%' }], xAxis: [{ ...x, gridIndex: 0 }, { ...x, gridIndex: 1 }, { ...x, gridIndex: 2 }], yAxis: [{ type: 'value', name: props.entry.unit, gridIndex: 0, scale: true }, { type: 'value', name: '风速 (m/s)', gridIndex: 1, scale: true }, { type: 'value', gridIndex: 1, show: false, min: 0, max: 1 }, { type: 'value', name: '温度/湿度', gridIndex: 2, scale: true }, { type: 'value', name: '气压 (hPa)', gridIndex: 2, scale: true, splitLine: { show: false } }], dataZoom: [{ type: 'inside', xAxisIndex: [0, 1, 2], filterMode: 'none' }, { type: 'slider', xAxisIndex: [0, 1, 2], bottom: 4, height: 22, filterMode: 'none' }], series }
})
watch(option, value => chart?.setOption(value, true))
onMounted(() => { chart = echarts.init(surface.value); chart.setOption(option.value); observer = new ResizeObserver(() => chart?.resize()); observer.observe(surface.value) })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>
<style scoped>
.weather-comparison { min-width: 0; border-top: 1px solid #d5d9df; padding-top: 12px; }
.weather-comparison > strong { display: block; overflow-wrap: anywhere; font-size: 12px; }
.weather-intervals { display: grid; gap: 4px; font-size: 11px; margin: 8px 0; overflow-wrap: anywhere; color: #89501e; }
.weather-chart { width: 100%; height: 560px; min-width: 0; }
</style>
