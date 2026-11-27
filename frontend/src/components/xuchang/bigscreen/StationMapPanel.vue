<template>
  <section class="map-panel" :class="{ 'is-capture': capture }" data-testid="station-map">
    <div ref="mapContainer" class="map-container" aria-label="许昌市站点空气质量地图"></div>

    <div v-if="capture" class="capture-title">站点{{ markerGranularity === 'hour' ? '小时' : '5分钟' }}{{ metricLabel }}<span v-if="captureTimeLabel" class="capture-time">{{ captureTimeLabel }}</span></div>

    <div class="map-controls">
      <!-- PM2.5 固定小时口径，粒度切换对它不生效，选中时隐藏按钮避免无效操作 -->
      <div v-if="(townshipStations.length || townshipHourStations.length) && displayMetric !== 'pm25'" class="layer-toggle township-granularity-toggle">
        <button type="button" :class="{ on: townshipGranularity === '5min' }" @click="setTownshipGranularity('5min')">5分钟</button>
        <button type="button" :class="{ on: townshipGranularity === 'hour' }" @click="setTownshipGranularity('hour')">小时</button>
      </div>
      <div class="layer-toggle station-type-toggle">
        <button
          v-for="layer in layerOptions"
          :key="layer.key"
          type="button"
          :class="{ on: visibleLayers.includes(layer.key) }"
          @click="toggleLayer(layer.key)"
        ><i class="shape" :class="`shape-${layer.key}`"></i>{{ layer.label }}</button>
      </div>
      <div v-if="!compact" class="map-legend">
        <span v-for="level in legendLevels" :key="level.label">
          <i :style="{ background: level.color }"></i>{{ level.label }}
        </span>
      </div>
    </div>

    <div class="metric-controls">
      <div class="layer-toggle metric-toggle">
        <button
          v-for="metric in metricOptions"
          :key="metric.key"
          type="button"
          :class="{ on: displayMetric === metric.key }"
          :title="metric.unit ? `单位 ${metric.unit}` : ''"
          @click="displayMetric = metric.key"
        >{{ metric.label }}</button>
      </div>
    </div>

    <button
      v-if="pitchAvailable && !capture"
      class="view-toggle"
      :class="{ on: isTilted }"
      type="button"
      :title="isTilted ? '切换回平面视角' : '切换到 2.5D 倾斜视角（可用鼠标右键拖拽旋转）'"
      @click="toggleViewMode"
    >{{ isTilted ? '平面视角' : '2.5D 视角' }}</button>

    <div v-if="error" class="map-error">{{ error }}</div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { fetchStationSeries } from '@/api/xuchang/bigScreen.js'
import { loadAMap } from '@/utils/mapLoader.js'
import { LEVEL_NAMES, LEVEL_PALETTE, aqiColor, aqiLevelName, iaqi, iaqiColor } from './aqiLevels.js'

const props = defineProps({
  stations: { type: Object, default: () => ({ national: [], townships: [], shengkong: [], office: [] }) },
  alerts: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
  capture: { type: Boolean, default: false },
  townshipGranularity: { type: String, default: '5min' },
  metric: { type: String, default: 'pm25' },
  layers: { type: String, default: '' },
  // 逗号分隔的站点名列表：本次告警高值站，地图上加"高值"角标放大标识
  highlight: { type: String, default: '' }
})

const emit = defineEmits(['tilt-change', 'ready'])

const mapContainer = ref(null)
const error = ref('')
const layerOptions = [
  { key: 'national', label: '国控站' },
  { key: 'townships', label: '乡镇站' },
  { key: 'shengkong', label: '省控站' },
  { key: 'office', label: '办事处' }
]
const visibleLayers = ref(props.capture && props.layers
  ? props.layers.split(',').filter(key => layerOptions.some(layer => layer.key === key))
  : ['national', 'townships', 'shengkong', 'office'])
const legendLevels = LEVEL_NAMES.map((label, index) => ({
  label: label.replace('污染', ''),
  color: LEVEL_PALETTE[index]
}))

let AMap = null
let map = null
let boundaryPolygons = []
let boundaryBounds = null
const INIT_CENTER = [113.852, 34.028]
const INIT_ZOOM = 10.5
const markerGroups = { national: [], townships: [], shengkong: [], office: [] }

const TYPE_LABELS = { national: '国控站', township: '乡镇站', shengkong: '省控站', office: '办事处站' }

