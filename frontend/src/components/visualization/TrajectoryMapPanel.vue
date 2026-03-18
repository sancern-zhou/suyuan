<template>
  <div class="trajectory-map-panel">
    <!-- 地图容器 -->
    <div ref="mapContainer" class="map-container"></div>

    <!-- 加载状态 -->
    <div v-if="loading" class="map-loading">
      <div class="spinner"></div>
      <p>地图加载中...</p>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="map-error">
      <p>{{ error }}</p>
      <button @click="retryLoad">重试</button>
    </div>

    <!-- 轨迹控制面板 -->
    <div v-if="mapInstance && !loading && !error" class="trajectory-controls">
      <div class="control-header">
        <h4>轨迹分析</h4>
        <span class="trajectory-count">{{ trajectoryCount }} 条轨迹</span>
      </div>

      <!-- 图层开关 -->
      <div class="control-group">
        <h5>图层</h5>
        <label>
          <input type="checkbox" v-model="layers.trajectories" @change="toggleTrajectories">
          <span>轨迹线</span>
        </label>
        <label>
          <input type="checkbox" v-model="layers.markers" @change="toggleMarkers">
          <span>起止点标记</span>
        </label>
        <label v-if="hasTimeLabels">
          <input type="checkbox" v-model="layers.timeLabels" @change="toggleTimeLabels">
          <span>时间标签</span>
        </label>
      </div>

      <!-- 轨迹信息 -->
      <div class="control-group trajectory-info" v-if="trajectoryStats">
        <h5>轨迹统计</h5>
        <div class="stat-item">
          <span class="stat-label">主导方向</span>
          <span class="stat-value">{{ trajectoryStats.dominant_direction || '未知' }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">总距离</span>
          <span class="stat-value">{{ trajectoryStats.total_distance_km?.toFixed(1) || '0' }} km</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">平均速度</span>
          <span class="stat-value">{{ trajectoryStats.avg_speed_ms?.toFixed(1) || '0' }} m/s</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">轨迹点数</span>
          <span class="stat-value">{{ trajectoryStats.trajectory_points || 0 }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { loadAMap } from '@/utils/mapLoader'

const props = defineProps({
  config: {
    type: Object,
    required: true,
    validator: (config) => {
      return config.map_center && config.layers
    }
  }
})

const emit = defineEmits(['ready'])

// 状态管理
const mapContainer = ref(null)
const mapInstance = ref(null)
const loading = ref(true)
const error = ref(null)

// 地图对象存储
const mapObjects = reactive({
  trajectories: [],
  markers: [],
  timeLabels: []
})

// 图层控制
const layers = reactive({
  trajectories: true,
  markers: true,
  timeLabels: false
})

// 辅助函数：安全获取坐标
function getCoords(point) {
  if (!point) return { lng: null, lat: null }
  const lng = point.lng ?? point.lon ?? point.longitude ?? null
  const lat = point.lat ?? point.latitude ?? null
  return { lng, lat }
}

function isValidCoord(point) {
  const { lng, lat } = getCoords(point)
  return lng !== null && lat !== null && !isNaN(lng) && !isNaN(lat)
}

// 计算属性
const trajectoryCount = computed(() => {
  // 适配轨迹分析结果：包含heatmap（轨迹密度点）和markers（企业标记）
  const layers = props.config?.layers || []
  let count = 0

  // 从heatmap数据中计算轨迹点数量（优化：限制最大显示数量）
  const heatmapLayer = layers.find(l => l.type === 'heatmap')
  if (heatmapLayer?.data?.length) {
    // 只统计实际渲染的点数（最多200个）
    count += Math.min(heatmapLayer.data.length, 200)
  }

  // 从polyline轨迹线中计算轨迹数量
  const polylineLayer = layers.find(l => l.type === 'polyline')
  if (polylineLayer?.data?.length) {
    count += polylineLayer.data.length
  }

  return count
})

const hasTimeLabels = computed(() => {
  return trajectoryCount.value > 0
})

const trajectoryStats = computed(() => {
  // 从config.meta或payload.meta中获取统计信息
  return props.config?.meta?.trajectory_stats || null
})

// 地图初始化
async function initMap() {
  try {
    loading.value = true
    error.value = null

    // 检查 API Key
    if (!import.meta.env.VITE_AMAP_KEY) {
      throw new Error('缺少高德地图 API Key，请在 .env.local 中配置 VITE_AMAP_KEY')
    }

    // 加载高德地图 API
    const AMap = await loadAMap()

    // 创建地图实例（支持 lng/lon 两种字段名）
    const center = props.config.map_center || {}
    const centerLng = center.lng || center.lon || center.longitude || 113.3
    const centerLat = center.lat || center.latitude || 23.1
    
    if (!centerLng || !centerLat || isNaN(centerLng) || isNaN(centerLat)) {
      console.error('轨迹地图中心点坐标无效:', { centerLng, centerLat })
    }
    
    mapInstance.value = new AMap.Map(mapContainer.value, {
      center: [centerLng, centerLat],
      zoom: props.config.zoom || 6,
      resizeEnable: true,
      mapStyle: 'amap://styles/normal',
      viewMode: '2D',
      preserveDrawingBuffer: true
    })

    // 添加控件
    mapInstance.value.addControl(new AMap.Scale())
    mapInstance.value.addControl(new AMap.ToolBar({
      position: {
        bottom: '20px',
        left: '20px'
      }
    }))

    // 渲染图层
    await renderLayers(AMap)

    // 自适应视野
    fitBounds(AMap)

    loading.value = false
    emit('ready')

    console.log('轨迹地图初始化成功', {
      center,
      zoom: props.config.zoom,
      trajectoryCount: trajectoryCount.value
    })

  } catch (err) {
    console.error('轨迹地图初始化失败:', err)
    error.value = err.message
    loading.value = false
  }
}

// 渲染所有图层
async function renderLayers(AMap) {
  const { layers: configLayers } = props.config

  if (!configLayers || !Array.isArray(configLayers)) {
    console.warn('没有图层配置')
    return
  }

  for (const layer of configLayers) {
    if (layer.type === 'trajectory_layer') {
      await renderTrajectories(AMap, layer.trajectories || [])
    } else if (layer.type === 'marker_layer') {
      await renderMarkers(AMap, layer.markers || [])
    } else if (layer.type === 'heatmap') {
      await renderHeatmap(AMap, layer.data || [], layer.options || {})
    } else if (layer.type === 'markers') {
      await renderMarkers(AMap, layer.data || [])
    } else if (layer.type === 'marker') {
      await renderMarkers(AMap, layer.data || [])
    } else if (layer.type === 'polyline') {
      await renderTrajectories(AMap, layer.data || [])
    }
  }
}

// 渲染热力图
async function renderHeatmap(AMap, heatmapData, options) {
  if (!heatmapData || heatmapData.length === 0) {
    console.warn('没有热力图数据')
    return
  }

  console.log('开始渲染热力图，原始数据点数量:', heatmapData.length)

  // 加载热力图插件
  await new Promise((resolve, reject) => {
    AMap.plugin('AMap.HeatMap', () => {
      resolve()
    })
  })

  // 创建热力图实例
  const heatmap = new AMap.HeatMap(mapInstance.value, {
    radius: options.radius || 30,  // 增大半径
    opacity: options.opacity || 0.7,  // 提高不透明度
    gradient: options.gradient || {
      '0.4': 'blue',
      '0.6': 'cyan',
      '0.8': 'lime',
      '0.9': 'yellow',
      '0.95': 'orange',
      '1.0': 'red'
    }
  })

  // 优化：数据采样和聚合，减少数据点数量
  let optimizedData = heatmapData

  if (heatmapData.length > 200) {
    console.log('数据点过多，进行采样优化...')
    // 采样策略：保留权重高的点，同时保持空间分布
    const sortedData = [...heatmapData]
      .sort((a, b) => (b.count || b.weight || 0) - (a.count || a.weight || 0))

    // 保留前100个高权重点
    const topPoints = sortedData.slice(0, 100)

    // 从剩余点中均匀采样
    const remainingPoints = sortedData.slice(100)
    const sampleStep = Math.ceil(remainingPoints.length / 100)
    const sampledPoints = remainingPoints.filter((_, index) => index % sampleStep === 0)

    optimizedData = [...topPoints, ...sampledPoints].slice(0, 200)
    console.log('采样完成，优化后数据点数量:', optimizedData.length)
  }

  // 准备热力图数据（转换为AMap需要的格式）
  const heatmapPoints = optimizedData.map(point => {
    const { lng, lat } = getCoords(point)
    return {
      lng: lng,
      lat: lat,
      count: point.count || point.weight || 1
    }
  }).filter(point => point.lng && point.lat)

  console.log('热力图数据转换完成，有效点数:', heatmapPoints.length)

  // 计算max值，避免过大的值导致显示异常
  const maxCount = Math.max(...heatmapPoints.map(p => p.count))
  const adjustedMax = Math.max(maxCount, 10)  // 最小值为10

  // 设置数据并渲染
  heatmap.setDataSet({
    data: heatmapPoints,
    max: adjustedMax
  })

  // 添加到地图
  mapInstance.value.add(heatmap)

  console.log('热力图渲染完成，max值:', adjustedMax)
}

// 渲染轨迹线
async function renderTrajectories(AMap, trajectories) {
  if (!trajectories || trajectories.length === 0) {
    console.warn('没有轨迹数据')
    return
  }

  trajectories.forEach((traj, index) => {
    if (!traj.path || traj.path.length < 2) {
      console.warn(`轨迹 ${index} 路径点不足`)
      return
    }

    // 转换路径格式（使用安全坐标访问）
    const path = traj.path.filter(p => isValidCoord(p)).map(p => {
      const { lng, lat } = getCoords(p)
      return [lng, lat]
    })

    // 创建轨迹线
    const polyline = new AMap.Polyline({
      path,
      strokeColor: traj.color || '#FF6B6B',
      strokeWeight: traj.width || 3,
      strokeOpacity: traj.opacity || 0.8,
      strokeStyle: traj.direction_arrows ? 'dashed' : 'solid',
      zIndex: 50
    })

    // 添加箭头装饰（显示方向）
    if (traj.direction_arrows) {
      polyline.setOptions({
        showDir: true,
        dirColor: traj.color || '#FF6B6B',
        dirImg: 'https://webapi.amap.com/theme/v1.3/markers/n/mark_b.png'
      })
    }

    // 点击事件
    polyline.on('click', () => {
      showTrajectoryInfo(AMap, traj)
    })

    mapInstance.value.add(polyline)
    mapObjects.trajectories.push(polyline)

    console.log(`轨迹 ${index} 已渲染`, {
      points: traj.path.length,
      color: traj.color
    })
  })
}

// 渲染标记点
async function renderMarkers(AMap, markers) {
  if (!markers || markers.length === 0) {
    console.warn('没有标记点数据')
    return
  }

  markers.forEach((markerData, index) => {
    // 适配轨迹分析结果中的标记格式
    let lng, lat, label, title, iconType, color

    if (markerData.position && Array.isArray(markerData.position)) {
      // 轨迹分析结果格式：{ position: [lng, lat], title: "...", label: {...}, extData: {...} }
      lng = markerData.position[0]
      lat = markerData.position[1]
      title = markerData.title || ''
      label = markerData.label?.content || ''
      iconType = 'enterprise'
      color = '#FF6B6B'
    } else {
      // 标准格式：{ lng, lat, label, icon, color }
      const coords = getCoords(markerData)
      lng = coords.lng
      lat = coords.lat
      label = markerData.label || ''
      iconType = markerData.icon
      color = markerData.color
      title = markerData.title || markerData.label
    }

    // 验证坐标有效性
    if (!lng || !lat || isNaN(lng) || isNaN(lat)) {
      console.warn(`跳过无效坐标的标记 ${index}:`, markerData)
      return
    }

    // 创建自定义图标内容
    const iconContent = createMarkerIcon(iconType, color)

    const marker = new AMap.Marker({
      position: [lng, lat],
      content: iconContent,
      offset: new AMap.Pixel(-12, -30),
      title: title || label,
      extData: markerData.extData || markerData
    })

    // 添加文本标注（优先级：label > title）
    const labelText = label || title
    if (labelText) {
      const text = new AMap.Text({
        text: labelText,
        position: [lng, lat],
        offset: new AMap.Pixel(0, -35),
        style: {
          'background-color': color || '#FF6B6B',
          'border': '2px solid white',
          'padding': '4px 8px',
          'border-radius': '4px',
          'font-size': '12px',
          'font-weight': 'bold',
          'color': 'white',
          'box-shadow': '0 2px 6px rgba(0,0,0,0.3)'
        }
      })
      mapInstance.value.add(text)
      mapObjects.timeLabels.push(text)
    }

    // 点击事件
    marker.on('click', () => {
      const content = `
        <div class="trajectory-popup">
          <h3>${title || '企业'}</h3>
          ${markerData.extData?.industry ? `
          <div class="info-row">
            <span class="label">行业</span>
            <span class="value">${markerData.extData.industry}</span>
          </div>` : ''}
          ${markerData.extData?.contribution ? `
          <div class="info-row">
            <span class="label">贡献率</span>
            <span class="value">${markerData.extData.contribution}</span>
          </div>` : ''}
          ${markerData.extData?.rank ? `
          <div class="info-row">
            <span class="label">排名</span>
            <span class="value">#${markerData.extData.rank}</span>
          </div>` : ''}
        </div>
      `
      const infoWindow = new AMap.InfoWindow({
        content,
        offset: new AMap.Pixel(0, -10)
      })
      infoWindow.open(mapInstance.value, marker.getPosition())
    })

    mapInstance.value.add(marker)
    mapObjects.markers.push(marker)

    console.log(`标记 ${index} 已渲染`, {
      label: labelText,
      icon: iconType,
      position: [lng, lat]
    })
  })
}

// 创建标记图标
function createMarkerIcon(iconType, color) {
  const iconColor = color || '#FF6B6B'

  if (iconType === 'start') {
    return `
      <div style="
        width: 24px;
        height: 24px;
        background: ${iconColor};
        border: 3px solid white;
        border-radius: 50%;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
      ">
        <span style="color: white; font-weight: bold;">S</span>
      </div>
    `
  } else if (iconType === 'end') {
    return `
      <div style="
        width: 24px;
        height: 24px;
        background: ${iconColor};
        border: 3px solid white;
        border-radius: 50%;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
      ">
        <span style="color: white; font-weight: bold;">E</span>
      </div>
    `
  } else if (iconType === 'enterprise') {
    // 企业标记（轨迹分析结果使用）
    return `
      <div style="
        width: 24px;
        height: 24px;
        background: ${iconColor};
        border: 3px solid white;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
      ">
        <div style="
          width: 8px;
          height: 8px;
          background: white;
          border-radius: 50%;
          transform: rotate(45deg);
        "></div>
      </div>
    `
  } else if (iconType === 'target') {
    // 分析点标记
    return `
      <div style="
        width: 28px;
        height: 28px;
        background: ${iconColor};
        border: 3px solid white;
        border-radius: 50%;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
      ">
        <span style="color: white; font-weight: bold;">🎯</span>
      </div>
    `
  }

  // 默认标记
  return `
    <div style="
      width: 16px;
      height: 16px;
      background: ${iconColor};
      border: 2px solid white;
      border-radius: 50%;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    "></div>
  `
}

// 显示轨迹信息
function showTrajectoryInfo(AMap, traj) {
  const content = `
    <div class="trajectory-popup">
      <h3>${traj.id || '轨迹'}</h3>
      <div class="info-row">
        <span class="label">轨迹点数</span>
        <span class="value">${traj.path?.length || 0}</span>
      </div>
      ${traj.metadata?.start_time ? `
      <div class="info-row">
        <span class="label">起始时间</span>
        <span class="value">${new Date(traj.metadata.start_time).toLocaleString()}</span>
      </div>` : ''}
      ${traj.metadata?.data_source ? `
      <div class="info-row">
        <span class="label">数据源</span>
        <span class="value">${traj.metadata.data_source}</span>
      </div>` : ''}
    </div>
  `

  const infoWindow = new AMap.InfoWindow({
    content,
    offset: new AMap.Pixel(0, -10)
  })

  // 使用安全坐标访问
  let position = mapInstance.value.getCenter()
  if (traj.path && traj.path[0] && isValidCoord(traj.path[0])) {
    const { lng, lat } = getCoords(traj.path[0])
    position = [lng, lat]
  }
  infoWindow.open(mapInstance.value, position)
}

// 自适应视野
function fitBounds(AMap) {
  const allPoints = []

  // 收集所有轨迹点
  mapObjects.trajectories.forEach(polyline => {
    const path = polyline.getPath()
    if (path && path.length > 0) {
      path.forEach(lngLat => {
        allPoints.push(lngLat)
      })
    }
  })

  // 收集所有标记点
  mapObjects.markers.forEach(marker => {
    const pos = marker.getPosition()
    if (pos) {
      allPoints.push(pos)
    }
  })

  // 收集热力图数据点
  const heatmapLayer = props.config?.layers?.find(l => l.type === 'heatmap')
  if (heatmapLayer?.data?.length) {
    heatmapLayer.data.forEach(point => {
      const { lng, lat } = getCoords(point)
      if (lng && lat && !isNaN(lng) && !isNaN(lat)) {
        allPoints.push(new AMap.LngLat(lng, lat))
      }
    })
  }

  if (allPoints.length === 0) {
    console.warn('没有可用的坐标点进行自适应')
    return
  }

  // 创建边界并自适应
  const bounds = new AMap.Bounds(allPoints[0], allPoints[0])
  allPoints.forEach(point => {
    bounds.extend(point)
  })

  mapInstance.value.setBounds(bounds, true, [60, 260, 60, 60])
}

// 交互控制
function toggleTrajectories() {
  mapObjects.trajectories.forEach(polyline => {
    polyline.setMap(layers.trajectories ? mapInstance.value : null)
  })
}

function toggleMarkers() {
  mapObjects.markers.forEach(marker => {
    marker.setMap(layers.markers ? mapInstance.value : null)
  })
}

function toggleTimeLabels() {
  mapObjects.timeLabels.forEach(text => {
    text.setMap(layers.timeLabels ? mapInstance.value : null)
  })
}

function retryLoad() {
  initMap()
}

// 生命周期
onMounted(() => {
  initMap()
})

onBeforeUnmount(() => {
  if (mapInstance.value) {
    mapInstance.value.destroy()
  }
})

// 监听配置变化
watch(() => props.config, (newConfig, oldConfig) => {
  if (mapInstance.value && newConfig !== oldConfig) {
    // 清理旧对象
    mapInstance.value.clearMap()
    mapObjects.trajectories = []
    mapObjects.markers = []
    mapObjects.timeLabels = []

    // 重新渲染
    initMap()
  }
}, { deep: true })

// 获取地图截图（用于导出报告）
const getChartImage = async (options = {}) => {
  if (!mapContainer.value) return null
  
  // 优先尝试直接从地图 canvas 导出（preserveDrawingBuffer 必须开启）
  try {
    const canvasEl = mapContainer.value.querySelector('canvas')
    if (canvasEl && typeof canvasEl.toDataURL === 'function') {
      return canvasEl.toDataURL('image/png')
    }
  } catch (e) {
    console.warn('[TrajectoryMapPanel] 原生canvas截图失败，降级html2canvas:', e)
  }

  // 降级使用 html2canvas
  try {
    const { default: html2canvas } = await import('html2canvas')
    const {
      pixelRatio = 2,
      backgroundColor = '#fff'
    } = options
    const canvas = await html2canvas(mapContainer.value, {
      useCORS: true,
      allowTaint: true,
      scale: pixelRatio,
      backgroundColor,
      logging: false
    })
    return canvas.toDataURL('image/png')
  } catch (error) {
    console.error('[TrajectoryMapPanel] 截图失败:', error)
    return null
  }
}

// 获取地图状态
const getChartState = () => {
  if (!mapInstance.value) return null
  
  try {
    const center = mapInstance.value.getCenter()
    const zoom = mapInstance.value.getZoom()
    
    return {
      center: { lng: center.getLng(), lat: center.getLat() },
      zoom: zoom
    }
  } catch (error) {
    console.error('[TrajectoryMapPanel] 获取状态失败:', error)
    return null
  }
}

// 暴露方法给父组件
defineExpose({
  getChartImage,
  getChartState,
  mapInstance
})
</script>

<style lang="scss" scoped>
.trajectory-map-panel {
  position: relative;
  width: 100%;
  height: 600px;
  background: #f5f5f5;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.map-container {
  width: 100%;
  height: 100%;
}

.map-loading, .map-error {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.95);
  z-index: 1000;
  gap: 12px;

  p {
    margin: 0;
    color: #666;
    font-size: 14px;
  }

  button {
    padding: 8px 20px;
    background: #1976d2;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    transition: background 0.2s;

    &:hover {
      background: #1565c0;
    }
  }
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f0f0f0;
  border-top-color: #1976d2;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.trajectory-controls {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 240px;
  max-height: 560px;
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.96);
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  backdrop-filter: blur(4px);
}

