<template>
  <div class="map-panel">
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


  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { loadAMap } from '@/utils/mapLoader'
import { MAP_CONFIG, MARKER_ICONS, INDUSTRY_COLORS, PATH_STYLES, SECTOR_STYLES, INFO_WINDOW_STYLES } from '@/config/mapConfig'

const props = defineProps({
  config: {
    type: Object,
    required: true,
    validator: (config) => {
      return config.map_center && config.station && config.enterprises
    }
  }
})

const emit = defineEmits(['ready', 'markerClick'])

// 状态管理
const mapContainer = ref(null)
const mapInstance = ref(null)
const loading = ref(true)
const error = ref(null)

// 地图对象存储
const markers = reactive({
  station: null,
  enterprises: [],
  upwindPaths: [],
  sectors: []
})

// 图层控制
const layers = reactive({
  enterprises: true,
  upwindPaths: true,
  sectors: true
})

// 筛选状态
const selectedIndustries = ref(new Set())
const maxDistance = ref(50)
const maxDistanceLimit = ref(50)

// 计算属性
const industries = computed(() => {
  if (!props.config?.enterprises) return []
  const industrySet = new Set(props.config.enterprises.map(e => e.industry).filter(Boolean))
  return Array.from(industrySet)
})

const enterpriseCount = computed(() => {
  return props.config?.enterprises?.length || 0
})

const hasUpwindPaths = computed(() => {
  return props.config?.upwind_paths?.length > 0
})

const hasSectors = computed(() => {
  return props.config?.sectors?.length > 0
})

// 获取行业颜色
function getIndustryColor(industry) {
  return INDUSTRY_COLORS[industry] || INDUSTRY_COLORS['其他']
}

// 【优化】判断是否应该显示企业名称标签
function shouldShowLabel(enterprise, index) {
  // 显示逻辑：前10个企业显示标签，完整显示排名前十的企业
  if (index < 10) {
    return true
  }
  return false
}

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

    // 获取地图中心点坐标（支持多种字段名，确保转换为数字）
    const mapCenter = props.config.map_center || {}
    let centerLng = Number(mapCenter.lng || mapCenter.lon || mapCenter.longitude)
    let centerLat = Number(mapCenter.lat || mapCenter.latitude)
    
    console.log('[MapPanel] 地图中心点:', { mapCenter, centerLng, centerLat })
    
    // 如果中心点无效，尝试从站点获取
    if (!centerLng || !centerLat || isNaN(centerLng) || isNaN(centerLat)) {
      const station = props.config.station || {}
      centerLng = Number(station.lng || station.lon || station.longitude) || 113.3
      centerLat = Number(station.lat || station.latitude) || 23.1
      console.warn('[MapPanel] 地图中心点无效，使用站点坐标或默认值:', { centerLng, centerLat })
    }

    // 创建地图实例
    mapInstance.value = new AMap.Map(mapContainer.value, {
      ...MAP_CONFIG,
      center: [centerLng, centerLat],
      zoom: calculateOptimalZoom(),
      viewMode: '2D',
      preserveDrawingBuffer: true
    })

    // 添加标准底图瓦片图层（确保底图显示）
    try {
      const tileLayer = new AMap.TileLayer({
        zIndex: 0,
        zooms: [1, 20]
      })
      tileLayer.setMap(mapInstance.value)
      console.log('[MapPanel] 底图瓦片图层添加成功')
    } catch (e) {
      console.warn('[MapPanel] 添加瓦片图层失败:', e)
    }

    // 注入信息窗口样式
    injectInfoWindowStyles()

    // 添加地图控件
    try {
      // 比例尺控件
      const scale = new AMap.Scale()
      mapInstance.value.addControl(scale)
      
      // 工具栏控件（缩放按钮等）
      const toolBar = new AMap.ToolBar({
        liteStyle: true  // 简洁模式
      })
      mapInstance.value.addControl(toolBar)
      
      console.log('[MapPanel] 地图控件添加成功')
    } catch (e) {
      console.warn('[MapPanel] 添加控件失败:', e)
    }

    // 渲染图层
    await renderStation(AMap)
    await renderEnterprises(AMap)
    if (hasUpwindPaths.value) await renderUpwindPaths(AMap)
    if (hasSectors.value) await renderSectors(AMap)

    // 自适应视野
    fitBounds(AMap)

    // 计算最大距离限制（支持 distance 和 distance_km 字段）
    if (props.config.enterprises?.length > 0) {
      const maxDist = Math.max(...props.config.enterprises.map(e => e.distance_km || e.distance || 0).filter(d => d > 0))
      maxDistanceLimit.value = Math.ceil(maxDist + 5)
      maxDistance.value = maxDistanceLimit.value
    }

    loading.value = false
    emit('ready')

    console.log('地图初始化成功', {
      center: props.config.map_center,
      enterprises: enterpriseCount.value,
      industries: industries.value
    })

  } catch (err) {
    console.error('地图初始化失败:', err)
    error.value = err.message
    loading.value = false
  }
}

