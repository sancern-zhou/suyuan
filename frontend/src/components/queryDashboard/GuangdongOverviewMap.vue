<template>
  <section class="guangdong-map" aria-label="广东省空气质量总览地图">
    <div class="map-surface">
      <div ref="mapContainer" class="amap-surface"></div>

      <div v-if="loading" class="map-state" role="status">
        <span class="state-title">地图加载中</span>
        <span class="state-detail">正在初始化高德地图</span>
      </div>

      <div v-else-if="error" class="map-state error" role="alert">
        <span class="state-title">地图不可用</span>
        <span class="state-detail">{{ error }}</span>
      </div>

      <div v-if="layers.heatmap && heatmapUnavailable" class="heatmap-note">暂无可渲染热力数据</div>
    </div>
    <div class="map-footer">
      <span>{{ overviewLabel }}</span>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { MAP_CONFIG } from '@/config/mapConfig'
import { loadAMap } from '@/utils/mapLoader'
import {
  extractCityMetricMarkers,
  extractHeatPoints,
  extractStationMarkers,
  GUANGDONG_CENTER,
  GUANGDONG_ZOOM
} from './guangdongMapData.js'

const props = defineProps({
  overview: {
    type: Object,
    default: null
  },
  focus: {
    type: Object,
    default: null
  },
  layers: {
    type: Object,
    default: () => ({})
  }
})

const mapContainer = ref(null)
const loading = ref(false)
const error = ref('')

let AMapApi = null
let map = null
let overlays = []
let heatmapLayer = null
let destroyed = false
const heatmapUnavailable = ref(false)

const overviewLabel = computed(() => {
  const updatedAt = props.overview?.updated_at || props.overview?.data_time || props.overview?.timestamp || props.overview?.generated_at
  return updatedAt ? `更新时间：${updatedAt}` : '等待地图数据'
})

const createOffset = (x, y) => {
  if (AMapApi?.Pixel) return new AMapApi.Pixel(x, y)
  return [x, y]
}

const markerValue = (value) => {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : ''
}

const markerContent = (marker) => {
  const classes = [
    'gd-overview-marker',
    marker.type === 'station' ? 'station' : 'city',
    marker.focused ? 'focused' : ''
  ].filter(Boolean).join(' ')
  const value = markerValue(marker.value)
  return `<div class="${classes}"><span>${value}</span></div>`
}

const clearOverlays = () => {
  if (map && overlays.length > 0) {
    try {
      map.remove(overlays)
    } catch {
      overlays.forEach((overlay) => {
        try {
          overlay.setMap(null)
        } catch {
          // Overlay cleanup is best-effort because AMap plugin classes vary by version.
        }
      })
    }
  }
  overlays = []
}

const clearHeatmap = () => {
  if (heatmapLayer) {
    try {
      heatmapLayer.setMap(null)
    } catch {
      // HeatMap cleanup is best-effort because plugin availability varies.
    }
  }
  heatmapLayer = null
  heatmapUnavailable.value = false
}

const createMarker = (marker) => {
  const size = marker.type === 'station' ? 22 : 30
  return new AMapApi.Marker({
    position: marker.position,
    title: marker.name,
    content: markerContent(marker),
    offset: createOffset(-Math.round(size / 2), -Math.round(size / 2)),
    zIndex: marker.focused ? 120 : marker.type === 'station' ? 90 : 80
  })
}

const renderOverlays = () => {
  if (!map || !AMapApi) return
  clearOverlays()
  clearHeatmap()

  const nextOverlays = []
  if (props.layers?.city_metrics) {
    nextOverlays.push(...extractCityMetricMarkers(props.overview, props.focus).map(createMarker))
  }
  if (props.layers?.stations) {
    nextOverlays.push(...extractStationMarkers(props.overview, props.focus).map(createMarker))
  }

  overlays = nextOverlays
  if (overlays.length > 0) {
    map.add(overlays)
  }

  if (props.layers?.heatmap) {
    renderHeatmap()
  }
}

