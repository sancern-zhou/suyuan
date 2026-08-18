<template>
  <div
    class="situation-map"
    :class="[`mode-${mode}`, { 'has-focus': Boolean(focusRegion) }]"
    aria-label="江苏省真实行政区划与运维站点分布图"
    @click="$emit('click')"
  >
    <div ref="chartRef" class="map-chart" role="img" :aria-label="mapAriaLabel"></div>

    <div v-if="focusRegion === 'nanjing'" class="focus-callout station-callout">
      <span>1002A · 江宁区</span>
      <strong>源创包装厂房</strong>
      <small>场景模拟：颗粒物数据中断</small>
    </div>
    <div v-else-if="focusRegion === 'dispatch'" class="focus-callout mobility-callout">
      <span>近 30 日智慧调度分析</span>
      <strong>4 类信号 · 6 项优化机会</strong>
      <small>调度轨迹、人员和频次均为场景模拟</small>
    </div>

    <div v-if="mapError" class="map-fallback" role="status">
      <strong>行政地图暂未加载</strong>
      <span>已读取 {{ stationCount }} 个真实站点坐标</span>
    </div>

    <div class="map-provenance">
      <span>13 市行政区划</span>
      <i></i>
      <span>{{ stationCount }} 个在用站点</span>
      <em>原江苏平台台账快照</em>
    </div>

    <div v-if="focusRegion === 'dispatch'" class="map-legend dispatch-legend" aria-label="智慧运维调度地图图例">
      <span><i class="legend-station muted"></i>真实站点</span>
      <span><i class="legend-route"></i>跨市任务</span>
      <span><i class="legend-unit"></i>单位轨迹</span>
      <span><i class="legend-person mobility"></i>人员轨迹</span>
      <span><i class="legend-frequent"></i>频繁到站</span>
    </div>
    <div v-else class="map-legend" aria-label="地图图例">
      <span><i class="legend-station"></i>在用站点</span>
      <span><i class="legend-anomaly"></i>场景异常</span>
      <span><i class="legend-person"></i>运维人员</span>
      <span><i class="legend-task"></i>待确认任务</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GeoComponent, TooltipComponent } from 'echarts/components'