// 注入信息窗口样式
function injectInfoWindowStyles() {
  if (document.getElementById('map-info-window-styles')) return

  const style = document.createElement('style')
  style.id = 'map-info-window-styles'
  style.textContent = INFO_WINDOW_STYLES
  document.head.appendChild(style)
}

// 渲染站点标记
async function renderStation(AMap) {
  const { station } = props.config
  
  // 验证站点坐标（确保转换为数字）
  const lng = Number(station.lng || station.lon || station.longitude)
  const lat = Number(station.lat || station.latitude)
  
  if (!lng || !lat || isNaN(lng) || isNaN(lat)) {
    console.error('[MapPanel] 站点坐标无效:', station.name, { lng, lat, station })
    return
  }

  console.log('[MapPanel] 创建站点标记:', station.name, [lng, lat])

  // 创建站点标记 DOM 元素
  const stationDiv = document.createElement('div')
  stationDiv.innerHTML = `
    <div style="position:relative;width:36px;height:36px;cursor:pointer;">
      <div style="position:absolute;bottom:0;left:50%;width:24px;height:24px;background:#1976d2;border-radius:50% 50% 50% 0;transform:rotate(-45deg) translateX(-50%);border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.3);"></div>
      <div style="position:absolute;bottom:8px;left:50%;transform:translateX(-50%);width:8px;height:8px;background:white;border-radius:50%;"></div>
    </div>
  `

  const marker = new AMap.Marker({
    position: new AMap.LngLat(lng, lat),
    content: stationDiv,
    offset: new AMap.Pixel(-18, -36),
    title: station.name,
    zIndex: 100
  })

  // 添加文本标注
  const label = new AMap.Text({
    text: station.name,
    position: new AMap.LngLat(lng, lat),
    offset: new AMap.Pixel(0, 8),
    style: {
      'background-color': 'rgba(25, 118, 210, 0.95)',
      'border': '2px solid white',
      'padding': '4px 10px',
      'border-radius': '4px',
      'font-size': '13px',
      'font-weight': 'bold',
      'color': 'white',
      'box-shadow': '0 2px 6px rgba(0,0,0,0.3)'
    }
  })

  mapInstance.value.add([marker, label])
  markers.station = { marker, label }
}