// 图标数值切换：AQI + 六项污染物（CO 为 mg/m³，其余 μg/m³）
const metricOptions = [
  { key: 'aqi', label: 'AQI' },
  { key: 'pm25', label: 'PM2.5', unit: 'μg/m³' },
  { key: 'pm10', label: 'PM10', unit: 'μg/m³' },
  { key: 'o3', label: 'O3', unit: 'μg/m³' },
  { key: 'so2', label: 'SO2', unit: 'μg/m³' },
  { key: 'no2', label: 'NO2', unit: 'μg/m³' },
  { key: 'co', label: 'CO', unit: 'mg/m³' }
]
const displayMetric = ref(metricOptions.some(item => item.key === props.metric) ? props.metric : 'pm25')
const townshipGranularity = ref(props.townshipGranularity === 'hour' ? 'hour' : '5min')
// PM2.5 固定小时口径：官方评价（GB3095/HJ633）只有小时/24h 值，5 分钟值是
// 仪器原始聚合、仅实时监视参考。气泡与弹窗曲线一律读小时数组，粒度切换
// 对 PM2.5 不生效（后端 station-series 同口径强制，双保险）。
const markerGranularity = computed(() => (displayMetric.value === 'pm25' ? 'hour' : townshipGranularity.value))
const townshipStations = computed(() => props.stations?.townships || [])
const townshipHourStations = computed(() => props.stations?.townships_hour || [])
const activeTownships = computed(() => markerGranularity.value === 'hour' ? townshipHourStations.value : townshipStations.value)
const metricLabel = computed(() => metricOptions.find(item => item.key === displayMetric.value)?.label || displayMetric.value)
const activeStations = computed(() => {
  const suffix = markerGranularity.value === 'hour' ? '_hour' : ''
  return {
    national: props.stations?.[`national${suffix}`] || [],
    townships: activeTownships.value,
    // 许昌市空气质量管控平台省控站只有小时数据，5 分钟模式没有对应观测值。
    shengkong: markerGranularity.value === 'hour' ? (props.stations?.shengkong_hour || []) : [],
    office: props.stations?.[`office${suffix}`] || []
  }
})
const townshipDataTime = computed(() => Object.values(activeStations.value).flat().map(item => item.data_time || item.dataTime).find(Boolean) || '')
// 截图标题附数据时刻：推送图必须能看出数值属于哪个时刻（对齐旧平台做法）
const captureTimeLabel = computed(() => {
  const match = String(townshipDataTime.value || '').match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  return match ? `${match[1]}年${Number(match[2])}月${Number(match[3])}日 ${match[4]}:${match[5]}` : ''
})
// AQI=100 对应的二级浓度限值；PM 为 24h、其余为 1h 评价口径。
const SECONDARY_LIMITS = { aqi: 100, pm25: 60, pm10: 120, o3: 200, so2: 500, no2: 200, co: 10 }
const metricColor = (metric, value) => metric === 'aqi' ? aqiColor(value) : iaqiColor(metric, value)
let activeInfo = null
let activeStationLayer = null
let stationChart = null
let seriesRequestId = 0

const closeStationSeries = () => {
  seriesRequestId += 1
  stationChart?.dispose()
  stationChart = null
  activeInfo?.close()
  activeInfo = null
  activeStationLayer = null
}

const waitForStationSeriesElement = async (requestId, info, chartId) => {
  // 高德 InfoWindow 的内容在部分 Android WebView 中异步插入 DOM。
  // 快速接口可能先于节点挂载返回，此时不能静默 return，否则永久显示加载中。
  // 关闭的弹窗内容会留在文档里，图表容器 id 必须按请求编号唯一，
  // 否则 getElementById 命中的是最早的隐藏旧节点，曲线画进了看不见的地方。
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (requestId !== seriesRequestId || activeInfo !== info) return null
    const element = document.getElementById(chartId)
    if (element) return element
    await new Promise(resolve => setTimeout(resolve, 16))
  }
  throw new Error('时序图表容器挂载超时，请关闭弹窗后重试')
}

// 弹窗内容挂在高德地图容器内，上面的触摸/点击会冒泡成地图事件（误拖地图、误触地图交互）。
// 在内容根节点按冒泡阶段拦截：事件先正常到达图表等子元素（tooltip 不受影响），
// 到根节点即停止继续向上。高德内容是异步插入的，与图表容器一样轮询等待挂载。
const isolateInfoContentEvents = async (requestId, info, chartId) => {
  const types = ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click', 'dblclick',
    'touchstart', 'touchend', 'touchmove', 'wheel']
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (requestId !== seriesRequestId || activeInfo !== info) return
    const root = document.getElementById(chartId)?.closest('.screen-station-series')
    if (root) {
      for (const type of types) root.addEventListener(type, event => event.stopPropagation())
      return
    }
    await new Promise(resolve => setTimeout(resolve, 16))
  }
}

