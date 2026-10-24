<template>
  <section class="map-panel">
    <header class="panel-title">
      <span class="title-bar" aria-hidden="true"></span>
      <h3>站点实时态势</h3>
      <div class="map-legend">
        <span v-for="level in legendLevels" :key="level.label">
          <i :style="{ background: level.color }"></i>{{ level.label }}
        </span>
        <span class="layer-toggle">
          <button
            v-for="layer in layerOptions"
            :key="layer.key"
            type="button"
            :class="{ on: visibleLayers.includes(layer.key) }"
            @click="toggleLayer(layer.key)"
          >{{ layer.label }}</button>
        </span>
      </div>
    </header>
    <div ref="mapContainer" class="map-container" aria-label="许昌市站点空气质量地图"></div>
    <div v-if="error" class="map-error">{{ error }}</div>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadAMap } from '@/utils/mapLoader.js'
import { LEVEL_NAMES, LEVEL_PALETTE, aqiColor } from './aqiLevels.js'

const props = defineProps({
  stations: { type: Object, default: () => ({ national: [], townships: [], counties: [] }) },
  alerts: { type: Array, default: () => [] }
})

const mapContainer = ref(null)
const error = ref('')
const visibleLayers = ref(['national', 'townships', 'counties'])
const layerOptions = [
  { key: 'national', label: '国控站' },
  { key: 'townships', label: '乡镇站' },
  { key: 'counties', label: '区县' }
]
const legendLevels = LEVEL_NAMES.slice(0, 4).map((label, index) => ({
  label: label.replace('污染', ''),
  color: LEVEL_PALETTE[index]
}))

let AMap = null
let map = null
const markerGroups = { national: [], townships: [], counties: [] }

const TYPE_LABELS = { national: '国控站', township: '乡镇站', county: '区县代表点' }

const alertKeys = () =>
  new Set(props.alerts.map(item => String(item.station_name || '').trim()))

const buildMarker = (station, isAlerting) => {
  const color = aqiColor(station.aqi)
  const label = `${station.station_name} AQI ${station.aqi ?? '—'}`
  const marker = new AMap.Marker({
    position: new AMap.LngLat(station.lon, station.lat),
    // 深色大屏样式：等级色圆点，告警站点加大加脉冲描边
    content: `
      <div class="screen-station-dot${isAlerting ? ' alerting' : ''}" style="--dot-color:${color}">
        <span>${station.aqi ?? '—'}</span>
      </div>`,
    offset: new AMap.Pixel(-17, -17),
    title: label,
    zIndex: isAlerting ? 130 : 110
  })
  marker.on('click', () => {
    const info = new AMap.InfoWindow({
      content: `
        <div class="screen-station-info">
          <strong>${station.station_name}</strong>
          <p>AQI ${station.aqi ?? '—'} · PM2.5 ${station.pm25 ?? '—'}</p>
          <small>${TYPE_LABELS[station.type] || '站点'}${station.quality ? ' · ' + station.quality : ''}${station.primary ? ' · 首要 ' + station.primary : ''} · ${String(station.data_time || '').replace('T', ' ').slice(0, 16)}</small>
        </div>`,
      offset: new AMap.Pixel(0, -18)
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

onMounted(async () => {
  try {
    AMap = await loadAMap()
    map = new AMap.Map(mapContainer.value, {
      center: [113.852, 34.036],
      zoom: 9.2,
      mapStyle: 'amap://styles/dark',
      viewMode: '2D',
      resizeEnable: true,
      zoomEnable: true,
      dragEnable: true
    })
    map.addControl(new AMap.Scale())
    renderMarkers()
  } catch (exc) {
    error.value = exc?.message || '地图加载失败'
  }
})

onBeforeUnmount(() => {
  clearMarkers()
  map?.destroy()
  map = null
})

watch(() => [props.stations, props.alerts], renderMarkers, { deep: true })
</script>

<style lang="scss" scoped>
.map-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 12px 14px;
  border: 1px solid rgba(63, 200, 212, 0.18);
  border-radius: 8px;
  background: rgba(7, 41, 59, 0.55);
  overflow: hidden;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;

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
}

.map-legend {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
  font-size: 11px;
  color: #8ab6c2;

  > span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    i { width: 9px; height: 9px; border-radius: 50%; }
  }

  .layer-toggle {
    display: inline-flex;
    gap: 4px;

    button {
      padding: 2px 8px;
      border: 1px solid rgba(63, 200, 212, 0.3);
      border-radius: 4px;
      background: transparent;
      color: #6f95a3;
      font-size: 11px;
      cursor: pointer;
      transition: all 0.2s;

      &.on {
        background: rgba(63, 200, 212, 0.15);
        color: #3fc8d4;
      }
    }
  }
}

.map-container {
  flex: 1;
  min-height: 0;
  border-radius: 6px;
}

.map-error {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
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
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--dot-color);
  border: 2px solid rgba(255, 255, 255, 0.85);
  box-shadow: 0 0 10px color-mix(in srgb, var(--dot-color) 70%, transparent);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);

  &.alerting {
    width: 42px;
    height: 42px;
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
