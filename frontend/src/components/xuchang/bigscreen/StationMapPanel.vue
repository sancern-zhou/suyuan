<template>
  <section class="map-panel">
    <div ref="mapContainer" class="map-container" aria-label="许昌市站点空气质量地图"></div>

    <div class="map-controls">
      <div class="layer-toggle">
        <button
          v-for="layer in layerOptions"
          :key="layer.key"
          type="button"
          :class="{ on: visibleLayers.includes(layer.key) }"
          @click="toggleLayer(layer.key)"
        ><i class="shape" :class="`shape-${layer.key}`"></i>{{ layer.label }}</button>
      </div>
      <div class="map-legend">
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
      v-if="pitchAvailable"
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
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { fetchStationSeries } from '@/api/xuchang/bigScreen.js'
import { loadAMap } from '@/utils/mapLoader.js'
import { LEVEL_NAMES, LEVEL_PALETTE, aqiColor, aqiLevelName, iaqi, iaqiColor } from './aqiLevels.js'

const props = defineProps({
  stations: { type: Object, default: () => ({ national: [], townships: [], shengkong: [], office: [] }) },
  alerts: { type: Array, default: () => [] }
})

const emit = defineEmits(['tilt-change'])

const mapContainer = ref(null)
const error = ref('')
const visibleLayers = ref(['national', 'townships', 'shengkong', 'office'])
const layerOptions = [
  { key: 'national', label: '国控站' },
  { key: 'townships', label: '乡镇站' },
  { key: 'shengkong', label: '省控站' },
  { key: 'office', label: '办事处' }
]
const legendLevels = LEVEL_NAMES.map((label, index) => ({
  label: label.replace('污染', ''),
  color: LEVEL_PALETTE[index]
}))

let AMap = null
let map = null
let boundaryPolygon = null
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
const displayMetric = ref('pm25')
// AQI=100 对应的二级浓度限值；PM 为 24h、其余为 1h 评价口径。
const SECONDARY_LIMITS = { aqi: 100, pm25: 60, pm10: 120, o3: 200, so2: 500, no2: 200, co: 10 }
const metricColor = (metric, value) => metric === 'aqi' ? aqiColor(value) : iaqiColor(metric, value)
let activeInfo = null
let stationChart = null
let seriesRequestId = 0

const closeStationSeries = () => {
  seriesRequestId += 1
  stationChart?.dispose()
  stationChart = null
  activeInfo?.close()
  activeInfo = null
}

const renderStationSeries = (payload, station, metric) => {
  const element = document.getElementById('station-series-chart')
  if (!element) return
  stationChart?.dispose()
  stationChart = echarts.init(element)
  const points = payload.points || []
  const option = metricOptions.find(item => item.key === metric)
  const validPoints = points.filter(item => item.value != null)
  const latest = validPoints.at(-1)
  const latestColor = metricColor(metric, latest?.value)
  const level = metric === 'aqi' ? aqiLevelName(latest?.value) : aqiLevelName(iaqi(metric, latest?.value))
  const summary = document.getElementById('station-series-summary')
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

const openStationSeries = async (station, marker) => {
  closeStationSeries()
  const metric = displayMetric.value
  const requestId = ++seriesRequestId
  const option = metricOptions.find(item => item.key === metric)
  const granularity = station.type === 'shengkong' ? '小时' : '5分钟'
  const info = new AMap.InfoWindow({
    content: `
      <div class="screen-station-series">
        <div class="series-heading">
          <div><strong>${esc(station.station_name)}</strong><span>${esc(option?.label || metric)} 时序</span></div>
          <div id="station-series-summary" class="series-summary"></div>
        </div>
        <small>${esc(TYPE_LABELS[station.type] || '站点')} · 近6小时${granularity}数据<span>折线按IAQI等级着色</span></small>
        <div id="station-series-chart" class="station-series-chart"><span>正在加载时序数据…</span></div>
        <footer><i></i> 二级标准 ${SECONDARY_LIMITS[metric]} ${esc(option?.unit || '')}<span>${['pm25', 'pm10'].includes(metric) ? '24小时限值' : (metric === 'aqi' ? 'IAQI=100' : '1小时限值')}</span></footer>
      </div>`,
    offset: new AMap.Pixel(0, -18),
    closeWhenClickMap: true
  })
  activeInfo = info
  info.on('close', () => {
    if (activeInfo !== info) return
    seriesRequestId += 1
    stationChart?.dispose()
    stationChart = null
    activeInfo = null
  })
  info.open(map, marker.getPosition())
  await nextTick()
  try {
    const payload = await fetchStationSeries(station, metric)
    if (requestId !== seriesRequestId || activeInfo !== info) return
    if (!payload.points?.length) {
      const element = document.getElementById('station-series-chart')
      if (element) element.innerHTML = '<span>该站点当前指标暂无时序数据</span>'
      return
    }
    renderStationSeries(payload, station, metric)
  } catch (exc) {
    if (requestId !== seriesRequestId) return
    const element = document.getElementById('station-series-chart')
    if (element) element.innerHTML = `<span>${esc(exc.message || '时序数据加载失败')}</span>`
  }
}

// 视角切换：地图以 3D 模式初始化（pitch=0 视觉等同平面），
// 切换 2.5D 即设置俯仰角并按市界 bounds 自适应视野（构图更满、便于截图）；
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
      // setBounds 无 padding 参数，仅外扩 2% 余量让市界尽量铺满画面（俯仰 50° 时底部有透视延伸）
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

// marker/infoWindow 走 innerHTML 注入，字符串字段一律转义，站点名等来自数据库
const esc = value =>
  String(value ?? '').replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ))