const renderStationSeries = (payload, station, metric, element) => {
  stationChart?.dispose()
  stationChart = echarts.init(element)
  const points = payload.points || []
  const option = metricOptions.find(item => item.key === metric)
  const validPoints = points.filter(item => item.value != null)
  const latest = validPoints.at(-1)
  const latestColor = metricColor(metric, latest?.value)
  const level = metric === 'aqi' ? aqiLevelName(latest?.value) : aqiLevelName(iaqi(metric, latest?.value))
  const summary = element.closest('.screen-station-series')?.querySelector('.series-summary')
  if (summary && latest) {
    summary.innerHTML = `
      <span>最新 <b style="color:${latestColor}">${latest.value}</b><em>${esc(option?.unit || '')}</em></span>
      <i style="color:${latestColor};border-color:${latestColor}">${esc(level)}</i>`
  }
  const limit = SECONDARY_LIMITS[metric]
  stationChart.setOption({
    animationDuration: 450,
    grid: { left: 47, right: 18, top: 35, bottom: 30 },
    tooltip: {
      trigger: 'axis', backgroundColor: 'rgba(4, 24, 36, 0.97)',
      borderColor: 'rgba(63, 200, 212, 0.4)', textStyle: { color: '#d8ecf1' },
      axisPointer: { type: 'line', lineStyle: { color: 'rgba(63, 200, 212, 0.45)' } },
      formatter: params => {
        const item = params[0]
        const value = item?.value
        const color = metricColor(metric, value)
        return `${String(item?.axisValue || '').replace('T', ' ').slice(5, 16)}<br/>${item?.marker || ''}${option?.label} <b style="color:${color}">${value ?? '缺测'}</b> ${option?.unit || ''}<br/><span style="color:${color}">${metric === 'aqi' ? aqiLevelName(value) : aqiLevelName(iaqi(metric, value))}</span>`
      }
    },
    xAxis: {
      type: 'category', data: points.map(item => item.time), boundaryGap: false,
      axisLine: { lineStyle: { color: 'rgba(138, 163, 174, 0.4)' } },
      axisLabel: {
        color: '#8ab6c2', fontSize: 10, interval: Math.max(Math.floor(points.length / 4) - 1, 0),
        formatter: value => String(value).slice(11, 16)
      }
    },
    yAxis: {
      type: 'value', name: option?.unit || 'AQI', scale: true, min: 0,
      nameTextStyle: { color: '#8ab6c2', padding: [0, 0, 0, 12] }, axisLabel: { color: '#8ab6c2' },
      splitLine: { lineStyle: { color: 'rgba(138, 163, 174, 0.15)' } }
    },
    visualMap: {
      show: false, dimension: 1, seriesIndex: 0,
      pieces: LEVEL_NAMES.map((name, index) => ({
        min: index === 0 ? 0 : [50, 100, 150, 200, 300][index - 1],
        max: [50, 100, 150, 200, 300, Infinity][index],
        color: LEVEL_PALETTE[index]
      }))
    },
    series: [{
      name: option?.label, type: 'line',
      data: points.map(item => [
        item.time,
        item.value == null ? null : (metric === 'aqi' ? item.value : iaqi(metric, item.value))
      ]),
      connectNulls: false, showSymbol: points.length < 20, symbolSize: 5,
      lineStyle: { width: 2.5 },
      areaStyle: { opacity: 0.13 },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: '#e5ae22', type: 'dashed', width: 1.3 },
        label: {
          show: true, position: 'insideEndTop', color: '#f2cc65', fontSize: 10,
          formatter: `二级 ${limit} ${option?.unit || ''}`
        },
        data: [{ yAxis: limit }]
      }
    }]
  })
}

const openStationSeries = async (station, marker, layerKey) => {
  closeStationSeries()
  const metric = displayMetric.value
  const requestId = ++seriesRequestId
  activeStationLayer = layerKey
  const chartId = `station-series-chart-${requestId}`
  const option = metricOptions.find(item => item.key === metric)
  const granularityLabel = markerGranularity.value === 'hour' ? '小时' : '5分钟'

  const info = new AMap.InfoWindow({
    content: `
      <div class="screen-station-series">
        <div class="series-heading">
          <div><strong>${esc(station.station_name)}</strong><span>${esc(option?.label || metric)} 时序</span></div>
          <div class="series-summary"></div>
        </div>
        <small>${esc(TYPE_LABELS[station.type] || '站点')} · 近6小时${granularityLabel === '小时' ? '' : granularityLabel}数据<span>折线按IAQI等级着色</span></small>
        <div id="${chartId}" class="station-series-chart"><span>正在加载时序数据…</span></div>
        <footer><i></i> 二级标准 ${SECONDARY_LIMITS[metric]} ${esc(option?.unit || '')}<span>${['pm25', 'pm10'].includes(metric) ? '24小时限值' : (metric === 'aqi' ? 'IAQI=100' : '1小时限值')}</span></footer>
      </div>`,
    offset: new AMap.Pixel(0, -18),
    // 点地图不关弹窗：触屏上点站点后的合成 click、以及看弹窗时误碰地图，
    // 都会被当成"点击地图"把弹窗关掉（用户反馈"一打开就自己没了"）。
    // 关闭只走右上角 ×、点其他站点切换、离开页面。
    closeWhenClickMap: false
  })
  activeInfo = info
  info.on('close', () => {
    if (activeInfo !== info) return
    seriesRequestId += 1
    stationChart?.dispose()
    stationChart = null
    activeInfo = null
    activeStationLayer = null
  })
  info.open(map, marker.getPosition())
  isolateInfoContentEvents(requestId, info, chartId)
  await nextTick()
  try {
    const payload = await fetchStationSeries(station, metric, markerGranularity.value)
    if (requestId !== seriesRequestId || activeInfo !== info) return
    const element = await waitForStationSeriesElement(requestId, info, chartId)
    if (!element) return
    if (!payload.points?.length) {
      element.innerHTML = '<span>该站点当前指标暂无时序数据</span>'
      return
    }
    renderStationSeries(payload, station, metric, element)
  } catch (exc) {
    if (requestId !== seriesRequestId || activeInfo !== info) return
    try {
      const element = await waitForStationSeriesElement(requestId, info, chartId)
      if (element) element.innerHTML = `<span>${esc(exc.message || '时序数据加载失败')}</span>`
    } catch {
      // 弹窗已关闭时无需再更新错误信息；请求编号防止旧请求污染新弹窗。
    }
  }
}

