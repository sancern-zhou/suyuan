<template>
  <section class="trend-panel">
    <header class="panel-title">
      <span class="title-bar" aria-hidden="true"></span>
      <h3>许昌市 AQI 走势与预报</h3>
      <div class="legend">
        <span><i class="observed-key"></i>实况</span>
        <span><i class="forecast-key"></i>预报</span>
      </div>
    </header>
    <div ref="chartEl" class="trend-chart"></div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  trend: { type: Object, default: null },
  forecast: { type: Object, default: null }
})

const chartEl = ref(null)
let chart = null
let resizeObserver = null

const observed = computed(() => props.trend?.rows || [])
const hourlyForecast = computed(() => props.forecast?.hourly || [])

const render = () => {
  if (!chart) return
  const categories = [
    ...observed.value.map(row => row.data_time),
    ...hourlyForecast.value.map(row => row.data_time)
  ]
  chart.setOption({
    grid: { left: 44, right: 16, top: 26, bottom: 26 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(7, 41, 59, 0.95)',
      borderColor: 'rgba(63, 200, 212, 0.4)',
      textStyle: { color: '#d8ecf1', fontSize: 12 }
    },
    xAxis: {
      type: 'category',
      data: categories,
      boundaryGap: false,
      axisLine: { lineStyle: { color: 'rgba(138, 163, 174, 0.4)' } },
      axisLabel: {
        color: '#7f9caa',
        fontSize: 11,
        interval: Math.max(Math.floor(categories.length / 4) - 1, 0),
        formatter: value => {
          const match = String(value).match(/(\d{2})-(\d{2})[T\s](\d{2})/)
          return match ? `${Number(match[2])}日${match[3]}时` : value
        }
      }
    },
    yAxis: {
      type: 'value',
      name: 'AQI',
      nameTextStyle: { color: '#7f9caa' },
      splitLine: { lineStyle: { color: 'rgba(138, 163, 174, 0.15)' } },
      axisLabel: { color: '#7f9caa', fontSize: 11 }
    },
    series: [
      {
        name: '实况',
        type: 'line',
        data: observed.value.map(row => row.aqi),
        showSymbol: false,
        lineStyle: { width: 2.5, color: '#3fc8d4' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(63, 200, 212, 0.35)' },
            { offset: 1, color: 'rgba(63, 200, 212, 0)' }
          ])
        }
      },
      {
        name: '预报',
        type: 'line',
        data: hourlyForecast.value.map(row => row.aqi),
        showSymbol: false,
        lineStyle: { width: 2, color: '#e5ae22', type: 'dashed' }
      }
    ]
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

watch(() => [props.trend, props.forecast], render, { deep: true })
</script>

<style lang="scss" scoped>
.trend-panel {
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
  margin-bottom: 4px;

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
  .legend {
    display: flex;
    gap: 12px;
    margin-left: auto;
    font-size: 12px;
    color: #8ab6c2;

    span { display: inline-flex; align-items: center; gap: 5px; }
    i {
      width: 14px;
      height: 3px;
      border-radius: 2px;
    }
    .observed-key { background: #3fc8d4; }
    .forecast-key { background: #e5ae22; }
  }
}

.trend-chart {
  flex: 1;
  min-height: 0;
}
</style>
