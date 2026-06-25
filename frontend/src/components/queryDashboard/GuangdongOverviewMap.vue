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
import guangdongBoundary from './guangdong-boundary.json'
import { createMapEvent, summarizeMapView } from './mapEventBridge.js'
import { loadProgramLayerFeatureEntries } from './mapProgramData.js'
import {
  createMapProgramExecutionReceipt,
  summarizeProgramLayerRenderResults
} from './mapProgramReceipt.js'
import { pointIconClassName, resolvePointIconPreset } from './mapProgramPointIcons.js'
import {
  extractCityMetricMarkers,
  extractHeatPoints,
  extractStationMarkers,
  GUANGDONG_CENTER,
  GUANGDONG_ZOOM
} from './guangdongMapData.js'

const GUANGDONG_FOCUS_ZOOM = 7.2
const GUANGDONG_MASK_OUTER_PATH = [
  [72, 3],
  [136, 3],
  [136, 55],
  [72, 55]
]

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
  },
  sessionId: {
    type: String,
    default: ''
  },
  mapProgram: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['map-event'])

const mapContainer = ref(null)
const loading = ref(false)
const error = ref('')

let AMapApi = null
let map = null
let overlays = []
let provinceOverlays = []
let heatmapLayer = null
let destroyed = false
let overlayRenderToken = 0
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
  const iconClass = marker.icon ? `icon-${pointIconClassName(marker.icon)}` : ''
  const classes = [
    'gd-overview-marker',
    marker.type === 'station' ? 'station' : 'city',
    iconClass,
    marker.focused ? 'focused' : ''
  ].filter(Boolean).join(' ')
  const value = markerValue(marker.value)
  return `<div class="${classes}"><span>${value}</span></div>`
}

const collectActiveLayerIds = () => {
  const dashboardLayers = Object.entries(props.layers || {})
    .filter(([, visible]) => visible)
    .map(([layerId]) => layerId)

  const programLayers = Array.isArray(props.mapProgram?.state?.layers)
    ? props.mapProgram.state.layers
      .filter(layer => layer?.lifecycle?.visible !== false)
      .map(layer => layer.id)
      .filter(Boolean)
    : []

  return [...new Set([...dashboardLayers, ...programLayers])]
}

const emitMapEvent = (eventName) => {
  if (!map) return
  emit('map-event', createMapEvent(eventName, {
    sessionId: props.sessionId,
    activeLayers: collectActiveLayerIds(),
    mapView: summarizeMapView(map)
  }))
}

const emitMapProgramReceipt = (eventName, receipt) => {
  if (!map || !props.mapProgram?.program_id) return
  emit('map-event', createMapEvent(eventName, {
    sessionId: props.sessionId,
    activeLayers: collectActiveLayerIds(),
    mapView: summarizeMapView(map),
    receipt
  }))
}

const handleMapViewChanged = () => {
  emitMapEvent('view_changed')
}

const attachMapEventListeners = () => {
  if (!map || typeof map.on !== 'function') return
  map.on('moveend', handleMapViewChanged)
  map.on('zoomend', handleMapViewChanged)
}