// 视角切换：地图以 3D 模式初始化（pitch=0 视觉等同平面），
// 切换 2.5D 即设置俯仰角并按市界 bounds 自适应视野（构图更满）；
// 切回平面恢复初始视野。3D 模式下右键拖拽可旋转。
// 注意：JSAPI 2.0 在浏览器无 WebGL 时会静默降级为 2D 栅格渲染
// （无视 viewMode:'3D'），该模式下 setPitch 无效，须隐藏按钮。
const isTilted = ref(false)
const pitchAvailable = ref(true)
const toggleViewMode = () => {
  isTilted.value = !isTilted.value
  if (!map) return
  try {
    if (typeof map.setRotation === 'function') map.setRotation(0)
    if (typeof map.setPitch !== 'function') {
      console.error('[StationMapPanel] JSAPI 已降级为 2D 渲染（WebGL 不可用），setPitch 不存在')
      pitchAvailable.value = false
      isTilted.value = false
      return
    }
    map.setPitch(isTilted.value ? 50 : 0)
    emit('tilt-change', isTilted.value)
    if (isTilted.value && boundaryBounds && typeof map.setBounds === 'function') {
      // setBounds 无 padding 参数，仅外扩 2% 余量让市界尽量铺满画面。
      // 截图取景不走这里：capture 用平面视角 fitCaptureBounds，倾斜构图
      // 会纵向透视压缩、放大两侧空白（许昌市界东西扁平）。
      const sw = boundaryBounds.getSouthWest()
      const ne = boundaryBounds.getNorthEast()
      const dLng = (ne.getLng() - sw.getLng()) * 0.02
      const dLat = (ne.getLat() - sw.getLat()) * 0.02
      map.setBounds(
        new AMap.Bounds([sw.getLng() - dLng, sw.getLat() - dLat], [ne.getLng() + dLng, ne.getLat() + dLat])
      )
    } else if (!isTilted.value) {
      map.setZoomAndCenter(INIT_ZOOM, INIT_CENTER)
    }
  } catch (exc) {
    console.error('[StationMapPanel] 视角切换失败', exc)
    isTilted.value = false
  }
}

// 截图取景：平面视角按市界精确铺满。许昌市界东西扁平（Mercator 宽高比≈1.45），
// 2.5D 倾斜会纵向透视压缩、放大两侧空白，截图不再使用。
// 不用 map.setBounds：它会把 zoom 吸附到整级，取景框可能溢出画布，遮罩层边缘被裁；
// 这里按 Web Mercator 自行解算连续 zoom，以像素级留白精确包住市界：
// 顶部留白给标题、底部留白给图层控件、横向留少量卫星底图边缘。
// 画布尺寸须与 screenshot.py 的 viewport（1600×1200）保持一致。
const CAPTURE_CANVAS = { width: 1600, height: 1200 }
const CAPTURE_PAD = { top: 100, bottom: 48, x: 72 }
const fitCaptureBounds = () => {
  if (!map || !boundaryBounds) return
  const sw = boundaryBounds.getSouthWest()
  const ne = boundaryBounds.getNorthEast()
  const lngSpan = ne.getLng() - sw.getLng()
  const merc = lat => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))
  const mercSpan = merc(ne.getLat()) - merc(sw.getLat())
  const widthZoom = Math.log2(
    ((CAPTURE_CANVAS.width - CAPTURE_PAD.x * 2) * 360) / (lngSpan * 256)
  )
  const heightZoom = Math.log2(
    ((CAPTURE_CANVAS.height - CAPTURE_PAD.top - CAPTURE_PAD.bottom) * 2 * Math.PI) / (mercSpan * 256)
  )
  const center = [(sw.getLng() + ne.getLng()) / 2, (sw.getLat() + ne.getLat()) / 2]
  map.setZoomAndCenter(Math.min(widthZoom, heightZoom), center, true)
}

const METRIC_LABELS = Object.fromEntries(metricOptions.map(item => [item.key, item.label]))

const metricValue = (station, key) => {
  if (key === 'aqi') return station.aqi
  return station[key]
}

const formatMetric = (station, key) => {
  const raw = metricValue(station, key)
  if (raw === null || raw === undefined || raw === '') return '—'
  const num = Number(raw)
  if (!Number.isFinite(num)) return String(raw)
  return key === 'co' ? num.toFixed(1) : String(Math.round(num))
}

const alertKeys = () =>
  new Set(props.alerts.map(item => String(item.station_name || '').trim()))

// 高值站标识：推送截图场景经 URL highlight 参数传入本次告警站名，与
// 常规 alerts（站点偏离告警）一样在地图上放大加注，便于用户一眼定位
const highlightNames = computed(() =>
  new Set(String(props.highlight || '').split(',').map(name => name.trim()).filter(Boolean))
)

const isFlagged = (station, layerKey, alerting) => ({
  // 偏离告警（国控）：保留脉冲光晕，不叠"高值"角标
  alerting: layerKey === 'national' && alerting.has(String(station.station_name || '').trim()),
  // 乡镇高值：推送截图经 highlight 参数传入，加"高值"角标
  highlighted: highlightNames.value.has(String(station.station_name || '').trim())
})