import { EffectScatterChart, LinesChart, MapChart, ScatterChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import jiangsuGeoJson from './jiangsu-320000.geo.json'
import { JIANGSU_OPS_STATIONS, JIANGSU_OPS_STATION_TOTAL } from './jiangsuOpsStations.js'

echarts.use([
  CanvasRenderer,
  GeoComponent,
  TooltipComponent,
  MapChart,
  ScatterChart,
  EffectScatterChart,
  LinesChart
])

const props = defineProps({
  focusRegion: { type: String, default: '' },
  activeLayer: { type: String, default: '' },
  mode: { type: String, default: 'overview' }
})
defineEmits(['click'])

const MAP_NAME = 'jiangsu-ops-real-boundary'
const chartRef = ref(null)
const mapError = ref(false)
let chart = null
let resizeObserver = null

const stationCount = JIANGSU_OPS_STATION_TOTAL
const sceneStationCode = '1002A'
const sceneStation = JIANGSU_OPS_STATIONS.find(item => item.code === sceneStationCode)

const stationData = JIANGSU_OPS_STATIONS.map(item => ({
  name: item.name,
  value: [item.lng, item.lat, 1],
  code: item.code,
  city: item.city,
  district: item.district
}))

const mobilityCities = new Set(['南京市', '徐州市', '宿迁市', '淮安市', '盐城市', '扬州市', '镇江市', '泰州市'])
const mobilityRoutes = [
  {
    id: 'xuzhou-suqian',
    name: '徐州 ⇄ 宿迁',
    frequency: 16,
    insight: '6 次具备属地技能替代条件',
    coords: [[117.521565, 34.355594], [118.526352, 33.784713]],
    lineStyle: { color: '#ffad5c', width: 3.2, opacity: .9 }
  },
  {
    id: 'huaian-yancheng',
    name: '淮安 ⇄ 盐城',
    frequency: 11,
    insight: '相邻日期出现交叉派单',
    coords: [[118.971034, 33.352326], [120.19868, 33.516581]],
    lineStyle: { color: '#ed7c62', width: 2.8, opacity: .88 }
  },
  {
    id: 'yangzhou-taizhou',
    name: '扬州 ⇄ 泰州',
    frequency: 8,
    insight: '两地同技能人员任务负荷不均',
    coords: [[119.479719, 32.737224], [120.060841, 32.571433]],
    lineStyle: { color: '#c68eff', width: 2.5, opacity: .86 }
  },
  {
    id: 'nanjing-zhenjiang',
    name: '南京 ⇄ 镇江',
    frequency: 6,
    insight: '2 次具备属地人员替代条件',
    coords: [[118.847868, 31.927726], [119.458183, 32.014028]],
    lineStyle: { color: '#6bbfe7', width: 2.1, opacity: .78 }
  }
]
const mobilityPeople = [
  { name: '运维人员甲', routeId: 'xuzhou-suqian', route: '徐州 ⇄ 宿迁', value: [117.521565, 34.355594, 16] },
  { name: '运维人员乙', routeId: 'huaian-yancheng', route: '淮安 ⇄ 盐城', value: [118.971034, 33.352326, 11] },
  { name: '运维人员丙', routeId: 'yangzhou-taizhou', route: '扬州 ⇄ 泰州', value: [119.479719, 32.737224, 8] }
]
const serviceUnitRoutes = [
  {
    name: '苏北运维一部',
    taskCount: 23,
    insight: '徐州—宿迁服务覆盖存在交叉',
    coords: [[117.521565, 34.355594], [118.526352, 33.784713], [118.971034, 33.352326]],
    lineStyle: { color: '#53d7d2', width: 2, opacity: .76, type: 'dashed' }
  },
  {
    name: '沿江运维中心',
    taskCount: 19,
    insight: '南京—镇江—扬州可合并同路任务',
    coords: [[118.847868, 31.927726], [119.458183, 32.014028], [119.479719, 32.737224]],
    lineStyle: { color: '#57aee8', width: 2, opacity: .74, type: 'dashed' }
  }
]
const serviceUnitBases = [
  { name: '苏北运维一部', coverage: '徐州、宿迁、淮安', value: [117.521565, 34.355594, 23] },
  { name: '沿江运维中心', coverage: '南京、镇江、扬州', value: [118.847868, 31.927726, 19] }
]
const frequentStationProfiles = [
  { code: '1022A', visits: 9, issue: '同类通信问题重复到站' },
  { code: '1063A', visits: 8, issue: '耗材更换与巡检可合并' },
  { code: '1072A', visits: 7, issue: '建议转为专项治理' },
  { code: '1080A', visits: 6, issue: '相邻任务可合并到站' }
]
const frequentStations = frequentStationProfiles.map(profile => {
  const station = JIANGSU_OPS_STATIONS.find(item => item.code === profile.code)
  return station ? {
    ...profile,
    name: station.name,
    city: station.city,
    value: [station.lng, station.lat, profile.visits]
  } : null
}).filter(Boolean)

const personData = [
  { name: '南京值守人员', value: [118.93, 32.13] },
  { name: '苏州值守人员', value: [120.63, 31.29] },
  { name: '淮安值守人员', value: [119.02, 33.62] }
]
const taskData = [
  { name: '待确认任务', value: [119.42, 32.39] },
  { name: '临近时限任务', value: [120.06, 32.18] }
]

const mapAriaLabel = computed(() => {
  if (props.focusRegion === 'nanjing') return `江苏省行政地图，聚焦真实站点${sceneStation?.name || '源创包装厂房'}`
  if (props.focusRegion === 'dispatch') return '江苏省行政地图，在真实站点底图上综合展示近三十日跨市任务、运维单位轨迹、运维人员轨迹和频繁到站站点'
  return `江苏省十三个省辖市行政地图，展示原江苏运维平台 ${stationCount} 个在用站点的真实坐标分布`
})

function mapOption() {
  const dispatchFocus = props.focusRegion === 'dispatch'
  const layerVisible = layer => dispatchFocus && (!props.activeLayer || props.activeLayer === layer)
  const stationFocus = props.focusRegion === 'nanjing'
  const showOperationalOverlays = props.mode === 'province' || props.focusRegion !== ''
  return {
    animationDurationUpdate: 420,
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(3, 22, 38, .96)',
      borderColor: 'rgba(91, 224, 220, .45)',
      textStyle: { color: '#dff9f7', fontSize: 12 },
      formatter: params => {
        const row = params.data || {}
        if (params.seriesName === '在用站点') {
          return `<b>${row.name}</b><br/>${row.city || ''}${row.district || ''}<br/>站点编码 ${row.code}`
        }
        if (params.seriesName === '跨市运维轨迹') {
          return `<b>${row.name}</b><br/>近 30 日 ${row.frequency} 次跨市任务<br/>${row.insight}`
        }
        if (params.seriesName === '运维单位轨迹') {
          return `<b>${row.name}</b><br/>近 30 日关联 ${row.taskCount} 项任务<br/>${row.insight}`
        }
        if (params.seriesName === '运维单位') {
          return `<b>${row.name}</b><br/>服务范围：${row.coverage}<br/>场景模拟单位`
        }
        if (params.seriesName === '轨迹人员') {
          return `<b>${row.name}</b><br/>高频路线：${row.route}<br/>场景模拟人员`
        }
        if (params.seriesName === '频繁到站站点') {
          return `<b>${row.name}</b><br/>近 30 日到站 ${row.visits} 次<br/>${row.issue}`
        }
        return row.name || params.name || ''
      }
    },
    geo: {
      map: MAP_NAME,
      roam: false,
      silent: false,
      layoutCenter: ['50%', '51%'],
      layoutSize: '100%',
      zoom: 1,
      label: {
        show: true,
        color: '#8cbac4',
        fontSize: props.mode === 'province' ? 13 : 12,
        formatter: params => params.name
      },
      itemStyle: {
        areaColor: '#0b506e',
        borderColor: 'rgba(100, 224, 224, .72)',
        borderWidth: 1.15,
        shadowBlur: 16,
        shadowColor: 'rgba(24, 201, 211, .22)'
      },
      emphasis: {
        label: { color: '#ecfffc' },
        itemStyle: { areaColor: '#11758d', borderColor: '#78f2e5' }
      },
      regions: dispatchFocus
        ? Array.from(mobilityCities).map(name => ({
            name,
            itemStyle: { areaColor: '#174f68', borderColor: '#70cbd1', borderWidth: 1.25 }
          }))
        : []
    },
    series: [
      {
        name: '在用站点',
        type: 'scatter',
        coordinateSystem: 'geo',
        data: stationData,
        symbolSize: dispatchFocus ? 3 : 4,
        itemStyle: { color: '#50e2d4', opacity: dispatchFocus ? .22 : .72 },
        emphasis: { itemStyle: { color: '#d9fff9', opacity: 1 }, scale: 2.1 },
        z: 4
      },
      {
        name: '场景异常',
        type: 'effectScatter',
        coordinateSystem: 'geo',
        data: !dispatchFocus && sceneStation ? [{
          name: sceneStation.name,
          value: [sceneStation.lng, sceneStation.lat, 10],
          code: sceneStation.code,
          city: sceneStation.city,
          district: sceneStation.district
        }] : [],
        showEffectOn: 'render',
        rippleEffect: { scale: stationFocus ? 5 : 3.5, brushType: 'stroke' },
        symbolSize: stationFocus ? 11 : 7,
        itemStyle: { color: stationFocus ? '#ff6f61' : '#ffab55', shadowBlur: 12, shadowColor: '#ff8d55' },
        z: 9
      },
      {
        name: '跨市运维轨迹',
        type: 'lines',
        coordinateSystem: 'geo',
        data: dispatchFocus ? mobilityRoutes.map(route => ({
          ...route,
          lineStyle: {
            ...route.lineStyle,
            opacity: layerVisible('cross-city') ? route.lineStyle.opacity : .08
          }
        })) : [],
        polyline: true,
        lineStyle: { curveness: .18 },
        effect: {
          show: layerVisible('cross-city'),
          period: 4.2,
          trailLength: .25,
          symbol: 'circle',
          symbolSize: 5,
          color: '#fff4cf'
        },
        emphasis: { lineStyle: { width: 5, opacity: 1 } },
        z: 8
      },
      {
        name: '运维单位轨迹',
        type: 'lines',
        coordinateSystem: 'geo',
        data: dispatchFocus ? serviceUnitRoutes.map(route => ({
          ...route,
          lineStyle: { ...route.lineStyle, opacity: layerVisible('unit') ? route.lineStyle.opacity : .08 }
        })) : [],
        polyline: true,
        effect: {
          show: layerVisible('unit'),
          period: 6,
          trailLength: .12,
          symbol: 'arrow',
          symbolSize: 6,
          color: '#a7fff7'
        },
        z: 7
      },
      {
        name: '运维单位',
        type: 'scatter',
        coordinateSystem: 'geo',
        data: dispatchFocus ? serviceUnitBases.map(unit => ({
          ...unit,
          itemStyle: { opacity: layerVisible('unit') ? 1 : .12 }
        })) : [],
        symbol: 'triangle',
        symbolSize: 12,
        itemStyle: { color: '#72e5dc', borderColor: '#e8fffd', borderWidth: 1 },
        label: { show: layerVisible('unit'), position: 'right', formatter: '{b}', color: '#a8e8e4', fontSize: 9 },
        z: 9
      },
      {
        name: '轨迹人员',
        type: 'effectScatter',
        coordinateSystem: 'geo',
        data: dispatchFocus ? mobilityPeople.map(person => ({
          ...person,
          itemStyle: { opacity: layerVisible('person') ? 1 : .12 }
        })) : [],
        rippleEffect: { scale: 3.8, brushType: 'stroke' },
        symbol: 'diamond',
        symbolSize: 10,
        itemStyle: { color: '#fff1a8', borderColor: '#ffffff', borderWidth: 1 },
        label: {
          show: layerVisible('person'),
          position: 'right',
          formatter: params => params.data.name.replace('运维人员', ''),
          color: '#f6e6b3',
          fontSize: 9
        },
        z: 9
      },
      {
        name: '频繁到站站点',
        type: 'effectScatter',
        coordinateSystem: 'geo',
        data: dispatchFocus ? frequentStations.map(station => ({
          ...station,
          itemStyle: { opacity: layerVisible('station') ? 1 : .12 }
        })) : [],
        rippleEffect: { scale: 4.5, brushType: 'stroke' },
        symbolSize: value => Math.max(10, value[2] + 4),
        itemStyle: { color: '#ff8668', borderColor: '#ffe0cf', borderWidth: 1 },
        label: { show: layerVisible('station'), position: 'right', formatter: params => `${params.data.visits}次`, color: '#ffc0aa', fontSize: 9 },
        z: 10
      },
      {
        name: '运维人员',
        type: 'scatter',
        coordinateSystem: 'geo',
        data: showOperationalOverlays && !dispatchFocus ? personData : [],
        symbol: 'rect',
        symbolSize: 8,
        itemStyle: { color: '#5af1df', borderColor: '#d7fff9', borderWidth: 1 },
        z: 7
      },
      {
        name: '待确认任务',
        type: 'scatter',
        coordinateSystem: 'geo',
        data: showOperationalOverlays && !dispatchFocus ? taskData : [],
        symbol: 'triangle',
        symbolSize: 10,
        itemStyle: { color: '#ffd773' },
        z: 7
      }
    ]
  }
}