.control-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;

  h4 {
    margin: 0 0 4px 0;
    font-size: 16px;
    font-weight: 600;
    color: #333;
  }

  .trajectory-count {
    font-size: 12px;
    color: #666;
  }
}

.control-group {
  margin-bottom: 16px;

  &:last-child {
    margin-bottom: 0;
  }

  h5 {
    margin: 0 0 10px 0;
    font-size: 13px;
    font-weight: 600;
    color: #555;
  }

  label {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 13px;
    cursor: pointer;
    user-select: none;

    &:hover {
      color: #1976d2;
    }

    input[type="checkbox"] {
      cursor: pointer;
      width: 16px;
      height: 16px;
    }

    span {
      flex: 1;
    }
  }
}

.trajectory-info {
  background: #fafafa;
  padding: 12px;
  border-radius: 6px;

  .stat-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    font-size: 12px;

    &:last-child {
      margin-bottom: 0;
    }

    .stat-label {
      color: #666;
      font-weight: 500;
    }

    .stat-value {
      color: #333;
      font-weight: 600;
      font-family: monospace;
    }
  }
}

// 自定义滚动条
.trajectory-controls::-webkit-scrollbar {
  width: 6px;
}

.trajectory-controls::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.trajectory-controls::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;

  &:hover {
    background: #a8a8a8;
  }
}

// 信息窗口样式（通过全局样式注入）
:deep(.trajectory-popup) {
  padding: 12px;
  min-width: 200px;

  h3 {
    margin: 0 0 12px 0;
    font-size: 16px;
    font-weight: 600;
    color: #333;
    border-bottom: 2px solid #FF6B6B;
    padding-bottom: 8px;
  }

  .info-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    font-size: 13px;

    &:last-child {
      margin-bottom: 0;
    }

    .label {
      color: #666;
      font-weight: 500;
      margin-right: 12px;
    }

    .value {
      color: #333;
      font-weight: 600;
    }
  }
}
</style>