// marker/infoWindow 走 innerHTML 注入，字符串字段一律转义，站点名等来自数据库
const esc = value =>
  String(value ?? '').replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ))

const buildMarker = (station, flagged, layerKey) => {
  const { alerting: isAlerting, highlighted } = flagged
  const metric = displayMetric.value
  const text = formatMetric(station, metric)
  // AQI 直接按等级上色；污染物按 HJ633 IAQI 折点换算后上色
  const color = metric === 'aqi' ? aqiColor(station.aqi) : iaqiColor(metric, metricValue(station, metric))
  const label = `${station.station_name} ${METRIC_LABELS[metric]} ${text}`
  const largeShape = ['shengkong', 'office'].includes(station.type)
  // 点径比常规交互略大一号：推送截图在手机上按宽度缩放显示，
  // 数值要看得清（旧平台同场景点径也更大）
  const markerSize = isAlerting || highlighted ? (largeShape ? 44 : 36) : (largeShape ? 36 : 28)
  const marker = new AMap.Marker({
    position: new AMap.LngLat(station.lon, station.lat),
    // 深色大屏样式：等级色图标（国控=三角形/乡镇=圆形/省控=菱形/办事处=六边形），
    // 告警站加脉冲光晕；乡镇高值站加红底"高值"角标
    content: `
      <div class="screen-station-dot type-${esc(station.type || 'national')}${isAlerting ? ' alerting' : ''}${highlighted ? ' highlighted' : ''}" style="--dot-color:${esc(color)}">
        <span>${esc(text)}</span>${highlighted ? '<i class="flag-badge">高值</i>' : ''}
      </div>`,
    offset: new AMap.Pixel(-markerSize / 2, -markerSize / 2),
    title: label,
    zIndex: isAlerting || highlighted ? 130 : 110
  })
  marker.on('click', () => openStationSeries(station, marker, layerKey))
  return marker
}

const clearMarkers = () => {
  Object.values(markerGroups).forEach(markers => markers.forEach(marker => marker.setMap(null)))
  markerGroups.national = []
  markerGroups.townships = []
  markerGroups.shengkong = []
  markerGroups.office = []
}

const markerSignature = (station, alerting) => JSON.stringify([
  station.station_name, station.type, station.lon, station.lat,
  displayMetric.value, metricValue(station, displayMetric.value), alerting
])

const updateMarkerGroup = (key, stations) => {
  const alerting = alertKeys()
  const signatures = stations.map(station => markerSignature(
    station, isFlagged(station, key, alerting)
  ))
  const previous = markerGroups[key]
  const unchanged = previous.length === stations.length && previous.every((entry, index) => (
    entry.signature === signatures[index]
  ))
  if (unchanged) return
  // 不重建仍有点击弹窗的图层：移动 WebView 中关闭/重建标记会让高德
  // 保留弹窗外壳却移除内容节点，造成永久加载。其他图层刷新不影响它。
  if (activeInfo && activeStationLayer === key) return
  previous.forEach(entry => entry.marker.setMap(null))
  markerGroups[key] = stations.map(station => {
    const flagged = isFlagged(station, key, alerting)
    return { marker: buildMarker(station, flagged, key), signature: markerSignature(station, flagged) }
  })
}

const applyLayerVisibility = () => {
  const show = key => visibleLayers.value.includes(key)
  markerGroups.national.forEach(({ marker }) => marker.setMap(show('national') ? map : null))
  markerGroups.townships.forEach(({ marker }) => marker.setMap(show('townships') ? map : null))
  markerGroups.shengkong.forEach(({ marker }) => marker.setMap(show('shengkong') ? map : null))
  markerGroups.office.forEach(({ marker }) => marker.setMap(show('office') ? map : null))
}

const renderMarkers = () => {
  if (!map || !AMap) return
  Object.entries(activeStations.value).forEach(([key, stations]) => updateMarkerGroup(key, stations))
  applyLayerVisibility()
  renderedGranularity = markerGranularity.value
  nextTick(notifyReady)
}

const toggleLayer = key => {
  const index = visibleLayers.value.indexOf(key)
  if (index >= 0) {
    if (visibleLayers.value.length === 1) return
    visibleLayers.value.splice(index, 1)
  } else {
    visibleLayers.value.push(key)
  }
  applyLayerVisibility()
}

const setTownshipGranularity = value => {
  closeStationSeries()
  townshipGranularity.value = value
}

let mapReady = false
let renderedGranularity = ''
// 截图模式取景完成前不发 ready：截图页以 ready 判定可以开始截图，
// 提前发出会截到初始视野而非市界取景后的画面
let captureFramed = !props.capture
const notifyReady = () => {
  if (!captureFramed) return
  if (props.capture && map && mapReady && renderedGranularity === markerGranularity.value) {
    emit('ready', {
      townshipGranularity: markerGranularity.value,
      townshipDataTime: townshipDataTime.value,
      townshipCount: activeStations.value.townships.length,
      metric: displayMetric.value,
      layers: visibleLayers.value
    })
  }
}

// 许昌市及六个标准行政区边界本地打包，截图不依赖在线行政区查询。
const geometryRings = geometry => {
  if (geometry?.type === 'Polygon') return [geometry.coordinates[0]]
  if (geometry?.type === 'MultiPolygon') return geometry.coordinates.map(polygon => polygon[0])
  return []
}