// 渲染企业标记
async function renderEnterprises(AMap) {
  const { enterprises } = props.config

  console.log('[MapPanel] renderEnterprises 开始, 企业总数:', enterprises?.length)
  console.log('[MapPanel] 企业数据示例:', enterprises?.[0])

  if (!enterprises || !Array.isArray(enterprises)) {
    console.error('[MapPanel] enterprises 数据无效:', enterprises)
    return
  }

  markers.enterprises = []
  let skippedCount = 0

  // 使用 forEach 获取索引
  enterprises.forEach((ent, idx) => {
    // 验证坐标有效性，跳过无效坐标
    const lng = ent.lng || ent.lon || ent.longitude
    const lat = ent.lat || ent.latitude

    // 转换为数字（防止字符串类型）
    const lngNum = Number(lng)
    const latNum = Number(lat)

    if (!lngNum || !latNum || isNaN(lngNum) || isNaN(latNum)) {
      console.warn('[MapPanel] 跳过无效坐标企业:', ent.name, { lng, lat, lngNum, latNum, rawEnt: ent })
      skippedCount++
      return
    }

    const markerColor = getIndustryColor(ent.industry)

    // 创建标记内容 DOM 元素
    const markerDiv = document.createElement('div')
    markerDiv.innerHTML = `
      <div style="position:relative;width:28px;height:28px;cursor:pointer;">
        <div style="position:absolute;bottom:0;left:50%;width:18px;height:18px;background:${markerColor};border-radius:50% 50% 50% 0;transform:rotate(-45deg) translateX(-50%);border:2px solid white;box-shadow:0 1px 6px rgba(0,0,0,0.3);"></div>
        <div style="position:absolute;bottom:6px;left:50%;transform:translateX(-50%);width:6px;height:6px;background:white;border-radius:50%;"></div>
      </div>
    `

    try {
      const marker = new AMap.Marker({
        position: new AMap.LngLat(lngNum, latNum),
        content: markerDiv,
        offset: new AMap.Pixel(-14, -28),
        title: ent.name,
        extData: ent,
        zIndex: 50
      })

      console.log('[MapPanel] 创建企业标记:', ent.name, [lngNum, latNum])

      // 点击事件 - 显示信息窗口
      marker.on('click', () => {
        showEnterpriseInfo(AMap, marker, ent)
        emit('markerClick', ent)
      })

      mapInstance.value.add(marker)

      // 【优化】为企业添加固定名称标签（仅对TOP-N企业或重要企业显示）
      if (shouldShowLabel(ent, idx)) {
        const label = new AMap.Text({
          text: ent.name,
          position: new AMap.LngLat(lngNum, latNum),
          offset: new AMap.Pixel(0, -40),
          style: {
            'background-color': 'rgba(255, 140, 0, 0.95)',  // 更鲜明的橙色
            'border': '2px solid white',                    // 更粗的边框
            'padding': '3px 8px',                           // 更大的内边距
            'border-radius': '4px',                         // 圆角
            'font-size': '12px',                            // 更大的字体
            'font-weight': '600',                           // 更粗的字重
            'color': 'white',                               // 白色文字
            'box-shadow': '0 2px 6px rgba(0,0,0,0.3)',     // 更明显的阴影
            'white-space': 'nowrap',
            'max-width': '150px',                           // 更宽的标签
            'overflow': 'hidden',
            'text-overflow': 'ellipsis'
          },
          zIndex: 60
        })
        mapInstance.value.add(label)
        markers.enterprises.push({ marker, label, data: ent, visible: true })
      } else {
        markers.enterprises.push({ marker, data: ent, visible: true })
      }
    } catch (err) {
      console.error('[MapPanel] 创建企业标记失败:', ent.name, err)
      skippedCount++
    }
  })
  
  console.log('[MapPanel] 渲染企业标记:', markers.enterprises.length, '/', enterprises.length, ', 跳过:', skippedCount)
}

