<template>
  <section class="interference-evidence" aria-label="外部环境干扰关键证据">
    <header>
      <div><span>AI 关键证据</span><strong>{{ viewTitle }}</strong></div>
      <nav aria-label="切换外部环境干扰证据视图">
        <button :class="{ active: activeView === 'video' }" type="button" @click="showView('video')">视频识别</button>
        <button :class="{ active: activeView === 'data' }" type="button" @click="showView('data')">数据影响</button>
        <button :class="{ active: activeView === 'chain' }" type="button" @click="showView('chain')">证据链</button>
      </nav>
    </header>

    <section v-show="activeView === 'video'" class="video-view">
      <figure class="interference-video" :class="[`scenario-${activeScenario.id}`, { obscured: activeScenario.id === 'occlusion' }]">
        <img v-if="stationImageUrl" :src="stationImageUrl" alt="1006A 站点外部环境监控画面" />
        <div v-else class="video-placeholder" aria-label="站房外部监控模拟画面">
          <i class="scene-road"></i><i class="scene-building"></i><i class="scene-station"></i><i class="scene-vehicle"></i><i class="scene-person"></i><i class="scene-mist"></i>
        </div>
        <span class="live-state"><i></i>AI 视频分析中</span>
        <time>{{ activeScenario.time }}</time>
        <span class="detection-box"><strong>{{ activeScenario.title }}</strong><small>置信度 {{ activeScenario.confidence }}</small></span>
        <span v-if="activeScenario.id === 'occlusion'" class="occlusion-mask">画面可用区域 38%</span>
      </figure>

      <nav class="scenario-switch" aria-label="典型外部环境干扰场景">
        <button v-for="item in scenarios" :key="item.id" :class="{ active: activeScenario.id === item.id }" type="button" @click="selectedScenario = item.id"><span>{{ item.title }}</span><small>{{ item.status }}</small></button>
      </nav>

      <div class="filter-summary"><span><strong>23</strong> 条原始视频告警</span><i>→</i><span><strong>18</strong> 条抖动、光照与短暂停留已过滤</span><i>→</i><span><strong>5</strong> 条进入时空关联</span></div>
    </section>

    <div v-show="activeView === 'data'" ref="chartRef" class="impact-chart" role="img" aria-label="喷淋雾炮事件与本站、邻近站点颗粒物的时空关联趋势"></div>

    <section v-show="activeView === 'chain'" class="evidence-chain-view">
      <div class="chain-conclusion"><span>AI 综合判断</span><strong>疑似外部喷淋影响监测代表性</strong><em>置信度 87% · 等待人工复核</em></div>
      <ol>
        <li><i>01</i><div><strong>视频证据</strong><span>09:36—09:44，东北侧约 120 米出现持续喷淋雾炮</span></div><em>已截取</em></li>
        <li><i>02</i><div><strong>监测数据</strong><span>本站 PM10 由 64 升至 142 微克/立方米，邻近站点无同步变化</span></div><em>已关联</em></li>
        <li><i>03</i><div><strong>气象条件</strong><span>东北风 2.1 米/秒，喷淋区域位于站点上风向</span></div><em>方向吻合</em></li>
        <li><i>04</i><div><strong>设备状态</strong><span>采样、流量、温控与质控状态正常，未发现设备异常</span></div><em>已排查</em></li>
        <li><i>05</i><div><strong>运维记录</strong><span>近 7 日无校准、维修或站房作业记录与本次波动重合</span></div><em>已核对</em></li>
      </ol>
    </section>

    <footer><span>{{ footerText }}</span><em>视频、人员与事件均为场景模拟</em></footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GridComponent, LegendComponent, MarkAreaComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([GridComponent, LegendComponent, MarkAreaComponent, TooltipComponent, LineChart, CanvasRenderer])

const props = defineProps({
  stationImageUrl: { type: String, default: '' },
  revealLevel: { type: Number, default: 1 }
})

const scenarios = Object.freeze([
  { id: 'spray', title: '喷淋雾炮', confidence: '86%', status: '高相关', time: '09:38:26' },
  { id: 'vehicle', title: '车辆停靠', confidence: '91%', status: '待筛选', time: '10:12:08' },
  { id: 'person', title: '人员靠近', confidence: '88%', status: '已识别', time: '11:05:43' },
  { id: 'occlusion', title: '摄像头遮挡', confidence: '94%', status: '画面异常', time: '13:27:19' }
])

const activeView = ref('video')
const selectedScenario = ref('spray')
const chartRef = ref(null)
let chart = null
let resizeObserver = null

