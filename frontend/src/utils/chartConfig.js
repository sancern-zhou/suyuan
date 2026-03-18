/**
 * 图表截图配置
 *
 * 功能：
 * - 定义截图的各项参数
 * - 配置不同图表类型的截图模式
 * - 缓存策略配置
 */

/**
 * 截图配置
 */
export const screenshotConfig = {
  // 基础截图参数
  base: {
    pixelRatio: 2,              // 截图清晰度（2倍高清）
    format: 'png',              // 图片格式
    quality: 1,                 // PNG质量（1为最高）
  },

  // 宽幅模式配置（用于报告插入）
  wide: {
    width: 1200,                // 固定宽度
    height: 500,                // 自适应高度
    removeDataZoom: true,       // 移除滑动轴
    removeLegend: false,        // 保留图例
    compactTitle: true,         // 紧凑标题
    backgroundColor: '#ffffff', // 背景色
  },

  // 标准模式（用于一般图表）
  standard: {
    width: 800,
    height: 500,
    removeDataZoom: false,
    removeLegend: false,
    backgroundColor: '#ffffff',
  },

  // 缩略图模式（用于预览）
  thumbnail: {
    width: 400,
    height: 300,
    removeDataZoom: true,
    removeLegend: false,
  },

  // 地图模式（保持原比例）
  map: {
    width: 800,
    height: 600,
    removeDataZoom: false,
  },

  // 图片类型模式（保持原样）
  original: {
    width: null,
    height: null,
    removeDataZoom: false,
  },

  // 缓存策略
  cache: {
    maxAge: 60000,              // 缓存有效期（60秒）
    maxSize: 50,                // 最大缓存数量
    cleanupInterval: 30000,     // 清理间隔（30秒）
  },

  // 图表类型对应的截图模式
  chartTypeModes: {
    // 时序图 -> 宽幅模式
    timeseries: 'wide',
    weather_timeseries: 'wide',
    pressure_pbl_timeseries: 'wide',
    stacked_timeseries: 'wide',
    facet_timeseries: 'wide',
    weather_ts: 'wide',
    pressure_pbl: 'wide',
    air_quality_timeseries: 'wide',
    air_quality_facet_timeseries: 'wide',
    particulate_stacked_timeseries: 'wide',

    // 统计图 -> 标准模式
    bar: 'standard',
    pie: 'standard',
    line: 'standard',

    // 专业分析图 -> 宽幅模式
    ternary_SNA: 'wide',
    sor_nor_scatter: 'wide',
    charge_balance: 'wide',
    ec_oc_scatter: 'wide',
    crustal_boxplot: 'wide',
    ion_timeseries: 'wide',

    // 地图类型 -> 地图模式
    map: 'map',
    trajectory_map: 'map',
    upwind_enterprise_map: 'map',
    upwind_map: 'map',

    // 图片类型 -> 保持原样
    image: 'original',
    trajectory_image: 'original',
    noaa_trajectory: 'original',
  },

  // 滑动轴组件名称
  dataZoomComponent: 'dataZoom',

  // 等待渲染超时
  waitRenderTimeout: 15000,
}

/**
 * 导出默认配置
 */
export default screenshotConfig