const buildMarker = (station, isAlerting) => {
  const metric = displayMetric.value
  const text = formatMetric(station, metric)
  // AQI 直接按等级上色；污染物按 HJ633 IAQI 折点换算后上色
  const color = metric === 'aqi' ? aqiColor(station.aqi) : iaqiColor(metric, metricValue(station, metric))
  const label = `${station.station_name} ${METRIC_LABELS[metric]} ${text}`
  const largeShape = ['shengkong', 'office'].includes(station.type)
  const markerSize = isAlerting ? (largeShape ? 40 : 32) : (largeShape ? 32 : 24)
  const marker = new AMap.Marker({
    position: new AMap.LngLat(station.lon, station.lat),
    // 深色大屏样式：等级色图标（国控=三角形/乡镇=圆形/省控=菱形/办事处=六边形），
    // 告警站点加大加脉冲光晕
    content: `
      <div class="screen-station-dot type-${esc(station.type || 'national')}${isAlerting ? ' alerting' : ''}" style="--dot-color:${esc(color)}">
        <span>${esc(text)}</span>
      </div>`,
    offset: new AMap.Pixel(-markerSize / 2, -markerSize / 2),
    title: label,
    zIndex: isAlerting ? 130 : 110
  })
  marker.on('click', () => openStationSeries(station, marker))
  return marker
}

const clearMarkers = () => {
  Object.values(markerGroups).forEach(markers => markers.forEach(marker => marker.setMap(null)))
  markerGroups.national = []
  markerGroups.townships = []
  markerGroups.shengkong = []
  markerGroups.office = []
}

const applyLayerVisibility = () => {
  const show = key => visibleLayers.value.includes(key)
  markerGroups.national.forEach(marker => marker.setMap(show('national') ? map : null))
  markerGroups.townships.forEach(marker => marker.setMap(show('townships') ? map : null))
  markerGroups.shengkong.forEach(marker => marker.setMap(show('shengkong') ? map : null))
  markerGroups.office.forEach(marker => marker.setMap(show('office') ? map : null))
}

