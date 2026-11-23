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
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadAMap } from '@/utils/mapLoader.js'
import { LEVEL_NAMES, LEVEL_PALETTE, aqiColor, iaqiColor } from './aqiLevels.js'

const props = defineProps({
  stations: { type: Object, default: () => ({ national: [], townships: [], counties: [] }) },
  alerts: { type: Array, default: () => [] }
})

const emit = defineEmits(['tilt-change'])

const mapContainer = ref(null)
const error = ref('')
const visibleLayers = ref(['national', 'townships', 'counties'])
const layerOptions = [
  { key: 'national', label: '国控站' },
  { key: 'townships', label: '乡镇站' },
  { key: 'counties', label: '区县' }
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
const markerGroups = { national: [], townships: [], counties: [] }

const TYPE_LABELS = { national: '国控站', township: '乡镇站', county: '区县代表点' }

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
  const marker = new AMap.Marker({
    position: new AMap.LngLat(station.lon, station.lat),
    // 深色大屏样式：等级色图标（国控=圆形/乡镇=圆角方块/区县=菱形），告警站点加大加脉冲描边
    content: `
      <div class="screen-station-dot type-${esc(station.type || 'national')}${isAlerting ? ' alerting' : ''}" style="--dot-color:${esc(color)}">
        <span>${esc(text)}</span>
      </div>`,
    offset: new AMap.Pixel(isAlerting ? -16 : -12, isAlerting ? -16 : -12),
    title: label,
    zIndex: isAlerting ? 130 : 110
  })
  marker.on('click', () => {
    const conc = metricOptions
      .filter(item => item.key !== 'aqi')
      .map(item => `${item.label} ${formatMetric(station, item.key)}`)
      .join(' · ')
    const info = new AMap.InfoWindow({
      content: `
        <div class="screen-station-info">
          <strong>${esc(station.station_name)}</strong>
          <p>AQI ${formatMetric(station, 'aqi')} · ${conc}</p>
          <small>${esc(TYPE_LABELS[station.type] || '站点')}${station.quality ? ' · ' + esc(station.quality) : ''}${station.primary ? ' · 首要 ' + esc(station.primary) : ''}${station.aqi_estimated ? ' · AQI按HJ633推算' : ''} · ${esc(String(station.data_time || '').replace('T', ' ').slice(0, 16))}</small>
        </div>`,
      offset: new AMap.Pixel(0, -14)
    })
    info.open(map, marker.getPosition())
  })
  return marker
}

const clearMarkers = () => {
  Object.values(markerGroups).forEach(markers => markers.forEach(marker => marker.setMap(null)))
  markerGroups.national = []
  markerGroups.townships = []
  markerGroups.counties = []
}

const applyLayerVisibility = () => {
  const show = key => visibleLayers.value.includes(key)
  markerGroups.national.forEach(marker => marker.setMap(show('national') ? map : null))
  markerGroups.townships.forEach(marker => marker.setMap(show('townships') ? map : null))
  markerGroups.counties.forEach(marker => marker.setMap(show('counties') ? map : null))
}

const renderMarkers = () => {
  if (!map || !AMap) return
  clearMarkers()
  const alerting = alertKeys()
  ;(props.stations?.national || []).forEach(station => {
    const marker = buildMarker(station, alerting.has(String(station.station_name || '').trim()))
    markerGroups.national.push(marker)
  })
  ;(props.stations?.townships || []).forEach(station => {
    markerGroups.townships.push(buildMarker(station, false))
  })
  ;(props.stations?.counties || []).forEach(station => {
    markerGroups.counties.push(buildMarker(station, false))
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
      border-radius: 50%;
    }

    &.shape-township {
      border-radius: 2px;
    }

    &.shape-county {
      transform: rotate(45deg) scale(0.85);
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

  // 国控站：圆形（默认）

  // 乡镇站：圆角方块
  &.type-township {
    border-radius: 5px;
  }

  // 区县代表点：菱形（背景层旋转 45°，AQI 文字保持水平）
  &.type-county {
    background: transparent;
    border-color: transparent;
    box-shadow: none;

    &::before {
      content: '';
      position: absolute;
      inset: 4px;
      background: var(--dot-color);
      border: 2px solid rgba(255, 255, 255, 0.85);
      box-shadow: 0 0 10px color-mix(in srgb, var(--dot-color) 70%, transparent);
      transform: rotate(45deg);
    }

    > span {
      position: relative;
    }
  }

  &.alerting {
    width: 32px;
    height: 32px;
    animation: station-pulse 1.4s ease-in-out infinite;
  }
}

.screen-station-info {
  padding: 4px 2px;
  strong { font-size: 14px; }
  p { margin: 4px 0 2px; }
  small { color: #6f95a3; }
}

@keyframes station-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(216, 82, 69, 0.8); }
  50% { box-shadow: 0 0 0 12px rgba(216, 82, 69, 0); }
}
</style>