const activeScenario = computed(() => scenarios.find(item => item.id === selectedScenario.value) || scenarios[0])
const viewTitle = computed(() => ({ video: `${activeScenario.value.title}识别画面`, data: '监测数据与事件时间窗', chain: '多源证据包' }[activeView.value]))
const footerText = computed(() => {
  if (activeView.value === 'data') return '事件发生后本站颗粒物抬升，邻近站点未出现同步变化'
  if (activeView.value === 'chain') return '视频、数据、气象、设备与运维记录已形成完整证据链'
  return `${activeScenario.value.title} · ${activeScenario.value.status} · 可切换查看四类典型干扰`
})

const times = ['09:20', '09:25', '09:30', '09:35', '09:36', '09:40', '09:44', '09:45', '09:50', '09:55', '10:00']
const chartOption = {
  animationDuration: 600,
  color: ['#ff9b69', '#55ded3', '#75a8ee'],
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(5,27,39,.96)',
    borderColor: 'rgba(80,203,205,.24)',
    textStyle: { color: '#dff7f6', fontSize: 11 }
  },
  legend: { top: 8, left: 8, itemWidth: 13, itemHeight: 2, textStyle: { color: '#78959d', fontSize: 9 } },
  grid: { top: 58, right: 24, bottom: 38, left: 46 },
  xAxis: { type: 'category', boundaryGap: false, data: times, axisLine: { lineStyle: { color: 'rgba(82,151,162,.18)' } }, axisTick: { show: false }, axisLabel: { color: '#58757d', fontSize: 9, interval: 1 } },
  yAxis: { type: 'value', name: '微克/立方米', nameTextStyle: { color: '#55757d', fontSize: 8 }, splitNumber: 4, axisLabel: { color: '#55757d', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(82,151,162,.1)' } } },
  series: [
    {
      name: '本站 PM10',
      type: 'line',
      smooth: .25,
      showSymbol: false,
      lineStyle: { width: 2.6 },
      areaStyle: { color: 'rgba(255,155,105,.08)' },
      data: [61, 63, 62, 64, 68, 106, 142, 131, 92, 72, 65],
      markArea: { silent: true, itemStyle: { color: 'rgba(255,143,91,.09)' }, label: { color: '#e9a070', fontSize: 9, formatter: '喷淋事件 09:36—09:44' }, data: [[{ xAxis: '09:36' }, { xAxis: '09:44' }]] }
    },
    { name: '邻近站点 PM10', type: 'line', smooth: .25, showSymbol: false, lineStyle: { width: 1.8 }, data: [59, 61, 60, 62, 63, 64, 65, 64, 63, 61, 62] },
    { name: '本站 PM2.5', type: 'line', smooth: .25, showSymbol: false, lineStyle: { width: 1.5, opacity: .82 }, data: [37, 38, 37, 39, 40, 48, 57, 53, 45, 40, 38] }
  ]
}

function showView(view) {
  activeView.value = view
  if (view === 'data') nextTick(() => chart?.resize())
}

watch(() => props.revealLevel, level => {
  if (level >= 4) showView('chain')
  else if (level >= 3) showView('data')
  else showView('video')
}, { immediate: true })

onMounted(() => {
  chart = echarts.init(chartRef.value)
  chart.setOption(chartOption)
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<style scoped>
.interference-evidence { display: grid; min-width: 0; min-height: 0; height: 100%; background: radial-gradient(circle at 50% 35%,rgba(16,94,111,.14),transparent 67%); grid-template-rows: 62px minmax(0,1fr) 46px; }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 5px 4px 12px; border-bottom: 1px solid rgba(75,164,175,.12); } header > div { display: grid; gap: 5px; } header span { color: #50cdd0; font-size: 9px; font-weight: 800; letter-spacing: .1em; } header strong { font-size: 17px; }
header nav { display: flex; gap: 3px; } header nav button { padding: 5px 9px; border: 0; background: rgba(18,71,83,.16); color: #607f87; cursor: pointer; font-size: 8px; } header nav button.active { background: rgba(30,133,139,.22); color: #72d9d4; }
.video-view { display: grid; min-height: 0; gap: 8px; padding-top: 12px; grid-template-rows: minmax(0,1fr) auto auto; }.interference-video { position: relative; min-height: 0; margin: 0; overflow: hidden; background: #061a26; }.interference-video > img,.video-placeholder { width: 100%; height: 100%; object-fit: cover; }.interference-video > img { opacity: .68; filter: saturate(.65) contrast(1.1); }.video-placeholder { position: relative; overflow: hidden; background: linear-gradient(#12384a 0 54%,#162d35 54% 100%); }.scene-road { position: absolute; right: -5%; bottom: -10%; left: -5%; height: 43%; transform: skewY(-5deg); background: #253b42; }.scene-building { position: absolute; bottom: 34%; left: 12%; width: 33%; height: 29%; background: #244c58; box-shadow: inset 0 0 0 2px #376671; }.scene-station { position: absolute; bottom: 33%; left: 46%; width: 20%; height: 21%; background: #c5d0c9; box-shadow: inset 0 0 0 3px #79918e; }.scene-vehicle { position: absolute; right: 13%; bottom: 22%; width: 23%; height: 10%; border-radius: 10px 15px 3px 3px; background: #a98051; }.scene-person { position: absolute; right: 40%; bottom: 23%; width: 8px; height: 27px; border-radius: 4px 4px 2px 2px; background: #e0b077; }.scene-mist { position: absolute; right: 27%; bottom: 35%; width: 31%; height: 24%; transform: rotate(-12deg); background: radial-gradient(ellipse,rgba(224,247,240,.55),transparent 68%); filter: blur(5px); }
.live-state,time { position: absolute; z-index: 3; top: 12px; padding: 5px 7px; background: rgba(3,22,31,.76); color: #9bb5ba; font-size: 8px; }.live-state { left: 12px; display: flex; align-items: center; gap: 6px; }.live-state i { width: 6px; height: 6px; border-radius: 50%; background: #ff9b69; box-shadow: 0 0 8px rgba(255,155,105,.65); } time { right: 12px; }.detection-box { position: absolute; z-index: 3; display: grid; gap: 2px; padding: 5px 7px; border: 2px solid #ff9b69; background: rgba(40,20,15,.18); color: #fff1e9; }.detection-box strong { font-size: 10px; }.detection-box small { color: #ffc4a7; font-size: 8px; }.scenario-spray .detection-box { right: 18%; bottom: 28%; width: 38%; height: 30%; }.scenario-vehicle .detection-box { right: 9%; bottom: 15%; width: 30%; height: 22%; }.scenario-person .detection-box { right: 34%; bottom: 17%; width: 15%; height: 39%; }.scenario-occlusion .detection-box { inset: 18% 16% 15%; }.occlusion-mask { position: absolute; z-index: 2; inset: 0 0 0 38%; display: grid; place-items: center; background: rgba(2,7,10,.82); color: #e7a67d; font-size: 10px; }.scenario-switch { display: grid; gap: 8px; grid-template-columns: repeat(4,minmax(0,1fr)); }.scenario-switch button { display: grid; gap: 2px; padding: 7px 4px; border: 0; border-bottom: 1px solid rgba(76,164,176,.12); background: transparent; color: #6c898f; cursor: pointer; text-align: left; }.scenario-switch button.active { border-bottom-color: #ff9b69; color: #dbeeed; }.scenario-switch span { font-size: 9px; }.scenario-switch small { color: #826f64; font-size: 7px; }.filter-summary { display: flex; align-items: center; justify-content: space-between; gap: 7px; padding: 4px 2px 0; color: #66858b; font-size: 8px; }.filter-summary span { display: flex; align-items: baseline; gap: 3px; }.filter-summary strong { color: #e5b07c; font-size: 13px; }.filter-summary i { color: #39626a; font-style: normal; }
.impact-chart { width: 100%; height: 100%; min-height: 300px; }.evidence-chain-view { min-height: 0; padding: 18px 4px 0; }.chain-conclusion { display: grid; gap: 4px; padding: 0 0 14px; border-bottom: 1px solid rgba(75,164,175,.12); }.chain-conclusion span { color: #50cdd0; font-size: 8px; }.chain-conclusion strong { font-size: 17px; }.chain-conclusion em { color: #e1aa6c; font-size: 8px; font-style: normal; }.evidence-chain-view ol { display: grid; gap: 0; margin: 0; padding: 0; list-style: none; }.evidence-chain-view li { display: grid; align-items: center; gap: 10px; padding: 10px 2px; border-bottom: 1px solid rgba(75,164,175,.08); grid-template-columns: 24px minmax(0,1fr) auto; }.evidence-chain-view li > i { color: #4acac9; font-size: 8px; font-style: normal; }.evidence-chain-view li > div { display: grid; gap: 2px; }.evidence-chain-view li strong { font-size: 10px; }.evidence-chain-view li span { color: #6b898f; font-size: 8px; line-height: 1.4; }.evidence-chain-view li > em { color: #67c8b3; font-size: 7px; font-style: normal; }
footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 4px 0; border-top: 1px solid rgba(75,164,175,.1); } footer span { color: #78969d; font-size: 9px; line-height: 1.45; } footer em { flex: none; color: #d4a465; font-size: 8px; font-style: normal; }
button:focus-visible { outline: 3px solid rgba(88,241,233,.3); outline-offset: 2px; }
@media (max-height: 820px) { .video-view { padding-top: 7px; }.scenario-switch button { padding-block: 4px; }.filter-summary strong { font-size: 11px; }.evidence-chain-view { padding-top: 10px; }.evidence-chain-view li { padding-block: 7px; } }
</style>