function renderMap() {
  if (!chartRef.value) return
  try {
    if (!echarts.getMap(MAP_NAME)) echarts.registerMap(MAP_NAME, jiangsuGeoJson)
    if (!chart) chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
    chart.setOption(mapOption(), { notMerge: true })
    nextTick(() => chart?.resize())
    mapError.value = false
  } catch (error) {
    console.error('江苏运维态势地图加载失败', error)
    mapError.value = true
  }
}

watch(() => [props.focusRegion, props.activeLayer, props.mode], renderMap)

onMounted(() => {
  renderMap()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  } else {
    window.addEventListener('resize', renderMap)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', renderMap)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.situation-map { position: relative; width: 100%; height: 100%; min-height: 0; overflow: hidden; isolation: isolate; cursor: default; }
.situation-map::before { content: ''; position: absolute; inset: 4% 9% 7%; z-index: -1; border-radius: 50%; background: radial-gradient(circle, rgba(48,225,214,.2), rgba(18,105,137,.05) 48%, transparent 71%); filter: blur(7px); }
.map-chart { position: absolute; inset: 0 0 30px; }
.map-provenance { position: absolute; left: 12px; top: 7px; display: flex; align-items: center; gap: 8px; padding: 5px 0; color: #a6d3d7; font-size: 10px; pointer-events: none; }
.map-provenance i { width: 3px; height: 3px; border-radius: 50%; background: #58ded4; }
.map-provenance em { color: #62c5c8; font-style: normal; }
.map-legend { position: absolute; right: 9px; bottom: 5px; display: flex; align-items: center; gap: 13px; color: #789eaa; font-size: 10px; pointer-events: none; }
.map-legend span { display: flex; align-items: center; gap: 5px; white-space: nowrap; }
.map-legend i { display: inline-block; width: 7px; height: 7px; }
.legend-station { border-radius: 50%; background: #50e2d4; }
.legend-station.muted { opacity: .42; }
.legend-anomaly { border-radius: 50%; background: #ff9c4d; box-shadow: 0 0 8px rgba(255,156,77,.7); }
.legend-person { border-radius: 1px; background: #55e5d4; }
.legend-person.mobility { transform: rotate(45deg); border: 1px solid #fff; background: #fff1a8; }
.legend-route { width: 18px!important; height: 3px!important; border-radius: 99px; background: linear-gradient(90deg,#ffad5c,#ed7c62,#c68eff); box-shadow: 0 0 7px rgba(255,173,92,.42); }
.legend-unit { width: 16px!important; height: 0!important; border-top: 2px dashed #53d7d2; }
.legend-frequent { border-radius: 50%; background: #ff8668; box-shadow: 0 0 7px rgba(255,134,104,.65); }
.legend-task { background: #ffd773; clip-path: polygon(50% 0, 100% 100%, 0 100%); }
.focus-callout { position: absolute; z-index: 3; display: grid; gap: 2px; min-width: 154px; padding: 9px 11px; border-left: 2px solid rgba(255,167,85,.72); background: linear-gradient(90deg,rgba(3,24,41,.9),transparent); pointer-events: none; }
.focus-callout span { color: #ffbd78; font-size: 10px; }
.focus-callout strong { color: #efffff; font-size: 13px; }
.focus-callout small { color: #90b8c1; font-size: 10px; }
.station-callout { left: 5%; bottom: 17%; }
.mobility-callout { right: 3%; top: 18%; }
.dispatch-legend { gap: 10px; }
.map-fallback { position: absolute; inset: 34% 25%; display: grid; place-content: center; gap: 5px; text-align: center; border: 1px solid rgba(255,170,91,.4); border-radius: 9px; background: rgba(4,28,45,.94); color: #f5fcfb; }
.map-fallback span { color: #9fc2c9; font-size: 11px; }
.mode-province .map-chart { bottom: 28px; }
@media (max-height: 820px) { .map-legend { gap: 9px; }.map-provenance { top: 3px; }.focus-callout { padding: 7px 9px; } }
</style>
