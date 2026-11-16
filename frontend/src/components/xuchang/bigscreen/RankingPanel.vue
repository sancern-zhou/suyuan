<template>
  <section class="ranking-panel">
    <header class="panel-title">
      <span class="title-bar" aria-hidden="true"></span>
      <h3>{{ title }}</h3>
      <small v-if="dataTime">{{ formatHour(dataTime) }}</small>
    </header>
    <div ref="chartEl" class="ranking-chart"></div>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { aqiColor, formatHour } from './aqiLevels.js'

const props = defineProps({
  title: { type: String, required: true },
  rows: { type: Array, default: () => [] },
  nameKey: { type: String, default: 'city' },
  dataTime: { type: String, default: '' },
  highlight: { type: String, default: '许昌市' }
})

const chartEl = ref(null)
let chart = null
let resizeObserver = null

const render = () => {
  if (!chart) return
  const rows = [...props.rows]
  // 排名升序：柱形图自下而上展示（最优在顶部）
  rows.reverse()
  chart.setOption({
    grid: { left: 76, right: 48, top: 8, bottom: 8 },
    xAxis: { type: 'value', show: false },
    yAxis: {
      type: 'category',
      data: rows.map(row => row[props.nameKey]),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: value => (value === props.highlight ? '#3fc8d4' : '#a8c8d2'),
        fontSize: 12
      }
    },
    series: [{
      type: 'bar',
      data: rows.map(row => ({
        value: row.aqi,
        itemStyle: {
          color: aqiColor(row.aqi),
          opacity: row[props.nameKey] === props.highlight ? 1 : 0.75,
          borderRadius: [0, 3, 3, 0]
        }
      })),
      barWidth: '55%',
      label: {
        show: true,
        position: 'right',
        color: '#d8ecf1',
        fontSize: 12,
        formatter: param => `#${rows[param.dataIndex].rank ?? '—'} ${param.value ?? '—'}`
      }
    }],
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(7, 41, 59, 0.95)',
      borderColor: 'rgba(63, 200, 212, 0.4)',
      textStyle: { color: '#d8ecf1', fontSize: 12 },
      formatter: param => {
        const row = rows[param[0].dataIndex]
        return `${row[props.nameKey]}<br/>AQI ${row.aqi ?? '—'} · PM2.5 ${row.pm25 ?? '—'}<br/>${row.quality || ''} ${row.primary ? '· 首要 ' + row.primary : ''}`
      }
    }
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

watch(() => props.rows, render, { deep: true })
</script>

<style lang="scss" scoped>
.ranking-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 12px 14px;
  border: 1px solid rgba(63, 200, 212, 0.18);
  border-radius: 8px;
  background: rgba(7, 41, 59, 0.55);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;

  .title-bar {
    width: 4px;
    height: 14px;
    border-radius: 2px;
    background: #3fc8d4;
  }
  h3 {
    margin: 0;
    font-size: 15px;
    color: #eaf6f8;
    letter-spacing: 1px;
  }
  small { color: #6f95a3; font-size: 12px; }
}

.ranking-chart {
  flex: 1;
  min-height: 0;
}
</style>