const renderHeatmap = () => {
  const points = extractHeatPoints(props.overview)
  if (!points.length || !AMapApi?.HeatMap) {
    heatmapUnavailable.value = true
    return
  }

  const max = Math.max(...points.map(point => point.value || 0), 1)
  try {
    heatmapLayer = new AMapApi.HeatMap(map, {
      radius: 28,
      opacity: [0, 0.78],
      gradient: {
        0.2: '#2d7dd2',
        0.45: '#35b779',
        0.7: '#fde725',
        1.0: '#d7191c'
      }
    })
    heatmapLayer.setDataSet({
      data: points.map(point => ({ ...point, count: point.value || 0 })),
      max
    })
  } catch {
    heatmapUnavailable.value = true
  }
}

const addControls = () => {
  try {
    if (AMapApi.Scale) map.addControl(new AMapApi.Scale())
  } catch {
    // Controls are optional and should not block map rendering.
  }
  try {
    if (AMapApi.ToolBar) map.addControl(new AMapApi.ToolBar({ position: 'RB' }))
  } catch {
    // Controls are optional and should not block map rendering.
  }
}

const initMap = async () => {
  loading.value = true
  error.value = ''
  try {
    AMapApi = await loadAMap()
    if (destroyed || !mapContainer.value) return

    map = new AMapApi.Map(mapContainer.value, {
      ...MAP_CONFIG,
      center: GUANGDONG_CENTER,
      zoom: GUANGDONG_ZOOM,
      pitch: 0,
      viewMode: '2D'
    })
    addControls()
    renderOverlays()
  } catch (err) {
    error.value = err?.message || '高德地图加载失败。'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.overview, props.focus, props.layers],
  renderOverlays,
  { deep: true }
)

onMounted(() => {
  initMap()
})

onBeforeUnmount(() => {
  destroyed = true
  clearOverlays()
  clearHeatmap()
  if (map) {
    try {
      map.destroy()
    } catch {
      // Ignore teardown errors from third-party map internals.
    }
  }
  map = null
  AMapApi = null
})
</script>

<style scoped>
.guangdong-map {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  background: #dfe8e7;
  color: #20313a;
}

.map-surface {
  position: relative;
  flex: 1;
  min-height: 320px;
}

.amap-surface {
  position: absolute;
  inset: 0;
}

.map-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #eef3f2;
  color: #52646c;
  text-align: center;
}

.map-state.error {
  background: #f8eeee;
  color: #8a2f2f;
}

.state-title {
  font-size: 14px;
  font-weight: 700;
}

.state-detail {
  max-width: 320px;
  font-size: 12px;
  line-height: 1.5;
}

.heatmap-note {
  position: absolute;
  right: 14px;
  bottom: 14px;
  max-width: 190px;
  padding: 7px 10px;
  border: 1px solid rgba(32, 49, 58, 0.16);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.86);
  color: #52646c;
  font-size: 12px;
  line-height: 1.35;
  box-shadow: 0 8px 18px rgba(29, 72, 76, 0.1);
}

.map-footer {
  display: flex;
  gap: 14px;
  justify-content: space-between;
  padding: 10px 14px;
  border-top: 1px solid rgba(32, 49, 58, 0.12);
  background: rgba(255, 255, 255, 0.48);
  font-size: 12px;
  color: #52646c;
}

.map-footer span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.gd-overview-marker) {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #ffffff;
  border-radius: 999px;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 4px 12px rgba(32, 49, 58, 0.28);
}

:deep(.gd-overview-marker.city) {
  width: 30px;
  height: 30px;
  background: #1f7a75;
}

:deep(.gd-overview-marker.station) {
  width: 22px;
  height: 22px;
  background: #245f9d;
  font-size: 0;
}

:deep(.gd-overview-marker.focused) {
  background: #d4523f;
  box-shadow: 0 0 0 4px rgba(212, 82, 63, 0.22), 0 4px 12px rgba(32, 49, 58, 0.28);
}
</style>