const detachMapEventListeners = () => {
  if (!map || typeof map.off !== 'function') return
  map.off('moveend', handleMapViewChanged)
  map.off('zoomend', handleMapViewChanged)
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

const clearProvinceOverlays = () => {
  if (map && provinceOverlays.length > 0) {
    try {
      map.remove(provinceOverlays)
    } catch {
      provinceOverlays.forEach((overlay) => {
        try {
          overlay.setMap(null)
        } catch {
          // Province overlay cleanup is best-effort because AMap plugin classes vary by version.
        }
      })
    }
  }
  provinceOverlays = []
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

const normalizeBoundaryPath = (boundary) => {
  if (!Array.isArray(boundary)) return []
  return boundary
    .map(point => {
      if (Array.isArray(point) && point.length >= 2) return [point[0], point[1]]
      if (typeof point?.getLng === 'function' && typeof point?.getLat === 'function') {
        return [point.getLng(), point.getLat()]
      }
      if (typeof point?.lng === 'number' && typeof point?.lat === 'number') return [point.lng, point.lat]
      return null
    })
    .filter(Boolean)
}

const extractLocalGuangdongBoundaries = () => {
  const features = Array.isArray(guangdongBoundary?.features) ? guangdongBoundary.features : []
  return features.flatMap(feature => {
    const geometry = feature?.geometry
    if (geometry?.type === 'Polygon') {
      return geometry.coordinates.map(normalizeBoundaryPath).filter(path => path.length > 0)
    }
    if (geometry?.type === 'MultiPolygon') {
      return geometry.coordinates
        .flatMap(polygon => polygon.map(normalizeBoundaryPath))
        .filter(path => path.length > 0)
    }
    return []
  })
}

const createGuangdongMaskPath = (boundaries) => [
  GUANGDONG_MASK_OUTER_PATH,
  ...boundaries
]

const renderProvinceFocusWithBoundaries = (boundaries) => {
  if (!map || !AMapApi?.Polygon || !boundaries.length) return

  clearProvinceOverlays()

  const mask = new AMapApi.Polygon({
    path: createGuangdongMaskPath(boundaries),
    className: 'gd-province-mask',
    strokeOpacity: 0,
    fillColor: '#101820',
    fillOpacity: 0.46,
    zIndex: 60,
    bubble: true
  })

  const boundaryPolygons = boundaries.map(path => new AMapApi.Polygon({
    path,
    className: 'gd-province-boundary',
    strokeColor: '#ffffff',
    strokeWeight: 2,
    strokeOpacity: 0.92,
    fillColor: '#4fb58f',
    fillOpacity: 0.08,
    zIndex: 70,
    bubble: true
  }))

  provinceOverlays = [mask, ...boundaryPolygons]
  map.add(provinceOverlays)
}

const renderProvinceFocus = () => {
  if (!map || !AMapApi?.Polygon) return

  const localBoundaries = extractLocalGuangdongBoundaries()
  renderProvinceFocusWithBoundaries(localBoundaries)
  if (!AMapApi?.DistrictSearch) return

  const districtSearch = new AMapApi.DistrictSearch({
    subdistrict: 0,
    extensions: 'all',
    level: 'province'
  })

  districtSearch.search('广东省', (status, result) => {
    if (destroyed || !map || status !== 'complete') return

    const boundaries = (result?.districtList?.[0]?.boundaries || [])
        .map(normalizeBoundaryPath)
        .filter(path => path.length > 0)
    if (!boundaries.length) return

    renderProvinceFocusWithBoundaries(boundaries)
  })
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

const createProgramPointMarker = (layer, feature) => {
  const coordinates = feature?.geometry?.coordinates
  if (!Array.isArray(coordinates) || coordinates.length < 2) return null
  const properties = feature.properties || {}
  const icon = resolvePointIconPreset(layer.style || {}, properties)
  return createMarker({
    type: 'station',
    name: properties.name || properties.station_name || layer.name || layer.id,
    position: coordinates,
    value: properties.value ?? properties.pm25 ?? null,
    icon,
    focused: true
  })
}

const normalizePolygonRings = (geometry) => {
  if (geometry?.type === 'Polygon') {
    return Array.isArray(geometry.coordinates)
      ? geometry.coordinates.map(normalizeBoundaryPath).filter(path => path.length > 0)
      : []
  }
  if (geometry?.type === 'MultiPolygon') {
    return Array.isArray(geometry.coordinates)
      ? geometry.coordinates
        .flatMap(polygon => polygon.map(normalizeBoundaryPath))
        .filter(path => path.length > 0)
      : []
  }
  return []
}

const createProgramPolygon = (layer, feature) => {
  if (!AMapApi?.Polygon) return null
  const path = normalizePolygonRings(feature?.geometry)
  if (!path.length) return null
  const style = layer.style || {}
  const properties = feature?.properties || {}
  const fillColorField = style.feature_fill_color_field || 'fill_color'
  const fillOpacityField = style.feature_fill_opacity_field || 'fill_opacity'
  const strokeColorField = style.feature_stroke_color_field || 'stroke_color'
  const strokeOpacityField = style.feature_stroke_opacity_field || 'stroke_opacity'
  return new AMapApi.Polygon({
    path,
    title: feature?.properties?.name || layer.name || layer.id,
    strokeColor: properties[strokeColorField] || style.stroke_color || style.strokeColor || '#1f5fbf',
    strokeWeight: style.stroke_weight ?? style.strokeWeight ?? 2,
    strokeOpacity: properties[strokeOpacityField] ?? style.stroke_opacity ?? style.strokeOpacity ?? 0.9,
    fillColor: properties[fillColorField] || style.fill_color || style.fillColor || '#2f80ed',
    fillOpacity: properties[fillOpacityField] ?? style.fill_opacity ?? style.fillOpacity ?? 0.18,
    zIndex: style.z_index ?? style.zIndex ?? 105,
    bubble: true
  })
}

const normalizeLinePaths = (geometry) => {
  if (geometry?.type === 'LineString') {
    const path = normalizeBoundaryPath(geometry.coordinates)
    return path.length > 0 ? [path] : []
  }
  if (geometry?.type === 'MultiLineString') {
    return Array.isArray(geometry.coordinates)
      ? geometry.coordinates.map(normalizeBoundaryPath).filter(path => path.length > 0)
      : []
  }
  return []
}

const createProgramLine = (layer, feature) => {
  if (!AMapApi?.Polyline) return null
  const paths = normalizeLinePaths(feature?.geometry)
  if (!paths.length) return null
  const style = layer.style || {}
  return paths.map(path => new AMapApi.Polyline({
    path,
    title: feature?.properties?.name || layer.name || layer.id,
    strokeColor: style.stroke_color || style.strokeColor || '#d7191c',
    strokeWeight: style.stroke_weight ?? style.strokeWeight ?? 2,
    strokeOpacity: style.stroke_opacity ?? style.strokeOpacity ?? 0.92,
    zIndex: style.z_index ?? style.zIndex ?? 112,
    bubble: true
  }))
}

const createProgramOverlay = (layer, feature) => {
  if (layer?.layer_type === 'point') return createProgramPointMarker(layer, feature)
  if (layer?.layer_type === 'polygon') return createProgramPolygon(layer, feature)
  if (layer?.layer_type === 'line') return createProgramLine(layer, feature)
  return null
}

const collectProgramOverlayResult = async () => {
  const entries = await loadProgramLayerFeatureEntries(props.mapProgram)
  const programOverlays = entries
    .map(({ layer, feature }) => createProgramOverlay(layer, feature))
    .flat()
    .filter(Boolean)
  return {
    entries,
    programOverlays
  }
}

const applyProgramFitBounds = (programOverlays) => {
  const view = props.mapProgram?.state?.view || {}
  if (view.fit_bounds !== true || !programOverlays?.length || typeof map?.setFitView !== 'function') return
  try {
    map.setFitView(programOverlays)
  } catch {
    // Fit bounds is a navigation convenience; rendering should still succeed if the map API rejects an overlay class.
  }
}

const renderOverlays = async () => {
  if (!map || !AMapApi) return
  const token = ++overlayRenderToken
  clearOverlays()
  clearHeatmap()

  const nextOverlays = []
  if (props.layers?.city_metrics) {
    nextOverlays.push(...extractCityMetricMarkers(props.overview, props.focus).map(createMarker))
  }
  if (props.layers?.stations) {
    nextOverlays.push(...extractStationMarkers(props.overview, props.focus).map(createMarker))
  }

  let programReceipt = null
  let programOverlays = []
  try {
    const programResult = await collectProgramOverlayResult()
    programOverlays = programResult.programOverlays
    nextOverlays.push(...programOverlays)
    if (props.mapProgram?.program_id) {
      programReceipt = createMapProgramExecutionReceipt(props.mapProgram, {
        status: 'executed',
        layers: summarizeProgramLayerRenderResults(props.mapProgram, programResult.entries)
      })
    }
  } catch (err) {
    if (props.mapProgram?.program_id) {
      programReceipt = createMapProgramExecutionReceipt(props.mapProgram, {
        status: 'failed',
        errors: [{ message: err?.message || 'map program layer rendering failed' }]
      })
    }
    // Program layer data is optional; dashboard base layers should still render.
  }

  if (token !== overlayRenderToken || destroyed || !map) return

  overlays = nextOverlays
  if (overlays.length > 0) {
    map.add(overlays)
  }
  applyProgramFitBounds(programOverlays)

  if (programReceipt) {
    emitMapProgramReceipt(
      programReceipt.status === 'failed' ? 'map_program_failed' : 'map_program_executed',
      programReceipt
    )
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

const normalizeCenter = (center) => {
  if (!Array.isArray(center) || center.length < 2) return null
  const lng = Number(center[0])
  const lat = Number(center[1])
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
  return [lng, lat]
}

const applyProgramView = () => {
  if (!map) return
  const view = props.mapProgram?.state?.view || {}
  const center = normalizeCenter(view.center)
  const zoom = Number(view.zoom)
  const hasZoom = Number.isFinite(zoom)

  if (center && hasZoom && typeof map.setZoomAndCenter === 'function') {
    map.setZoomAndCenter(zoom, center)
    return
  }
  if (center && typeof map.setCenter === 'function') {
    map.setCenter(center)
  }
  if (hasZoom && typeof map.setZoom === 'function') {
    map.setZoom(zoom)
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
    map.setZoomAndCenter(GUANGDONG_FOCUS_ZOOM, GUANGDONG_CENTER)
    attachMapEventListeners()
    addControls()
    renderProvinceFocus()
    applyProgramView()
    await renderOverlays()
  } catch (err) {
    error.value = err?.message || '高德地图加载失败。'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.overview, props.focus, props.layers, props.mapProgram],
  async () => {
    applyProgramView()
    await renderOverlays()
  },
  { deep: true }
)

onMounted(() => {
  initMap()
})

onBeforeUnmount(() => {
  destroyed = true
  clearOverlays()
  clearProvinceOverlays()
  clearHeatmap()
  detachMapEventListeners()
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

:deep(.gd-overview-marker.station.icon-pollution_source) {
  background: #7a4d9f;
}

:deep(.gd-overview-marker.station.icon-factory) {
  background: #49545a;
  border-radius: 5px;
}

:deep(.gd-overview-marker.station.icon-dust) {
  background: #b7791f;
  border-style: dashed;
}

:deep(.gd-overview-marker.station.icon-traffic) {
  width: 24px;
  height: 18px;
  background: #2f6f8f;
  border-radius: 6px;
}

:deep(.gd-overview-marker.station.icon-fire) {
  background: #c2412d;
  border-radius: 50% 50% 50% 8px;
  transform: rotate(-45deg);
}

:deep(.gd-overview-marker.station.icon-monitor) {
  background: #1f7a75;
  border-radius: 4px;
}

:deep(.gd-overview-marker.station.icon-selected) {
  background: #d4523f;
  box-shadow: 0 0 0 5px rgba(212, 82, 63, 0.24), 0 4px 12px rgba(32, 49, 58, 0.28);
}

:deep(.gd-overview-marker.station.icon-pollution_source span),
:deep(.gd-overview-marker.station.icon-factory span),
:deep(.gd-overview-marker.station.icon-dust span),
:deep(.gd-overview-marker.station.icon-traffic span),
:deep(.gd-overview-marker.station.icon-fire span),
:deep(.gd-overview-marker.station.icon-monitor span),
:deep(.gd-overview-marker.station.icon-selected span) {
  display: none;
}
</style>
