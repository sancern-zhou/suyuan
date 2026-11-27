<template>
  <section class="screen-card">
    <header class="screen-card-title">
      <span class="title-bar"></span>
      <h3>168 城全国排名（生态环境部发布）</h3>
      <div class="title-right">
        <div class="seg-switch">
          <button :class="{ active: scope === 'cum' }" @click="scope = 'cum'">累计</button>
          <button :class="{ active: scope === 'month' }" @click="scope = 'month'">当月</button>
        </div>
      </div>
    </header>

    <template v-if="latest">
      <div class="rank-hero">
        <div class="rank-item">
          <span>综合指数排名（倒序）</span>
          <strong>{{ latest.composite_rank ?? '—' }}</strong>
          <small>指数 {{ fmt(latest.composite_index, 2) }}</small>
        </div>
        <div class="rank-item">
          <span>PM2.5 排名（倒序）</span>
          <strong>{{ latest.pm25_rank ?? '—' }}</strong>
          <small>{{ fmt(latest.pm25, 1) }} μg/m³</small>
        </div>
      </div>
      <div v-show="latest" ref="chartEl" class="rank-trend"></div>
    </template>
    <div v-else class="empty-hint">暂无 168 城官方排名数据</div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  series: { type: Object, default: null }   // rank168_series
})

const scope = ref('cum')
const chartEl = ref(null)
let chart = null
let resizeObserver = null

const rows = computed(() => props.series?.[scope.value] || [])
const latest = computed(() => rows.value[0] || null)
const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}

const render = () => {
  if (!chart) return
  const timeline = [...rows.value].reverse()
  chart.setOption({
    grid: { left: 34, right: 34, top: 18, bottom: 20 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(7, 41, 59, 0.95)',
      borderColor: 'rgba(63, 200, 212, 0.4)',
      textStyle: { color: '#d8ecf1', fontSize: 12 }
    },
    xAxis: {
      type: 'category',
      data: timeline.map(row => row.period_label || row.data_month),
      axisLine: { lineStyle: { color: 'rgba(138, 163, 174, 0.4)' } },
      axisLabel: { color: '#7f9caa', fontSize: 10 }
    },
    yAxis: {
      type: 'value',
      inverse: true,   // 排名值小=好，置顶上优
      name: '名次',
      nameTextStyle: { color: '#7f9caa', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(138, 163, 174, 0.12)' } },
      axisLabel: { color: '#7f9caa', fontSize: 10 }
    },
    series: [
      {
        name: '综合指数排名',
        type: 'line',
        data: timeline.map(row => row.composite_rank),
        lineStyle: { color: '#3fc8d4', width: 2 },
        itemStyle: { color: '#3fc8d4' },
        symbolSize: 5
      },
      {
        name: 'PM2.5 排名',
        type: 'line',
        data: timeline.map(row => row.pm25_rank),
        lineStyle: { color: '#e5ae22', width: 2, type: 'dashed' },
        itemStyle: { color: '#e5ae22' },
        symbolSize: 5
      }
    ]
  }, { notMerge: true })
}

const mountChart = async () => {
  await nextTick()
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  render()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartEl.value)
}

onMounted(mountChart)
watch(latest, async value => {
  if (value && !chart) await mountChart()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

watch(rows, render)
</script>

<style lang="scss" scoped>
@import './panelCommon.scss';

.rank-hero {
  display: flex;
  gap: 14px;
  align-items: center;

  .rank-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 6px 12px;
    border-radius: 6px;
    background: rgba(229, 174, 34, 0.08);
    border: 1px solid rgba(229, 174, 34, 0.22);

    span { font-size: 11px; color: #e5ae22; }
    strong { font-size: 24px; color: #eaf6f8; line-height: 1.2; }
    small { font-size: 10px; color: #8ab6c2; }
  }
}

.rank-trend { height: 130px; margin-top: 8px; }
</style>
