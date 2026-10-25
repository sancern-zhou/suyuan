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
import { hexWithAlpha } from './reviewTimeSeriesData.js'
echarts.use([GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkAreaComponent, LineChart, ScatterChart, CanvasRenderer])
// 风向箭头：竖直细长，尾部贴轴，箭头指向风吹去的方向（气象风向为来向）。
const WIND_ARROW_SYMBOL = 'path://M-1,12 L-1,-5 L-4,-5 L0,-12 L4,-5 L1,-5 L1,12 Z'
const props = defineProps({ entry: { type: Object, required: true }, weather: { type: Object, required: true }, markAreas: { type: Array, default: () => [] } })
const surface = ref(null); let chart; let observer
// 纵坐标名称：贴各自的轴侧、垂直居中（默认 nameLocation:'end' 会把名称顶到轴顶端，
// 与上方图例 / 上一个子图的时间轴标签重叠）。
const AXIS_NAME_STYLE = { nameLocation: 'middle', nameRotate: 90, nameGap: 52, nameTextStyle: { fontSize: 11 } }
// 轴范围：证据包窗口是自然日/推算窗，末端常落在未来（数据只到最近一个完整小时），
// 直接用窗口会把轴拖出一段没有数据的空白。这里收紧到实际观测范围——气象行 ∪ 污染物
// 曲线点的最早/最晚时刻（时间格式混有 'T' 与空格，归一为空格后按字典序比较），
// 无有效观测时回退窗口原值。
const observationRange = computed(() => {
  let start = null
  let end = null
  const consider = value => {
    const text = String(value ?? '').trim().replace('T', ' ')
    if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(text)) return
    if (start === null || text < start) start = text
    if (end === null || text > end) end = text
  }
  for (const row of (props.weather?.data || [])) consider(row?.timePoint)
  for (const item of (props.entry?.series || [])) {
    for (const point of (item?.points || [])) consider(point?.time)
  }
  return {
    start: start ?? String(props.weather?.start ?? '').replace('T', ' '),
    end: end ?? String(props.weather?.end ?? '').replace('T', ' '),
  }
})
// 逐小时槽位与轴共用收紧后的范围：气象行更晚、污染物更早等交错形态也全覆盖。
const rangedWeather = computed(() => ({ ...props.weather, start: observationRange.value.start, end: observationRange.value.end }))
const times = computed(() => hourlyWeatherPoints(rangedWeather.value, 'windSpeed').map(([time]) => time))
const valuesFor = key => hourlyWeatherPoints(rangedWeather.value, key)
const alignedPollutant = item => { const values = new Map((item.points || []).map(point => [weatherTime(point.time), point.value])); return times.value.map(time => [time, values.get(time) ?? null]) }
// 次轴：unit 与主单位不同的污染物序列（如 CO 的 mg/m³）挂到首格右侧独立轴，
// 与智能事件证据包的站点污染物+气象复合图同构；序列不带 unit 的旧调用方无次轴。
// 注意 ECharts 要求各 grid 的 yAxis 连续分组：次轴必须紧跟主污染轴（index 1），
// 后续风速/风向/温湿压的轴索引相应顺移。
const secondaryUnits = [...new Set(props.entry.series
  .map(item => (item.unit && props.entry.unit && item.unit !== props.entry.unit ? item.unit : null))
  .filter(Boolean))]
