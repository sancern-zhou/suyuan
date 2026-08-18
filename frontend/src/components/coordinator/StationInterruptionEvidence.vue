<template>
  <section class="evidence-visual" aria-label="AI 关键证据可视化">
    <header>
      <div><span>AI 证据视图</span><strong>{{ activeView === 'chart' ? '五分钟数据趋势' : '站房监控画面' }}</strong></div>
      <nav aria-label="切换证据视图">
        <button :class="{ active: activeView === 'chart' }" type="button" @click="showView('chart')">数据</button>
        <button :class="{ active: activeView === 'video' }" type="button" @click="showView('video')">视频</button>
      </nav>
    </header>

    <div v-show="activeView === 'chart'" ref="chartRef" class="evidence-chart" role="img" aria-label="PM2.5、PM10 和二氧化硫五分钟数据趋势，颗粒物于九点十二分中断"></div>

    <figure v-show="activeView === 'video'" class="evidence-video">
      <img v-if="stationImageUrl" :src="stationImageUrl" alt="源创包装厂房站点监控画面" />
      <div v-else class="video-placeholder"><i></i><span>站房监控画面</span></div>
      <span class="live-state"><i></i>画面正常</span>
      <time>09:20:16</time>
    </figure>

    <footer>
      <span>{{ activeView === 'chart' ? '颗粒物同步断数，气态因子仍持续更新' : '站房在线，画面未见明显环境异常' }}</span>
      <em>场景模拟</em>
    </footer>
  </section>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, LineChart, CanvasRenderer])

defineProps({ stationImageUrl: { type: String, default: '' } })

const activeView = ref('chart')
const chartRef = ref(null)
let chart = null
let resizeObserver = null

const times = ['08:30', '08:40', '08:50', '09:00', '09:10', '09:12', '09:20', '09:30', '09:40', '09:50']
const option = {
  animationDuration: 600,
  color: ['#52e0d6', '#ffb35f', '#6fa9f6'],
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(5, 27, 39, .96)',
    borderColor: 'rgba(80, 203, 205, .24)',
    textStyle: { color: '#dff7f6', fontSize: 11 }
  },
  legend: {
    top: 8,
    left: 8,
    itemWidth: 13,
    itemHeight: 2,
    textStyle: { color: '#78959d', fontSize: 9 }
  },
  grid: { top: 58, right: 22, bottom: 38, left: 42 },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: times,
    axisLine: { lineStyle: { color: 'rgba(82, 151, 162, .18)' } },
    axisTick: { show: false },
    axisLabel: { color: '#58757d', fontSize: 9, interval: 1 }
  },
  yAxis: {
    type: 'value',
    name: '微克/立方米',
    nameTextStyle: { color: '#55757d', fontSize: 8, padding: [0, 0, 4, 4] },
    splitNumber: 4,
    axisLabel: { color: '#55757d', fontSize: 9 },
    splitLine: { lineStyle: { color: 'rgba(82, 151, 162, .1)' } }
  },
  series: [
    {
      name: 'PM2.5',
      type: 'line',
      smooth: .28,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 2.5 },
      areaStyle: { color: 'rgba(82, 224, 214, .07)' },
      data: [37, 40, 39, 44, 42, null, null, null, null, null],
      markLine: {
        symbol: 'none',
        label: { formatter: '09:12 数据中断', color: '#ff9879', fontSize: 9, position: 'insideEndTop' },
        lineStyle: { color: '#ff795f', width: 1.5, type: 'dashed' },
        data: [{ xAxis: '09:12' }]
      }
    },
    { name: 'PM10', type: 'line', smooth: .28, showSymbol: false, connectNulls: false, lineStyle: { width: 2.5 }, data: [58, 61, 59, 66, 64, null, null, null, null, null] },
    { name: 'SO₂（对照）', type: 'line', smooth: .28, showSymbol: false, lineStyle: { width: 1.5, opacity: .78 }, data: [11, 12, 11, 13, 12, 13, 12, 14, 13, 14] }
  ]
}

function showView(view) {
  activeView.value = view
  if (view === 'chart') nextTick(() => chart?.resize())
}

onMounted(() => {
  chart = echarts.init(chartRef.value)
  chart.setOption(option)
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<style scoped>
.evidence-visual { display: grid; min-height: 0; height: 100%; background: radial-gradient(circle at 50% 35%,rgba(16,94,111,.14),transparent 67%); grid-template-rows: 62px minmax(0,1fr) 46px; }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 5px 4px 12px; border-bottom: 1px solid rgba(75,164,175,.12); }
header > div { display: grid; gap: 5px; } header span { color: #50cdd0; font-size: 9px; font-weight: 800; letter-spacing: .1em; } header strong { font-size: 17px; }
nav { display: flex; gap: 3px; } nav button { padding: 5px 9px; border: 0; background: rgba(18,71,83,.16); color: #607f87; cursor: pointer; font-size: 8px; } nav button.active { background: rgba(30,133,139,.22); color: #72d9d4; }
.evidence-chart { width: 100%; height: 100%; min-height: 300px; }
.evidence-video { position: relative; min-height: 0; margin: 16px 0 8px; overflow: hidden; background: #061a26; }.evidence-video img,.video-placeholder { width: 100%; height: 100%; object-fit: cover; }.evidence-video img { opacity: .78; filter: saturate(.7) contrast(1.08); }.video-placeholder { display: grid; place-content: center; justify-items: center; gap: 10px; background: linear-gradient(rgba(23,89,101,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(23,89,101,.08) 1px,transparent 1px),#071e2b; background-size: 28px 28px; color: #66848b; font-size: 11px; }.video-placeholder i { width: 38px; height: 28px; border: 1px solid #47727a; }.live-state,time { position: absolute; top: 12px; padding: 5px 7px; background: rgba(3,22,31,.72); color: #91aaaF; font-size: 8px; }.live-state { left: 12px; display: flex; align-items: center; gap: 6px; }.live-state i { width: 6px; height: 6px; border-radius: 50%; background: #55d7a1; box-shadow: 0 0 8px rgba(85,215,161,.6); } time { right: 12px; }
footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 4px 0; border-top: 1px solid rgba(75,164,175,.1); } footer span { color: #78969d; font-size: 9px; line-height: 1.45; } footer em { flex: none; color: #d4a465; font-size: 8px; font-style: normal; }
button:focus-visible { outline: 3px solid rgba(88,241,233,.3); outline-offset: 2px; }
</style>