const renderMarkers = () => {
  if (!map || !AMap) return
  closeStationSeries()
  clearMarkers()
  const alerting = alertKeys()
  ;(props.stations?.national || []).forEach(station => {
    const marker = buildMarker(station, alerting.has(String(station.station_name || '').trim()))
    markerGroups.national.push(marker)
  })
  ;(props.stations?.townships || []).forEach(station => {
    markerGroups.townships.push(buildMarker(station, false))
  })
  ;(props.stations?.shengkong || []).forEach(station => {
    markerGroups.shengkong.push(buildMarker(station, false))
  })
  ;(props.stations?.office || []).forEach(station => {
    markerGroups.office.push(buildMarker(station, false))
  })
  applyLayerVisibility()
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

// 许昌市界高亮：边界 GeoJSON 本地打包（public/geo/xuchang_bound.json），
// 不依赖高德 district 在线接口（部分网络环境不可达）；失败静默降级。
const renderCityBoundary = async () => {
  try {
    const url = `${import.meta.env.BASE_URL}geo/xuchang_bound.json`
    const response = await fetch(url)
    if (!response.ok) return
    const geo = await response.json()
    if (!map) return
    const rings = []
    for (const feature of geo?.features || []) {
      const geometry = feature?.geometry
      if (geometry?.type === 'Polygon') rings.push(geometry.coordinates[0])
      else if (geometry?.type === 'MultiPolygon') {
        geometry.coordinates.forEach(polygon => rings.push(polygon[0]))
      }
    }
    if (!rings.length) return
    boundaryPolygon = new AMap.Polygon({
      path: rings.map(ring => ring.map(([lng, lat]) => [lng, lat])),
      strokeColor: '#3fc8d4',
      strokeWeight: 2.5,
      strokeOpacity: 0.95,
      fillColor: '#0b3a52',
      fillOpacity: 0.15,
      zIndex: 50
    })
    map.add(boundaryPolygon)
    // 记录市界范围，供 2.5D 视角切换时自适应视野
    const all = rings.flat()
    boundaryBounds = new AMap.Bounds(
      [Math.min(...all.map(p => p[0])), Math.min(...all.map(p => p[1]))],
      [Math.max(...all.map(p => p[0])), Math.max(...all.map(p => p[1]))]
    )
  } catch (exc) {
    console.warn('市界边界加载失败', exc)
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
    renderCityBoundary()
    renderMarkers()
  } catch (exc) {
    error.value = exc?.message || '地图加载失败'
  }
})

onBeforeUnmount(() => {
  closeStationSeries()
  clearMarkers()
  boundaryPolygon = null
  boundaryBounds = null
  map?.destroy()
  map = null
})

watch(() => [props.stations, props.alerts], renderMarkers, { deep: true })
watch(displayMetric, renderMarkers)
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
  align-items: center;
  gap: 12px;
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

// 2.5D / 平面视角切换，置于右下角（与底部控件条同高，避让页头）
.view-toggle {
  position: absolute;
  bottom: 52px;
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
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--dot-color);
  border: 2px solid rgba(255, 255, 255, 0.85);
  box-shadow: 0 0 10px color-mix(in srgb, var(--dot-color) 70%, transparent);
  color: #fff;
  font-size: 10px;
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
    width: 32px;
    height: 32px;
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
    width: 32px;
    height: 32px;
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
    width: 32px;
    height: 32px;
    animation: station-pulse 1.4s ease-in-out infinite;

    &.type-shengkong,
    &.type-office {
      width: 40px;
      height: 40px;
    }
  }
}

.screen-station-series {
  width: 410px;
  padding: 12px 12px 9px;
  border: 1px solid rgba(63, 200, 212, 0.32);
  border-radius: 8px;
  background: linear-gradient(145deg, rgba(8, 39, 55, 0.99), rgba(4, 24, 36, 0.99));
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.36), inset 0 1px rgba(255, 255, 255, 0.04);

  .series-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;

    > div:first-child {
      display: flex;
      align-items: baseline;
      gap: 8px;
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
  width: 384px;
  height: 230px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8ab6c2;
  font-size: 12px;
}

@keyframes station-pulse {
  /* 用 drop-shadow 而非 box-shadow 扩散环：透明背景 + clip-path 形状下 box-shadow 会显示成圆形 */
  0%, 100% { filter: drop-shadow(0 0 2px rgba(216, 82, 69, 0.85)); }
  50% { filter: drop-shadow(0 0 10px rgba(216, 82, 69, 0.85)); }
}
</style>