const addBoundaryRings = (rings, style) => rings.forEach(ring => {
  const polygon = new AMap.Polygon({
    path: ring.map(([lng, lat]) => new AMap.LngLat(lng, lat)),
    ...style
  })
  map.add(polygon)
  boundaryPolygons.push(polygon)
})

const renderCityBoundary = async () => {
  try {
    const baseUrl = import.meta.env.BASE_URL
    const [cityResponse, districtsResponse] = await Promise.all([
      fetch(`${baseUrl}geo/xuchang_bound.json`),
      fetch(`${baseUrl}geo/xuchang_districts.json`)
    ])
    if (!cityResponse.ok) return
    const [cityGeo, districtsGeo] = await Promise.all([
      cityResponse.json(),
      districtsResponse.ok ? districtsResponse.json() : { features: [] }
    ])
    if (!map) return
    // 淡蓝色填充保留底图辨识度；区县边界细于市界，避免喧宾夺主。
    for (const feature of districtsGeo?.features || []) {
      addBoundaryRings(geometryRings(feature.geometry), {
        strokeColor: '#a5dce4', strokeWeight: 1.4, strokeOpacity: 0.8,
        fillColor: '#75c9f2', fillOpacity: 0.22, zIndex: 51
      })
    }
    const cityRings = (cityGeo?.features || []).flatMap(feature => geometryRings(feature.geometry))
    addBoundaryRings(cityRings, {
      strokeColor: '#3fc8d4', strokeWeight: 2.5, strokeOpacity: 0.95,
      fillColor: '#75c9f2', fillOpacity: 0.22, zIndex: 52
    })
    // 记录市界范围，供 2.5D 视角切换时自适应视野
    const all = cityRings.flat()
    if (!all.length) return
    boundaryBounds = new AMap.Bounds(
      [Math.min(...all.map(p => p[0])), Math.min(...all.map(p => p[1]))],
      [Math.max(...all.map(p => p[0])), Math.max(...all.map(p => p[1]))]
    )
  } catch (exc) {
    console.warn('市界及区县边界加载失败', exc)
  }
}

onMounted(async () => {
  try {
    AMap = await loadAMap()
    map = new AMap.Map(mapContainer.value, {
      center: INIT_CENTER,
      zoom: INIT_ZOOM,
      mapStyle: 'amap://styles/dark',
      viewMode: '3D',
      pitch: 0,
      pitchEnable: true,
      rotateEnable: true,
      resizeEnable: true,
      zoomEnable: true,
      dragEnable: true
    })
    // 卫星影像 + 路网注记（JS API 2.0 类名为 TileLayer.Satellite / TileLayer.RoadNet）
    try {
      map.add(new AMap.TileLayer.Satellite({ zIndex: 5 }))
      map.add(new AMap.TileLayer.RoadNet({ zIndex: 6 }))
    } catch (exc) {
      console.warn('卫星图层加载失败，回退默认底图', exc)
    }
    map.addControl(new AMap.Scale())
    // JSAPI 在无 WebGL 环境会降级为 2D 渲染，此时不支持俯仰角，隐藏切换按钮
    pitchAvailable.value = typeof map.setPitch === 'function'
    if (!pitchAvailable.value) {
      console.warn('[StationMapPanel] 当前浏览器 WebGL 不可用，地图已降级为 2D 渲染，2.5D 视角不可用')
    }
    const boundaryLoaded = renderCityBoundary()
    mapReady = true
    renderMarkers()
    if (props.capture) {
      // 平面视角按市界取景（许昌市界东西扁平，倾斜构图站点分布不均、
      // 两侧空白多）；取景完成后才发 ready，确保 Playwright 截到的是
      // 市界铺满后的画面。市界加载失败时保持初始视野兜底。
      await boundaryLoaded
      fitCaptureBounds()
      captureFramed = true
    }
    await nextTick()
    notifyReady()
  } catch (exc) {
    error.value = exc?.message || '地图加载失败'
  }
})

onBeforeUnmount(() => {
  closeStationSeries()
  clearMarkers()
  boundaryPolygons = []
  boundaryBounds = null
  map?.destroy()
  map = null
})

watch(() => [props.stations, props.alerts], renderMarkers, { deep: true })
watch(displayMetric, renderMarkers)
watch(townshipGranularity, () => nextTick(() => { renderMarkers(); notifyReady() }))
</script>

