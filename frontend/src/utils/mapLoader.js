/**
 * 高德地图加载器
 * 负责按需加载高德地图 JS API，并提供单例管理
 */
import AMapLoader from '@amap/amap-jsapi-loader'
import { resolveAMapConfig } from './amapConfig.js'

let AMapInstance = null
let loadingPromise = null

/**
 * 加载高德地图 API
 * @returns {Promise<AMap>} 高德地图实例
 */
export async function loadAMap() {
  // 如果已加载，直接返回
  if (AMapInstance) {
    return AMapInstance
  }

  // 如果正在加载，返回同一个 Promise
  if (loadingPromise) {
    return loadingPromise
  }

  const amapConfig = await resolveAMapConfig({ env: import.meta.env })
  if (!amapConfig.key) {
    throw new Error('缺少高德地图 API Key，无法加载高德地图。')
  }

  // 开始加载
  loadingPromise = AMapLoader.load({
    key: amapConfig.key,
    version: '2.0',
    plugins: [
      'AMap.Scale',           // 比例尺
      'AMap.ToolBar',         // 工具条
      'AMap.ControlBar',      // 3D控制
      'AMap.MouseTool',       // 鼠标工具
      'AMap.PolygonEditor',   // 多边形编辑
      'AMap.Geocoder',        // 地理编码
      'AMap.InfoWindow',      // 信息窗口
      'AMap.DistrictSearch',   // 行政区边界查询
      'AMap.HeatMap'          // 热力图
    ],
    // 添加安全密钥配置（如果有的话）
    securityJsCode: amapConfig.securityJsCode || ''
  }).then(AMap => {
    AMapInstance = AMap
    console.log('高德地图 API 加载成功')
    return AMap
  }).catch(err => {
    console.error('高德地图 API 加载失败:', err)
    loadingPromise = null  // 重置加载状态，允许重试
    throw err
  })

  return loadingPromise
}

/**
 * 重置地图实例（用于测试或重新加载）
 */
export function resetAMap() {
  AMapInstance = null
  loadingPromise = null
}