// 显示企业信息窗口
function showEnterpriseInfo(AMap, marker, ent) {
  let emissionsHtml = ''
  if (ent.emissions && typeof ent.emissions === 'object') {
    const emissionEntries = Object.entries(ent.emissions)
    if (emissionEntries.length > 0) {
      emissionsHtml = `
        <div class="info-section">
          <h4>排放信息</h4>
          <div class="emissions-grid">
            ${emissionEntries.map(([key, val]) => `
              <div class="emission-item">
                <div class="em-label">${key}</div>
                <div class="em-value">${val}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `
    }
  }

  // 支持 distance_km 和 distance 两种字段名
  const distance = ent.distance_km || ent.distance
  const content = `
    <div class="enterprise-popup">
      <h3>${ent.name}</h3>
      <div class="info-row">
        <span class="label">行业</span>
        <span class="value" style="color: ${getIndustryColor(ent.industry)}">${ent.industry || '未知'}</span>
      </div>
      ${distance !== undefined ? `
      <div class="info-row">
        <span class="label">距离</span>
        <span class="value">${distance.toFixed(2)} km</span>
      </div>` : ''}
      ${ent.score !== undefined ? `
      <div class="info-row">
        <span class="label">评分</span>
        <span class="value">${ent.score}</span>
      </div>` : ''}
      ${emissionsHtml}
    </div>
  `

  const infoWindow = new AMap.InfoWindow({
    content,
    offset: new AMap.Pixel(0, -30),
    isCustom: false
  })

  infoWindow.open(mapInstance.value, marker.getPosition())
}

// 渲染上风向路径
async function renderUpwindPaths(AMap) {
  const { upwind_paths } = props.config

  console.log('渲染上风向路径', {
    count: upwind_paths?.length || 0,
    paths: upwind_paths
  })

  if (!upwind_paths || upwind_paths.length === 0) {
    console.warn('没有上风向路径数据')
    return
  }

  markers.upwindPaths = upwind_paths.map((path, pathIndex) => {
    if (!path.coordinates || path.coordinates.length === 0) {
      console.warn(`路径 ${pathIndex} 没有坐标数据`)
      return null
    }

    // 验证并过滤无效坐标（支持 lng/lon 两种字段名）
    const coords = path.coordinates
      .filter(coord => {
        const lng = coord?.lng ?? coord?.lon ?? coord?.longitude
        const lat = coord?.lat ?? coord?.latitude
        const isValid = typeof lng === 'number' &&
                       typeof lat === 'number' &&
                       !isNaN(lng) &&
                       !isNaN(lat)
        if (!isValid) {
          console.warn('发现无效坐标', coord)
        }
        return isValid
      })
      .map(coord => {
        const lng = coord.lng ?? coord.lon ?? coord.longitude
        const lat = coord.lat ?? coord.latitude
        return [lng, lat]
      })

    if (coords.length < 2) {
      console.warn(`路径 ${pathIndex} 有效坐标不足2个，无法绘制`)
      return null
    }

    console.log(`路径 ${pathIndex} 坐标`, coords)

    const polyline = new AMap.Polyline({
      path: coords,
      strokeColor: PATH_STYLES.upwind.strokeColor,
      strokeWeight: PATH_STYLES.upwind.strokeWeight,
      strokeOpacity: PATH_STYLES.upwind.strokeOpacity,
      strokeStyle: PATH_STYLES.upwind.strokeStyle,
      zIndex: PATH_STYLES.upwind.zIndex
    })

    mapInstance.value.add(polyline)
    console.log('路径已添加到地图', polyline)
    return polyline
  }).filter(Boolean)

  console.log('路径渲染完成，总数:', markers.upwindPaths.length)
}

// 渲染风向扇区
async function renderSectors(AMap) {
  const { sectors } = props.config

  console.log('渲染风向扇区', {
    count: sectors?.length || 0,
    sectors
  })

  if (!sectors || sectors.length === 0) {
    console.warn('没有风向扇区数据')
    return
  }

  markers.sectors = sectors.map((sector, sectorIndex) => {
    if (!sector.coordinates || sector.coordinates.length === 0) {
      console.warn(`扇区 ${sectorIndex} 没有坐标数据`)
      return null
    }

    // 验证并过滤无效坐标
    const coords = sector.coordinates
      .filter(coord => {
        const lng = coord?.lng ?? coord?.lon ?? coord?.longitude
        const lat = coord?.lat ?? coord?.latitude
        const isValid = typeof lng === 'number' &&
                       typeof lat === 'number' &&
                       !isNaN(lng) &&
                       !isNaN(lat)
        if (!isValid) {
          console.warn('发现无效坐标', coord)
        }
        return isValid
      })
      .map(coord => {
        const lng = coord.lng ?? coord.lon ?? coord.longitude
        const lat = coord.lat ?? coord.latitude
        return [lng, lat]
      })

    if (coords.length < 3) {
      console.warn(`扇区 ${sectorIndex} 有效坐标不足3个，无法绘制多边形`)
      return null
    }

    console.log(`扇区 ${sectorIndex} 坐标`, coords)

    const polygon = new AMap.Polygon({
      path: coords,
      fillColor: SECTOR_STYLES.default.fillColor,
      fillOpacity: SECTOR_STYLES.default.fillOpacity,
      strokeColor: SECTOR_STYLES.default.strokeColor,
      strokeWeight: SECTOR_STYLES.default.strokeWeight,
      strokeOpacity: SECTOR_STYLES.default.strokeOpacity,
      zIndex: SECTOR_STYLES.default.zIndex
    })

    mapInstance.value.add(polygon)
    console.log('扇区已添加到地图', polygon)
    return polygon
  }).filter(Boolean)

  console.log('扇区渲染完成，总数:', markers.sectors.length)
}

// 计算最优缩放级别
function calculateOptimalZoom() {
  const { enterprises } = props.config
  if (!enterprises?.length) return 12

  const distances = enterprises.map(e => e.distance || 0).filter(d => d > 0)
  if (distances.length === 0) return 12

  const maxDist = Math.max(...distances)

  if (maxDist < 3) return 14
  if (maxDist < 5) return 13
  if (maxDist < 10) return 12
  if (maxDist < 20) return 11
  return 10
}

// 自适应视野
function fitBounds(AMap) {
  const { enterprises, station, upwind_paths, sectors } = props.config

  // 辅助函数：安全获取坐标（确保转换为数字）
  const getCoords = (obj) => {
    if (!obj) return null
    const lng = Number(obj.lng || obj.lon || obj.longitude)
    const lat = Number(obj.lat || obj.latitude)
    if (lng && lat && !isNaN(lng) && !isNaN(lat)) {
      return new AMap.LngLat(lng, lat)
    }
    return null
  }

  // 获取站点坐标作为初始边界
  const stationLngLat = getCoords(station)
  if (!stationLngLat) {
    console.warn('[MapPanel] 站点坐标无效，跳过视野调整')
    return
  }

  // 收集所有坐标点
  const allPoints = [stationLngLat]

  // 添加企业坐标
  if (enterprises?.length) {
    enterprises.forEach(ent => {
      const lngLat = getCoords(ent)
      if (lngLat) {
        allPoints.push(lngLat)
      }
    })
  }

  // 添加上风向路径坐标
  if (upwind_paths?.length) {
    upwind_paths.forEach(path => {
      if (path.coordinates?.length) {
        path.coordinates.forEach(coord => {
          const lngLat = getCoords(coord)
          if (lngLat) {
            allPoints.push(lngLat)
          }
        })
      }
    })
  }

  // 添加扇区坐标
  if (sectors?.length) {
    sectors.forEach(sector => {
      if (sector.coordinates?.length) {
        sector.coordinates.forEach(coord => {
          const lngLat = getCoords(coord)
          if (lngLat) {
            allPoints.push(lngLat)
          }
        })
      }
    })
  }

  console.log('[MapPanel] fitBounds: 共', allPoints.length, '个坐标点')

  // 使用 setFitView 自动调整视野包含所有标记
  if (allPoints.length > 1) {
    mapInstance.value.setFitView(null, false, [50, 50, 50, 50])
  } else {
    // 只有一个点，设置中心和缩放
    mapInstance.value.setCenter(stationLngLat)
    mapInstance.value.setZoom(14)
  }
}

// 交互控制
function toggleEnterprises() {
  markers.enterprises.forEach(({ marker, visible }) => {
    if (layers.enterprises && visible) {
      marker.show()
    } else {
      marker.hide()
    }
  })
}

function toggleUpwindPaths() {
  markers.upwindPaths.forEach(polyline => {
    polyline.setMap(layers.upwindPaths ? mapInstance.value : null)
  })
}

function toggleSectors() {
  markers.sectors.forEach(polygon => {
    polygon.setMap(layers.sectors ? mapInstance.value : null)
  })
}

function toggleIndustry(industry) {
  if (selectedIndustries.value.has(industry)) {
    selectedIndustries.value.delete(industry)
  } else {
    selectedIndustries.value.add(industry)
  }
  filterEnterprises()
}

function filterByDistance() {
  filterEnterprises()
}

function filterEnterprises() {
  markers.enterprises.forEach(({ marker, label, data }, index) => {
    const industryMatch = selectedIndustries.value.size === 0 ||
                          selectedIndustries.value.has(data.industry)
    // 支持 distance_km 和 distance 两种字段名
    const dist = data.distance_km || data.distance
    const distanceMatch = !dist || dist <= maxDistance.value

    const shouldShow = industryMatch && distanceMatch
    markers.enterprises[index].visible = shouldShow

    if (layers.enterprises && shouldShow) {
      marker.show()
      // 同时控制标签的显示/隐藏
      if (label) {
        label.show()
      }
    } else {
      marker.hide()
      // 同时控制标签的显示/隐藏
      if (label) {
        label.hide()
      }
    }
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

  // 清理样式
  const styleEl = document.getElementById('map-info-window-styles')
  if (styleEl && document.querySelectorAll('.map-panel').length === 1) {
    styleEl.remove()
  }
})

// 监听配置变化
watch(() => props.config, (newConfig, oldConfig) => {
  if (mapInstance.value && newConfig !== oldConfig) {
    // 清理旧标记（包括标签）
    mapInstance.value.clearMap()
    markers.enterprises = []
    markers.upwindPaths = []
    markers.sectors = []
    markers.station = null

    // 重新渲染
    initMap()
  }
}, { deep: true })

// 获取地图截图（用于导出报告）
const getChartImage = async (options = {}) => {
  if (!mapContainer.value) return null
  
  // 优先使用底层 canvas 的 toDataURL（需 preserveDrawingBuffer）
  try {
    const canvasEl = mapContainer.value.querySelector('canvas')
    if (canvasEl && typeof canvasEl.toDataURL === 'function') {
      return canvasEl.toDataURL('image/png')
    }
  } catch (e) {
    console.warn('[MapPanel] 原生canvas截图失败，降级html2canvas:', e)
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
    console.error('[MapPanel] 截图失败:', error)
    return null
  }
}

// 获取地图状态（视野范围）
const getChartState = () => {
  if (!mapInstance.value) return null

  try {
    const center = mapInstance.value.getCenter && mapInstance.value.getCenter()
    const zoom = mapInstance.value.getZoom && mapInstance.value.getZoom()
    const bounds = mapInstance.value.getBounds && mapInstance.value.getBounds()

    // 检查中心点
    if (!center || typeof center.getLng !== 'function' || typeof center.getLat !== 'function') {
      console.warn('[MapPanel] 地图中心点尚未初始化或不可用')
      return null
    }

    // 边界检查，避免 northeast/southwest 为空时报错
    const hasBounds = bounds && bounds.northeast && bounds.southwest

    return {
      center: { lng: center.getLng(), lat: center.getLat() },
      zoom: zoom ?? null,
      bounds: hasBounds ? {
        northeast: { lng: bounds.northeast.getLng(), lat: bounds.northeast.getLat() },
        southwest: { lng: bounds.southwest.getLng(), lat: bounds.southwest.getLat() }
      } : null
    }
  } catch (error) {
    console.error('[MapPanel] 获取状态失败:', error)
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
.map-panel {
  position: relative;
  width: 100%;
  height: 500px;
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


</style>