<style lang="scss" scoped>
.map-panel {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.map-container {
  position: absolute;
  inset: 0;
}

.map-controls {
  position: absolute;
  bottom: 52px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  display: flex;
  // 各组放不下时整组折到下一行：不在行内挤压（按钮文字会折行），也不会被视口边缘裁掉
  flex-wrap: wrap;
  justify-content: center;
  // left:50% 配自适应宽度时，shrink-to-fit 的可用宽度只有半个视口，内容一多就被挤压；
  // 改为按内容宽度布局，并以视口宽减去左右留白为上限兜底
  width: max-content;
  max-width: calc(100% - 20px);
  align-items: center;
  gap: 12px;
  row-gap: 8px;
}

.layer-toggle {
  display: inline-flex;
  gap: 4px;

  button {
    padding: 3px 10px;
    border: 1px solid rgba(63, 200, 212, 0.4);
    border-radius: 4px;
    background: rgba(7, 41, 59, 0.8);
    color: #8ab6c2;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
    backdrop-filter: blur(4px);
    display: inline-flex;
    align-items: center;
    gap: 5px;

    &.on {
      background: rgba(63, 200, 212, 0.2);
      color: #3fc8d4;
      border-color: #3fc8d4;
    }
  }

  // 形状小样与地图站点图标一一对应
  .shape {
    display: inline-block;
    width: 9px;
    height: 9px;
    background: currentColor;
    flex: none;

    &.shape-national {
      clip-path: polygon(50% 0, 100% 100%, 0 100%);
    }

    &.shape-township {
      border-radius: 50%;
    }

    &.shape-shengkong {
      transform: rotate(45deg) scale(0.85);
    }

    &.shape-office {
      clip-path: polygon(25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%, 0 50%);
    }
  }
}

// 因子切换组：AQI + 六项污染物，置于页面上方居中
.metric-controls {
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  display: flex;
  align-items: center;
}

// 2.5D / 平面视角切换，置于右上角（顶部因子条下方），
// 避开底部站点/空气质量等级图例，防止窄屏下与图例重叠
.view-toggle {
  position: absolute;
  top: 52px;
  right: 16px;
  /* 需盖过 BigScreenView 的 .side-panel（z 200）/panel-handle（z 210），
     否则右侧数据面板展开时整块透明容器会拦截按钮点击 */
  z-index: 230;
  padding: 4px 12px;
  border: 1px solid rgba(63, 200, 212, 0.4);
  border-radius: 4px;
  background: rgba(7, 41, 59, 0.8);
  color: #8ab6c2;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  backdrop-filter: blur(4px);

  &.on {
    background: rgba(63, 200, 212, 0.2);
    color: #3fc8d4;
    border-color: #3fc8d4;
  }
}

.metric-toggle {
  button.on {
    background: rgba(229, 174, 34, 0.18);
    color: #e5ae22;
    border-color: #e5ae22;
  }
}

.capture-title {
  position: absolute;
  top: 62px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  color: #eaf6f8;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 2px;
  text-shadow: 0 2px 6px #04141f;
  white-space: nowrap;

  .capture-time {
    margin-left: 14px;
    font-size: 17px;
    font-weight: 500;
    letter-spacing: 1px;
    color: #cfe6ee;
  }
}

// 截图模式底部控件贴近底边（capture 无 BroadcastTicker，52px 是给它让位的），
// 给市界取景让出纵向空间
.map-panel.is-capture .map-controls {
  bottom: 14px;
}

.township-granularity-toggle {
  flex: none;
}

.map-legend {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border: 1px solid rgba(63, 200, 212, 0.25);
  border-radius: 4px;
  background: rgba(7, 41, 59, 0.8);
  font-size: 11px;
  color: #8ab6c2;
  backdrop-filter: blur(4px);

  > span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    i { width: 9px; height: 9px; border-radius: 50%; }
  }
}

.map-error {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 210;
  padding: 10px 18px;
  border-radius: 6px;
  background: rgba(7, 41, 59, 0.9);
  color: #e5ae22;
  font-size: 13px;
}
</style>

<style lang="scss">
/* 大屏站点气泡为地图 DOM 覆盖物，样式需全局生效 */
.screen-station-dot {
  --dot-color: #5b7684;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--dot-color);
  border: 2px solid rgba(255, 255, 255, 0.85);
  box-shadow: 0 0 10px color-mix(in srgb, var(--dot-color) 70%, transparent);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);

  // 国控站：三角形（背景层 clip-path，数值文字保持水平、略下移落入色块质心）
  &.type-national {
    background: transparent;
    border-color: transparent;
    box-shadow: none;

    &::before,
    &::after {
      content: '';
      position: absolute;
      clip-path: polygon(50% 0, 100% 100%, 0 100%);
    }

    // 外层白描边 + 等级色光晕
    &::after {
      inset: 0;
      z-index: 1;
      background: rgba(255, 255, 255, 0.85);
      filter: drop-shadow(0 0 6px color-mix(in srgb, var(--dot-color) 70%, transparent));
    }

    // 内层等级色（缩 2px 露出描边）
    &::before {
      inset: 2px;
      z-index: 2;
      background: var(--dot-color);
    }

    > span {
      position: relative;
      z-index: 3;
      transform: translateY(4px);
    }
  }

  // 乡镇站：圆形（默认样式即圆形，无需覆写）

  // 省控站：菱形（背景层旋转 45°，AQI 文字保持水平）
  &.type-shengkong {
    width: 36px;
    height: 36px;
    background: transparent;
    border-color: transparent;
    box-shadow: none;

    &::before {
      content: '';
      position: absolute;
      inset: 2px;
      background: var(--dot-color);
      border: 2px solid rgba(255, 255, 255, 0.85);
      box-shadow: 0 0 10px color-mix(in srgb, var(--dot-color) 70%, transparent);
      transform: rotate(45deg);
    }

    > span {
      position: relative;
    }
  }

  // 办事处站：六边形（背景层 clip-path，平顶左右尖）
  &.type-office {
    width: 36px;
    height: 36px;
    background: transparent;
    border-color: transparent;
    box-shadow: none;

    &::before,
    &::after {
      content: '';
      position: absolute;
      clip-path: polygon(25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%, 0 50%);
    }

    &::after {
      inset: 0;
      z-index: 1;
      background: rgba(255, 255, 255, 0.85);
      filter: drop-shadow(0 0 6px color-mix(in srgb, var(--dot-color) 70%, transparent));
    }

    &::before {
      inset: 2px;
      z-index: 2;
      background: var(--dot-color);
    }

    > span {
      position: relative;
      z-index: 3;
    }
  }

  &.alerting {
    width: 36px;
    height: 36px;
    animation: station-pulse 1.4s ease-in-out infinite;

    &.type-shengkong,
    &.type-office {
      width: 44px;
      height: 44px;
    }
  }

  // 乡镇高值站：放大醒目（无脉冲动画，与偏离告警的动态光晕区分）
  &.highlighted {
    width: 36px;
    height: 36px;

    &.type-shengkong,
    &.type-office {
      width: 44px;
      height: 44px;
    }
  }

  // 高值站"高值"角标：右上角红底白字，截图静态呈现（无动画依赖）
  .flag-badge {
    position: absolute;
    top: -9px;
    right: -14px;
    z-index: 4;
    padding: 1px 4px;
    border-radius: 3px;
    background: #e34d4d;
    border: 1px solid rgba(255, 255, 255, 0.9);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    line-height: 1.2;
    white-space: nowrap;
    text-shadow: none;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.45);
  }
}