const secondaryAxisIndex = unit => 1 + secondaryUnits.indexOf(unit)
const WIND_SPEED_AXIS = 1 + secondaryUnits.length
const WIND_DIRECTION_AXIS = WIND_SPEED_AXIS + 1
const CLIMATE_AXIS = WIND_DIRECTION_AXIS + 1
const PRESSURE_AXIS = CLIMATE_AXIS + 1
const option = computed(() => {
  const windSpeed = valuesFor('windSpeed'); const windDirection = valuesFor('windDirection'); const temperature = valuesFor('temperature'); const humidity = valuesFor('humidity'); const pressure = valuesFor('pressure')
  // 污染物曲线颜色由调用方传入（与小时时序图一致：目标蓝、对照紫、剔除建议污染物补画色），
  // 未带颜色的序列（如 AI 旧 spec）回退 ECharts 默认色板；气象序列固定用默认色板。
  const series = props.entry.series.map(item => ({
    name: item.name, type: 'line', xAxisIndex: 0,
    yAxisIndex: item.unit && secondaryUnits.includes(item.unit) ? secondaryAxisIndex(item.unit) : 0,
    showSymbol: false, connectNulls: false,
    data: alignedPollutant(item),
    ...(item.color ? { lineStyle: { color: item.color }, itemStyle: { color: item.color } } : {}),
  }))
  series.push({ name: '风速 (m/s)', type: 'line', xAxisIndex: 1, yAxisIndex: WIND_SPEED_AXIS, showSymbol: false, data: windSpeed }, { name: '风向', type: 'scatter', xAxisIndex: 1, yAxisIndex: WIND_DIRECTION_AXIS, symbol: WIND_ARROW_SYMBOL, symbolSize: [8, 26], data: windDirection.flatMap(([time, value]) => (value == null || value < 0 || value > 360) ? [] : [{ value: [time, 0.5, value], symbolRotate: 180 - value }]), encode: { x: 0, y: 1, tooltip: [2] }, tooltip: { valueFormatter: direction => `${direction}°（来向）` } }, { name: '温度 (°C)', type: 'line', xAxisIndex: 2, yAxisIndex: CLIMATE_AXIS, showSymbol: false, data: temperature }, { name: '湿度 (%)', type: 'line', xAxisIndex: 2, yAxisIndex: CLIMATE_AXIS, showSymbol: false, data: humidity }, { name: '大气压 (hPa)', type: 'line', xAxisIndex: 2, yAxisIndex: PRESSURE_AXIS, showSymbol: false, data: pressure })
  if (series[0] && props.markAreas.length) series[0].markArea = {
    silent: true,
    itemStyle: { color: 'rgba(220, 110, 40, 0.16)' },
    label: { show: false },
    // 区间按所属污染物曲线色着色（与小时时序图一致），无颜色归属回退默认橙。
    data: props.markAreas.map(area => [
      { name: area.name, xAxis: weatherTime(area.start), itemStyle: { color: hexWithAlpha(area.color, 0.16) || 'rgba(220, 110, 40, 0.16)' } },
      { xAxis: weatherTime(area.end) },
    ]),
  }
  const x = { type: 'time', min: weatherTime(observationRange.value.start), max: weatherTime(observationRange.value.end), axisLabel: { hideOverlap: true } }
  return { animation: false, tooltip: { trigger: 'axis', confine: true }, legend: { type: 'scroll', top: 4, left: 0, right: 0 }, grid: [{ left: 72, right: 72, top: 50, height: '23%' }, { left: 72, right: 72, top: '37%', height: '23%' }, { left: 72, right: 72, top: '70%', height: '20%' }], xAxis: [{ ...x, gridIndex: 0 }, { ...x, gridIndex: 1 }, { ...x, gridIndex: 2 }], yAxis: [{ type: 'value', name: props.entry.unit, gridIndex: 0, position: 'left', scale: true, ...AXIS_NAME_STYLE }, ...secondaryUnits.map(unit => ({ type: 'value', name: unit, gridIndex: 0, position: 'right', scale: true, splitLine: { show: false }, ...AXIS_NAME_STYLE })), { type: 'value', name: '风速 (m/s)', gridIndex: 1, position: 'left', scale: true, ...AXIS_NAME_STYLE }, { type: 'value', gridIndex: 1, show: false, min: 0, max: 1 }, { type: 'value', name: '温度/湿度', gridIndex: 2, position: 'left', scale: true, ...AXIS_NAME_STYLE }, { type: 'value', name: '气压 (hPa)', gridIndex: 2, position: 'right', scale: true, splitLine: { show: false }, ...AXIS_NAME_STYLE }], dataZoom: [{ type: 'inside', xAxisIndex: [0, 1, 2], filterMode: 'none' }, { type: 'slider', xAxisIndex: [0, 1, 2], bottom: 4, height: 22, filterMode: 'none' }], series }
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
