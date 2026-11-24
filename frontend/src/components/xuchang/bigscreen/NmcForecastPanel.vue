<template>
  <section class="screen-card nmc-card">
    <header class="screen-card-title">
      <span class="title-bar"></span>
      <h3>NMC 气象预报</h3>
      <div class="title-right">
        <div class="seg-switch">
          <button
            v-for="item in metrics"
            :key="item.key"
            :class="{ active: metric === item.key }"
            @click="metric = item.key"
          >{{ item.label }}</button>
        </div>
      </div>
    </header>

    <div v-show="rows.length" ref="chartEl" class="nmc-chart"></div>
    <div v-if="!rows.length" class="empty-hint">暂无 NMC 气象预报数据</div>
    <div class="caliber-note">逐3小时 · 7天 · 发布 {{ publishLabel }}</div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  forecast: { type: Object, default: null }   // nmc_forecast
})

const metrics = [
  { key: 'temperature', label: '气温', unit: '℃', color: '#e5ae22', digits: 1 },
  { key: 'humidity', label: '湿度', unit: '%', color: '#3fc8d4', digits: 0 },
  { key: 'wind_speed', label: '风速', unit: 'm/s', color: '#7fd6a4', digits: 1 },
  { key: 'precipitation_probability', label: '降水概率', unit: '%', color: '#7aa2f7', digits: 0 }
]

const metric = ref('temperature')
const chartEl = ref(null)
let chart = null
let resizeObserver = null

const rows = computed(() => props.forecast?.rows || [])
const publishLabel = computed(() =>
  String(props.forecast?.publish_time || '').replace('T', ' ').slice(5, 16)
)
const currentMetric = computed(() => metrics.find(item => item.key === metric.value))

const render = () => {
  if (!chart) return
  const meta = currentMetric.value
  chart.setOption({
    grid: { left: 36, right: 14, top: 24, bottom: 24 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(7, 41, 59, 0.95)',
      borderColor: 'rgba(63, 200, 212, 0.4)',
      textStyle: { color: '#d8ecf1', fontSize: 12 },
      formatter: params => {
        const row = rows.value[params[0].dataIndex]
        const value = row?.[meta.key]
        return `${String(row?.time || '').replace('T', ' ').slice(5, 16)}<br/>` +
          `${meta.label} ${value ?? '—'} ${meta.unit}<br/>` +
          `${row?.weather_text || ''} ${row?.wind_direction || ''}`
      }
    },
    xAxis: {
      type: 'category',
      data: rows.value.map(row => row.time),
      axisLine: { lineStyle: { color: 'rgba(138, 163, 174, 0.4)' } },
      axisLabel: {
        color: '#7f9caa',
        fontSize: 10,
        interval: Math.max(Math.floor(rows.value.length / 6) - 1, 0),
        formatter: value => {
          const match = String(value).match(/(\d{2})-(\d{2})[T\s](\d{2})/)
          return match ? `${Number(match[2])}日${match[3]}时` : value
        }
      }
    },
    yAxis: {
      type: 'value',
      name: meta.unit,
      nameTextStyle: { color: '#7f9caa', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(138, 163, 174, 0.12)' } },
      axisLabel: { color: '#7f9caa', fontSize: 10 }
    },
    series: [{
      name: meta.label,
      type: 'line',
      data: rows.value.map(row => row[meta.key]),
      showSymbol: false,
      lineStyle: { width: 2, color: meta.color },
      itemStyle: { color: meta.color },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: meta.color + '55' },
          { offset: 1, color: meta.color + '00' }
        ])
      }
    }]
  }, { notMerge: true })
}

onMounted(() => {
  chart = echarts.init(chartEl.value)
  render()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartEl.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

watch([rows, metric], render)
</script>

<style lang="scss" scoped>
@import './panelCommon.scss';

.nmc-chart { height: 220px; }
</style>