.screen-station-series {
  width: min(410px, calc(100vw - 48px));
  padding: 12px 12px 9px;
  border: 1px solid rgba(63, 200, 212, 0.32);
  border-radius: 8px;
  background: linear-gradient(145deg, rgba(8, 39, 55, 0.99), rgba(4, 24, 36, 0.99));
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.36), inset 0 1px rgba(255, 255, 255, 0.04);

  .series-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    // 窄屏（App 端）适配：右侧摘要放不下时整块折到站名下一行，
    // 不再挤压站名宽度（此前站名恒被 ellipsis 截断）
    flex-wrap: wrap;
    gap: 10px;
    row-gap: 2px;

    > div:first-child {
      display: flex;
      align-items: baseline;
      // “XX 时序”标签放不下时折到站名下一行，站名独占整行完整显示；
      // 站名本身超长才走 ellipsis 兜底
      flex-wrap: wrap;
      gap: 8px;
      row-gap: 1px;
      min-width: 0;
    }

    strong {
      overflow: hidden;
      color: #eaf6f8;
      font-size: 15px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    span { color: #3fc8d4; font-size: 12px; white-space: nowrap; }
  }

  .series-summary {
    display: flex;
    align-items: center;
    gap: 7px;
    white-space: nowrap;

    > span { color: #8ab6c2; font-size: 11px; }
    b { margin-left: 3px; font-size: 22px; line-height: 1; }
    em { margin-left: 3px; color: #8ab6c2; font-size: 9px; font-style: normal; }
    i { padding: 2px 5px; border: 1px solid; border-radius: 3px; font-size: 10px; font-style: normal; }
  }

  small {
    display: flex;
    justify-content: space-between;
    margin: 8px 0 2px;
    color: #789aa9;
    font-size: 10px;

    span { color: #608392; }
  }

  footer {
    display: flex;
    align-items: center;
    gap: 5px;
    padding-top: 5px;
    border-top: 1px solid rgba(63, 200, 212, 0.12);
    color: #c5a958;
    font-size: 10px;

    i { width: 16px; border-top: 1px dashed #e5ae22; }
    span { margin-left: auto; color: #789aa9; }
  }
}

.station-series-chart {
  width: 100%;
  height: 230px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8ab6c2;
  font-size: 12px;
}

@media (max-width: 600px) {
  .metric-controls {
    top: 10px;
    width: calc(100% - 20px);
  }

  .metric-toggle {
    display: flex;
    width: 100%;
    gap: 3px;

    button {
      flex: 1;
      justify-content: center;
      min-width: 0;
      padding: 5px 2px;
      font-size: 10px;
    }
  }

  // 站点类型组独占一行、四列铺满。粒度切换同为 .layer-toggle，不能命中这条规则：
  // 否则它也按 100% 宽布局，会把站点类型组整组挤出屏幕
  .map-controls > .station-type-toggle {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    width: 100%;

    button {
      justify-content: center;
      min-width: 0;
      padding: 6px 3px;
      font-size: 11px;
    }
  }

  // 粒度切换保持内容宽度，字号与上下内边距对齐站点类型按钮
  .map-controls > .township-granularity-toggle button {
    padding: 6px 10px;
    font-size: 11px;
  }

  .view-toggle {
    right: 10px;
    top: 46px;
    padding: 5px 9px;
    font-size: 11px;
  }
}

@keyframes station-pulse {
  /* 用 drop-shadow 而非 box-shadow 扩散环：透明背景 + clip-path 形状下 box-shadow 会显示成圆形 */
  0%, 100% { filter: drop-shadow(0 0 2px rgba(216, 82, 69, 0.85)); }
  50% { filter: drop-shadow(0 0 10px rgba(216, 82, 69, 0.85)); }
}
</style>
