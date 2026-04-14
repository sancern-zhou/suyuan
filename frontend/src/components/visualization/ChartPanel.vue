<template>
  <div class="chart-panel" :style="{ height: dynamicHeight }">
    <div v-if="!hasValidData" class="chart-empty">
      <p>暂无图表数据</p>
      <p v-if="debugInfo" class="debug-info">{{ debugInfo }}</p>
    </div>
    <div v-else class="chart-scroll" ref="scrollContainer">
      <div
        class="chart-canvas"
        ref="chartContainer"
        :style="{ width: chartWidth }"
        @contextmenu="handleChartContextMenu"
      ></div>
    </div>

    <!-- 自定义右键菜单 -->
    <div
      v-if="contextMenu.visible"
      class="chart-context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
    >
      <div class="context-menu-item" @click="copyImageToClipboard">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
        </svg>
        <span>复制图片</span>
      </div>
      <div class="context-menu-item" @click="saveImageAsPNG">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <span>保存图片</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import 'echarts-gl'  // 引入echarts-gl扩展库以支持3D图表

const props = defineProps({
  data: {
    type: Object,
    required: true
  },
  customHeight: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['ready'])

const chartContainer = ref(null)

// 右键菜单状态
const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  imageData: null
})

// 动态计算图表高度：根据图表类型返回不同高度
const dynamicHeight = computed(() => {
  // 如果外部设置了自定义高度，优先使用
  if (props.customHeight) {
    return props.customHeight
  }

  // 根据图表类型返回不同高度
  const chartType = props.data?.type || 'default'

  const heightMap = {
    'pie': '320px',
    'bar': '450px',  // 增加高度，为极坐标柱状图（污染玫瑰图）预留空间
    'polar_bar': '500px',  // 极坐标柱状图（风玫瑰图）
    'line': '380px',
    'timeseries': '420px',
    'stacked_timeseries': '480px',  // 堆叠时序图（多离子堆叠+PM2.5双Y轴）
    'weather_timeseries': '450px',  // 带风向指针的气象时序图
    'pressure_pbl_timeseries': '400px',  // 气压+边界层高度双Y轴图
    'facet_timeseries': '600px',  // 分面时序图（多污染物×多站点）
    'heatmap': '480px',
    'radar': '420px',
    'wind_rose': '480px',  // 增加高度，为标题、轴名称、图例预留空间
    'profile': '550px',
    'map': '600px',
    'scatter3d': '520px',
    'surface3d': '520px',
    'line3d': '520px',
    'bar3d': '520px',
    'volume3d': '520px',
    'default': '400px'
  }

  return heightMap[chartType] || '400px'
})
const scrollContainer = ref(null)
let chartInstance = null
let resizeObserver = null
let waitingForVisible = false
const chartWidth = ref('100%')

const getChartIdForLog = () => {
  const d = props.data || {}
  return (
    d.id ||
    d.vizId ||
    d.chart_id ||
    d?.payload?.id ||
    d?.payload?.meta?.chart_id ||
    d?.title ||
    'unknown_chart'
  )
}

const isContainerVisible = () => {
  const el = chartContainer.value
  if (!el) return false

  const { clientWidth, clientHeight } = el
  if (clientWidth <= 0 || clientHeight <= 0) {
    return false
  }

  // 检查父容器是否被v-show隐藏
  let parent = el.parentElement
  let depth = 0
  const maxDepth = 5

  while (parent && depth < maxDepth) {
    const style = window.getComputedStyle(parent)
    if (style.display === 'none') {
      return false
    }
    parent = parent.parentElement
    depth++
  }

  return true
}

const logContainerMetrics = (el, label = 'container') => {
  // 调试用，生产环境可忽略
}
const handleWindowResize = () => {
  updateChartWidth()
}

// 检查是否有有效数据（v3.0格式）
const hasValidData = computed(() => {
  if (!props.data) return false

  const chartType = props.data.type
  if (!chartType) return false

  const chartData = props.data.data
  if (!chartData) return false

  return true
})

// 调试信息（v3.0格式）
const debugInfo = computed(() => {
  if (!props.data) return 'data is null'
  const keys = Object.keys(props.data)
  return `类型: ${props.data.type || 'unknown'}, 字段: ${keys.join(', ')}`
})

// 分析时间数据，决定显示格式
const analyzeTimeData = (xData) => {
  if (!xData || xData.length === 0) {
    return { format: 'date', rotate: 0, interval: 'auto', spanDays: 0 }
  }

  // 解析时间数据
  const times = xData.map(t => {
    if (!t) return null
    // 支持多种时间格式
    const str = String(t)
    // 尝试解析 "2025-12-02 14:00" 或 "2025-12-02T14:00:00" 格式
    const date = new Date(str.replace(' ', 'T'))
    return isNaN(date.getTime()) ? null : date
  }).filter(t => t !== null)

  if (times.length < 2) {
    return { format: 'date', rotate: 0, interval: 'auto', spanDays: 0 }
  }

  // 计算时间跨度
  const minTime = Math.min(...times.map(t => t.getTime()))
  const maxTime = Math.max(...times.map(t => t.getTime()))
  const spanMs = maxTime - minTime
  const spanHours = spanMs / (1000 * 60 * 60)
  const spanDays = spanMs / (1000 * 60 * 60 * 24)

  // 检查是否都在同一天
  const firstDate = new Date(minTime).toDateString()
  const lastDate = new Date(maxTime).toDateString()
  const sameDay = firstDate === lastDate

  // 根据数据量和时间跨度决定显示策略
  const dataCount = xData.length
  let format, rotate, interval

  if (sameDay || spanDays < 1) {
    // 同一天内的数据：只显示时间 (HH:mm)
    format = 'time'
    rotate = dataCount > 24 ? 45 : 0
    interval = dataCount > 48 ? Math.floor(dataCount / 12) - 1 : 'auto'
  } else if (spanDays <= 3) {
    // 1-3天：显示日期+时间 (MM-DD HH:mm)，间隔显示
    format = 'datetime'
    rotate = 45
    interval = Math.max(Math.floor(dataCount / 8) - 1, 0)
  } else if (spanDays <= 7) {
    // 3-7天：显示日期+时间，更大间隔
    format = 'datetime'
    rotate = 45
    interval = Math.max(Math.floor(dataCount / 6) - 1, 0)
  } else {
    // 超过7天：只显示日期 (MM-DD)
    format = 'date'
    rotate = dataCount > 14 ? 45 : 0
    interval = dataCount > 30 ? Math.floor(dataCount / 10) - 1 : 'auto'
  }

  return { format, rotate, interval, spanDays, sameDay, dataCount }
}

// 根据分析结果格式化时间标签
const formatTimeLabel = (value, analysis, index) => {
  if (!value) return ''
  
  const str = String(value)
  
  // 尝试提取日期和时间部分
  let datePart = ''
  let timePart = ''
  
  if (str.includes(' ')) {
    // "2025-12-02 14:00:00" 格式
    const parts = str.split(' ')
    datePart = parts[0] || ''
    timePart = parts[1] || ''
  } else if (str.includes('T')) {
    // "2025-12-02T14:00:00" ISO格式
    const parts = str.split('T')
    datePart = parts[0] || ''
    timePart = parts[1] || ''
  } else {
    // 纯日期
    datePart = str
  }
  
  // 简化日期格式 (去掉年份)
  if (datePart && datePart.includes('-')) {
    const dateParts = datePart.split('-')
    if (dateParts.length === 3) {
      datePart = `${dateParts[1]}-${dateParts[2]}`  // MM-DD
    }
  }
  
  // 简化时间格式 (只保留小时:分钟)
  if (timePart && timePart.includes(':')) {
    const timeParts = timePart.split(':')
    timePart = `${timeParts[0]}:${timeParts[1]}`  // HH:mm
  }
  
  switch (analysis.format) {
    case 'time':
      // 同一天：只显示时间
      return timePart || datePart
    case 'datetime':
      // 多天但需要精确：显示日期+时间
      return timePart ? `${datePart}\n${timePart}` : datePart
    case 'date':
    default:
      // 长跨度：只显示日期
      return datePart
  }
}

/**
 * 检测并优化完整 ECharts 配置格式
 * 用于识别 execute_python 工具返回的完整 ECharts 配置
 * @param {Object} chartData - 图表数据
 * @param {string} chartType - 图表类型（用于特殊检测）
 * @returns {Object|null} 优化后的配置或 null（非完整格式）
 */
const detectAndOptimizeEChartsConfig = (chartData, chartType = null) => {
  if (!chartData || typeof chartData !== 'object') {
    return null
  }

  console.log('[detectAndOptimizeEChartsConfig] chartType:', chartType, 'has polar:', 'polar' in chartData)

  // 特殊图表类型检测 - 检测是否为完整配置
  let isCompleteConfig = false
  if (chartType) {
    if (chartType === 'pie' && 'title' in chartData && 'series' in chartData) {
      isCompleteConfig = true
    }

    if (chartType === 'radar' && 'radar' in chartData && 'series' in chartData) {
      isCompleteConfig = true
    }

    if (chartType === 'scatter' && 'series' in chartData) {
      isCompleteConfig = true
    }

    if (chartType.includes('3d') &&
        ('grid3D' in chartData ||
         ('xAxis3D' in chartData && 'yAxis3D' in chartData && 'zAxis3D' in chartData))) {
      isCompleteConfig = true
    }

    // bar 类型的极坐标图表（污染玫瑰图）
    if (chartType === 'bar' && 'polar' in chartData && 'series' in chartData) {
      isCompleteConfig = true
    }

    // polar_bar 类型的极坐标图表（风玫瑰图）
    if (chartType === 'polar_bar' && 'polar' in chartData && 'series' in chartData) {
      isCompleteConfig = true
    }
  }

  // 极坐标图表检测
  if ('polar' in chartData && 'angleAxis' in chartData && 'radiusAxis' in chartData && 'series' in chartData) {
    isCompleteConfig = true
  }

  // 如果是完整配置，返回它（会在 buildOption 最后通过 optimizeChartLayout 统一优化）
  if (isCompleteConfig) {
    console.log('[detectAndOptimizeEChartsConfig] 识别为完整配置')
    return chartData
  }

  // 标准图表检测
  if (!('xAxis' in chartData) || !('yAxis' in chartData) || !('series' in chartData)) {
    return null
  }

  // 优化配置
  const optimized = { ...chartData }

  // 优化 yAxis.name 显示
  if (optimized.yAxis?.name) {
    optimized.yAxis = {
      ...optimized.yAxis,
      nameTextStyle: {
        fontSize: 12,
        overflow: 'none',
        breakAll: false
      },
      nameGap: optimized.yAxis.nameGap || 35,
      nameLocation: optimized.yAxis.nameLocation || 'middle'
    }
  }

  // 优化 grid.left
  if (optimized.grid) {
    const currentLeft = optimized.grid.left || '3%'
    if (typeof currentLeft === 'string' && currentLeft.includes('%')) {
      const leftValue = parseInt(currentLeft)
      if (leftValue > 6) {
        optimized.grid = {
          ...optimized.grid,
          left: '6%'
        }
      }
    }
  }

  return optimized
}

/**
 * 统一优化图表布局
 * 确保标题、图例、图表内容之间有合适的间距
 * @param {Object} option - ECharts 配置
 * @returns {Object} 优化后的配置
 */
const optimizeChartLayout = (option) => {
  const optimized = { ...option }

  console.log('[optimizeChartLayout] 开始优化，图表类型:', option.series?.[0]?.type || 'unknown', '有极坐标:', !!option.polar)

  // 标题高度估算（包含 padding）- 增加间距
  const TITLE_HEIGHT = 50
  const LEGEND_HEIGHT = 35
  const TITLE_PADDING = 20

  // 优化标题位置：确保标题与图表内容有间距
  if (optimized.title) {
    // 强制设置标题 top 值，覆盖原有设置
    optimized.title = {
      ...optimized.title,
      top: 15,  // 容器变大后，可以稍微增加
      textStyle: {
        ...(optimized.title.textStyle || {}),
        fontSize: 15  // 恢复正常字体
      }
    }
  }

  // 优化图例位置：确保图例不与标题重叠
  if (optimized.legend) {
    const legend = optimized.legend

    // 如果图例在顶部，强制调整位置
    if (legend.top && typeof legend.top === 'string' && legend.top.includes('%')) {
      const topValue = parseInt(legend.top)
      if (topValue < 15) {
        // 图例位置太靠上，容易与标题重叠
        optimized.legend = {
          ...legend,
          top: '18%'
        }
      }
    } else if (legend.top && typeof legend.top === 'number' && legend.top < 60) {
      // 图例位置数值太小，调整到 65
      optimized.legend = {
        ...legend,
        top: 65
      }
    }
    // 如果图例在底部，确保有足够空间
    else if (legend.bottom) {
      // 强制设置底部图例位置
      optimized.legend = {
        ...legend,
        bottom: '15%'  // 容器变大后，使用百分比更合适
      }
    }
    // 如果图例没有设置位置，默认放底部
    else if (!legend.top && !legend.bottom && !legend.left && !legend.right) {
      optimized.legend = {
        ...legend,
        bottom: '15%'
      }
    }
  }

  // 优化 grid 位置：为标题和图例预留空间
  if (optimized.grid) {
    const grid = optimized.grid
    const minTop = TITLE_HEIGHT + TITLE_PADDING

    // 强制调整 grid.top
    if (typeof grid.top === 'string' && grid.top.includes('%')) {
      const topValue = parseInt(grid.top)
      if (topValue < 15) {
        optimized.grid = {
          ...grid,
          top: '18%'
        }
      }
    } else {
      // 强制设置数值
      optimized.grid = {
        ...grid,
        top: minTop
      }
    }
  }

  // 优化极坐标图表：调整中心位置和半径
  if (optimized.polar) {
    // 强制设置 polar 半径，为轴名称预留空间
    optimized.polar = {
      ...optimized.polar,
      radius: '50%'  // 容器变大后，可以稍微增加半径
    }

    // 优化 radiusAxis 名称显示
    if (optimized.radiusAxis) {
      optimized.radiusAxis = {
        ...optimized.radiusAxis,
        nameTextStyle: {
          ...(optimized.radiusAxis.nameTextStyle || {}),
          fontSize: 11,
          padding: [0, 0, 8, 0]  // 下边距
        },
        nameGap: 10  // 轴名称与轴线的距离
      }
    }

    // 优化 angleAxis 标签显示
    if (optimized.angleAxis) {
      optimized.angleAxis = {
        ...optimized.angleAxis,
        axisLabel: {
          ...(optimized.angleAxis.axisLabel || {}),
          fontSize: 10,
          margin: 5
        }
      }
    }
  }

  // 优化饼图：调整中心位置为标题留出空间
  if (optimized.series && Array.isArray(optimized.series)) {
    for (const serie of optimized.series) {
      if (serie.type === 'pie' && serie.center) {
        const [x, y] = serie.center
        // 强制调整中心位置向下
        if (typeof y === 'string' && y.includes('%')) {
          serie.center = [x, '65%']
        } else {
          serie.center = [x, '65%']
        }
      }
    }
  }

  // 优化雷达图：调整中心位置为标题留出空间
  if (optimized.radar && optimized.radar.center) {
    const [x, y] = optimized.radar.center
    // 强制调整中心位置向下
    if (typeof y === 'string' && y.includes('%')) {
      optimized.radar.center = [x, '65%']
    } else {
      optimized.radar.center = [x, '65%']
    }
  }

  return optimized
}

// 构建ECharts配置（v3.0格式）
const buildOption = () => {
  try {
    if (!hasValidData.value) {
      return {}
    }

    const chartType = (props.data.type || '').toLowerCase()
    const title = props.data.title || ''
    const meta = props.data.meta || {}
    const chartData = props.data.data

    let actualData = chartData
    if (typeof chartData === 'object' && chartData.type) {
      actualData = chartData.data
    }

    let option = {}
    switch (chartType) {
      case 'pie':
        option = buildPieOption(actualData, title, meta)
        break
      case 'bar':
        // 检查是否为完整的 ECharts 配置（如污染玫瑰图）
        const barOptimized = detectAndOptimizeEChartsConfig(actualData, 'bar')
        if (barOptimized) {
          option = barOptimized
        } else {
          option = buildBarOption(actualData, title, meta)
        }
        break
      case 'polar_bar':
        // 极坐标柱状图（风玫瑰图），通常是完整的 ECharts 配置
        const polarBarOptimized = detectAndOptimizeEChartsConfig(actualData, 'polar_bar')
        if (polarBarOptimized) {
          option = polarBarOptimized
        } else {
          option = buildBarOption(actualData, title, meta)
        }
        break
      case 'line':
      case 'timeseries':
        option = buildLineOption(actualData, title, meta)
        break
      case 'radar':
        option = buildRadarOption(actualData, title, meta)
        break
      case 'heatmap':
        option = buildHeatmapOption(actualData, title, meta)
        break
      case 'wind_rose':
        option = buildWindRoseOption(actualData, title, meta)
        break
      case 'weather_timeseries':
        option = buildWeatherTimeseriesOption(actualData, title, meta)
        break
      case 'pressure_pbl_timeseries':
        option = buildPressurePblOption(actualData, title, meta)
        break
      case 'stacked_timeseries':
        option = buildStackedTimeseriesOption(actualData, title, meta)
        break
      case 'scatter':
        const scatterOptimized = detectAndOptimizeEChartsConfig(actualData, 'scatter')
        if (scatterOptimized) {
          option = scatterOptimized
        } else {
          option = buildGenericOption(actualData, title, meta)
        }
        break
      case 'scatter3d':
        option = buildScatter3dOption(actualData, title, meta)
        break
      case 'surface3d':
        option = buildSurface3dOption(actualData, title, meta)
        break
      case 'line3d':
        option = buildLine3dOption(actualData, title, meta)
        break
      case 'bar3d':
        option = buildBar3dOption(actualData, title, meta)
        break
      case 'volume3d':
        option = buildVolume3dOption(actualData, title, meta)
        break
      case 'profile':
        option = buildProfileOption(actualData, title, meta)
        break
      case 'facet_timeseries':
        option = buildFacetTimeseriesOption(actualData, title, meta)
        break
      default:
        const hasTimeseriesFormat = actualData &&
          actualData.x && actualData.series &&
          Array.isArray(actualData.x) && Array.isArray(actualData.series)
        const hasLineFormat = actualData &&
          actualData.x && actualData.y &&
          Array.isArray(actualData.x) && Array.isArray(actualData.y)

        if (hasTimeseriesFormat || hasLineFormat) {
          option = buildLineOption(actualData, title, meta)
        } else {
          option = buildGenericOption(actualData, title, meta)
        }
    }

    if (!option || Object.keys(option).length === 0) {
      return {}
    }

    // 统一优化图表配置：标题和图例间距
    const optimized = optimizeChartLayout(option)
    console.log('[ChartPanel] 优化后的标题位置:', optimized.title?.top)
    console.log('[ChartPanel] 优化后的图例位置:', optimized.legend?.top || optimized.legend?.bottom)
    if (optimized.polar) {
      console.log('[ChartPanel] 极坐标半径:', optimized.polar?.radius)
    }
    if (optimized.radiusAxis?.name) {
      console.log('[ChartPanel] radiusAxis名称:', optimized.radiusAxis.name)
    }
    return optimized
  } catch (error) {
    console.error('[ChartPanel] buildOption 错误:', error)
    return {}
  }
}


/**
 * 创建统一的 toolbox 配置
 * @param {string} chartName - 图表名称，用于保存图片时的文件名
 * @returns {Object} ECharts toolbox 配置
 */
const createToolboxConfig = (chartName = '图表') => {
  return {
    show: true,
    right: 20,
    top: 10,
    feature: {
      saveAsImage: {
        show: true,
        title: '保存为图片',
        type: 'png',
        pixelRatio: 2,
        name: chartName
      },
      dataView: { show: false },
      restore: { show: false },
      dataZoom: { show: false },
      magicType: { show: false }
    }
  }
}

// 饼图
const buildPieOption = (payload, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(payload, 'pie')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const data = Array.isArray(payload) ? payload : []

  return {
    title: {
      text: title,
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', left: 'left', top: '10%' },
    toolbox: createToolboxConfig(title || '饼图'),
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '60%'],
      data,
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      },
      label: { show: true, position: 'outside', formatter: '{b}: {d}%' }
    }]
  }
}

// 柱状图（v3.0格式）
const buildBarOption = (chartData, title, meta) => {
  // 支持两种格式：
  // 1. 单序列: { x: [...], y: [...] }
  // 2. 多序列: { x: [...], series: [{name, data}, ...] }
  // 3. 完整 ECharts 配置格式（包含 xAxis、yAxis、series）

  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'bar')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const xData = chartData.x || []
  const yData = chartData.y || []
  const series = chartData.series || []

  let chartSeries = []
  let hasLegend = false

  if (series && series.length > 0) {
    // 多序列格式：series: [{name, data}, ...]
    hasLegend = true
    chartSeries = series.map((s, index) => ({
      name: s.name,
      type: 'bar',
      data: s.data,
      itemStyle: {
        color: ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272'][index % 6]
      },
      emphasis: { itemStyle: { color: '#91cc75' } }
    }))
  } else if (yData && yData.length > 0) {
    // 单序列格式：y: [...]
    hasLegend = false
    chartSeries = [{
      name: title || '数据',
      type: 'bar',
      data: yData,
      itemStyle: { color: '#5470c6' },
      emphasis: { itemStyle: { color: '#91cc75' } }
    }]
  }

  // 如果是多序列，需要图例，同时让出更多顶部空间，避免挤压标题
  const legend = hasLegend
    ? { data: series.map(s => s.name), top: 55 }
    : { show: false }
  const gridTop = hasLegend ? 100 : 60

  return {
    title: {
      text: title,
      left: 'center',
      top: 10,
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend,
    toolbox: createToolboxConfig(title || '柱状图'),
    grid: { top: gridTop, left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: { rotate: xData.length > 10 ? 45 : 0, fontSize: 12 }
    },
    yAxis: { type: 'value', name: meta.unit || '' },
    series: chartSeries
  }
}

// 预处理函数：合并 O3 和 O3_8h 数据（支持两种格式）
// 格式1: { x: [...], series: [...] } - 已处理好的多系列数据
// 格式2: [{timestamp, O3, O3_8h, ...}, ...] - 原始记录列表，需要合并
const preprocessO3DualData = (chartData) => {
  // 如果已经是标准格式，直接返回
  if (chartData.x && chartData.series) {
    return chartData
  }

  // 如果是原始记录列表格式，需要合并
  if (Array.isArray(chartData) && chartData.length > 0) {
    const firstItem = chartData[0]

    // 检查是否是原始记录格式（包含时间戳字段的对象）
    const hasTimestamp = firstItem.timestamp || firstItem.timePoint || firstItem.TimePoint
    const hasO3 = 'O3' in firstItem || 'o3' in firstItem
    const hasO3_8h = 'O3_8h' in firstItem

    if (hasTimestamp && (hasO3 || hasO3_8h)) {
      // 按时间戳分组合并
      const timeMap = new Map()

      chartData.forEach(record => {
        // 获取时间戳
        const timestamp = record.timestamp || record.timePoint || record.TimePoint
        if (!timestamp) return

        if (!timeMap.has(timestamp)) {
          timeMap.set(timestamp, {
            timestamp,
            o3Values: [],
            o3_8hValues: []
          })
        }

        const entry = timeMap.get(timestamp)

        // 收集O3值
        if ('O3' in record && record.O3 !== null && record.O3 !== undefined) {
          entry.o3Values.push(record.O3)
        } else if ('o3' in record && record.o3 !== null && record.o3 !== undefined) {
          entry.o3Values.push(record.o3)
        }

        // 收集O3_8h值
        if ('O3_8h' in record && record.O3_8h !== null && record.O3_8h !== undefined) {
          entry.o3_8hValues.push(record.O3_8h)
        }
      })

      // 构建合并后的数据
      const xData = []
      const o3Series = []
      const o3_8hSeries = []

      // 按时间排序
      const sortedTimes = Array.from(timeMap.keys()).sort((a, b) => {
        const dateA = new Date(a.replace(' ', 'T'))
        const dateB = new Date(b.replace(' ', 'T'))
        return dateA - dateB
      })

      sortedTimes.forEach(timestamp => {
        const entry = timeMap.get(timestamp)
        xData.push(timestamp)

        // 取平均值或第一个有效值
        o3Series.push(entry.o3Values.length > 0
          ? (entry.o3Values.reduce((a, b) => a + b, 0) / entry.o3Values.length)
          : null)
        o3_8hSeries.push(entry.o3_8hValues.length > 0
          ? (entry.o3_8hValues.reduce((a, b) => a + b, 0) / entry.o3_8hValues.length)
          : null)
      })

      // 构建多系列格式
      const series = []
      if (o3Series.some(v => v !== null)) {
        series.push({ name: 'O3(小时)', data: o3Series })
      }
      if (o3_8hSeries.some(v => v !== null)) {
        series.push({ name: 'O3_8h(8H平均)', data: o3_8hSeries })
      }

      return { x: xData, series }
    }
  }

  return chartData
}

// 线图/时序图（v3.0格式）
const buildLineOption = (chartData, title, meta) => {
  // v3.0格式：chartData = { x: [...], series: [{name, data}, ...] } 或 { x: [...], y: [...] }
  // 也支持原始记录列表格式（包含 O3 和 O3_8h 字段）
  // 也支持 series[].data 为 [{time, value}] 对象数组格式（Agent生成）
  // 也支持完整 ECharts 配置格式（包含 xAxis、yAxis、series）

  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'line')
  if (optimizedConfig) {
    return optimizedConfig
  }

  // 预处理：合并 O3 和 O3_8h 数据
  const processedData = preprocessO3DualData(chartData)

  let xData = processedData.x || []
  let series = processedData.series || []
  const yData = processedData.y || []

  // 兼容 series[].data 为 [{time, value}] 对象数组格式 或 [[time, value]] 数组格式
  if (series.length > 0 && xData.length === 0) {
    const firstData = series[0]?.data
    if (firstData?.length > 0) {
      const first = firstData[0]
      if (Array.isArray(first) && first.length >= 2) {
        xData = firstData.map(d => d[0])
        series = series.map(s => ({
          ...s,
          data: s.data.map(d => (Array.isArray(d) ? d[1] : d) ?? null)
        }))
      } else if (typeof first === 'object' && first !== null && 'time' in first) {
        xData = firstData.map(d => d.time)
        series = series.map(s => ({
          ...s,
          data: s.data.map(d => d.value ?? null)
        }))
      }
    }
  }

  let chartSeries = []
  let hasLegend = false

  if (series && series.length > 0) {
    // 多序列格式：series: [{name, data}, ...]
    hasLegend = true
    chartSeries = series.map((s, index) => ({
      name: s.name,
      type: 'line',
      data: s.data,
      smooth: true,
      showSymbol: false,
      emphasis: { focus: 'series' },
      itemStyle: {
        color: ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272'][index % 6]
      },
      lineStyle: { width: 1 }
    }))
  } else if (yData && yData.length > 0) {
    // 单序列格式：y: [...]
    hasLegend = false
    chartSeries = [{
      name: title || '数据',
      type: 'line',
      data: yData,
      smooth: true,
      showSymbol: false,
      emphasis: { focus: 'series' },
      itemStyle: { color: '#5470c6' },
      lineStyle: { width: 1 }
    }]
  }

  const legendTop = hasLegend ? 55 : 0
  const gridTop = hasLegend ? 100 : 60

  // 智能分析时间数据，决定显示格式
  const timeAnalysis = analyzeTimeData(xData)

  // 智能判断是否需要 Y 轴自动缩放（不从 0 开始）
  // 气压(hPa)、边界层高度(m)、温度等数据需要自动缩放以显示波动
  const unit = meta.unit || ''
  const titleLower = (title || '').toLowerCase()
  const needsScale = (
    unit === 'hPa' ||                                    // 气压
    titleLower.includes('气压') ||
    titleLower.includes('pressure') ||
    titleLower.includes('边界层') ||
    titleLower.includes('boundary') ||
    titleLower.includes('pbl') ||
    (series.length === 1 && series[0]?.name?.includes('气压')) ||
    (series.length === 1 && series[0]?.name?.includes('边界层'))
  )

  // 智能dataZoom：数据点超过20个时显示缩放滑块
  const needsDataZoom = xData.length > 20
  const dataZoomConfig = needsDataZoom ? [
    {
      type: 'slider',
      show: true,
      start: 0,   // 默认显示完整图表
      end: 100,
      height: 24,
      bottom: 5,
      borderColor: '#ddd',
      fillerColor: 'rgba(25, 118, 210, 0.15)',
      handleStyle: { color: '#1976d2' },
      textStyle: { fontSize: 10 },
      brushSelect: false
    },
    {
      type: 'inside',
      start: 0,   // 默认显示完整图表
      end: 100,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true
    }
  ] : []

  // 有dataZoom时需要更多底部空间
  const gridBottom = needsDataZoom ? '18%' : '10%'

  return {
    title: {
      text: title,
      left: 'center',
      top: 10,
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: { trigger: 'axis' },
    legend: hasLegend ? { data: series.map(s => s.name), top: legendTop } : { show: false },
    toolbox: createToolboxConfig(title || '折线图'),
    grid: { top: gridTop, left: '3%', right: '4%', bottom: gridBottom, containLabel: true },
    xAxis: {
      type: 'category',
      data: xData,
      boundaryGap: false,
      axisLabel: {
        rotate: timeAnalysis.rotate,
        fontSize: 10,
        interval: timeAnalysis.interval,
        formatter: function(value, index) {
          return formatTimeLabel(value, timeAnalysis, index)
        }
      }
    },
    yAxis: {
      type: 'value',
      name: meta.unit || '',
      scale: needsScale,
      min: needsScale ? 'dataMin' : undefined,
      max: needsScale ? 'dataMax' : undefined
    },
    dataZoom: dataZoomConfig,
    series: chartSeries
  }
}

// 雷达图（v3.0格式）
const buildRadarOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'radar')
  if (optimizedConfig) {
    return optimizedConfig
  }

  // 支持两种格式：
  // 1. 旧格式（单站点）: { x: [...], y: [...] }
  // 2. 新格式（多站点）: { indicator: [...], series: [...] }

  let indicators = []
  let seriesData = []

  if (chartData.indicator && chartData.series) {
    // 新格式：多站点雷达图
    indicators = chartData.indicator || []
    seriesData = chartData.series || []
  } else if (chartData.x && chartData.y) {
    // 旧格式：单站点雷达图（兼容）
    const indicatorNames = chartData.x || []
    const values = chartData.y || []

    indicators = indicatorNames.map(name => ({
      name: name,
      max: 100
    }))

    seriesData = [{
      value: values,
      name: title || '控制效果',
      itemStyle: { color: '#5470c6' }
    }]
  }

  return {
    title: {
      text: title,
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      trigger: 'item',
      formatter: function(params) {
        if (params.value) {
          let result = `${params.name}<br/>`
          params.value.forEach((val, idx) => {
            if (indicators[idx]) {
              result += `${indicators[idx].name}: ${val.toFixed(2)}%<br/>`
            }
          })
          return result
        }
        return params.name
      }
    },
    legend: {
      data: seriesData.map(s => s.name),
      top: '10%',
      show: seriesData.length > 1
    },
    toolbox: createToolboxConfig(title || '雷达图'),
    radar: {
      indicator: indicators,
      center: ['50%', '60%'],
      radius: '60%',
      splitNumber: 4,
      name: {
        textStyle: {
          fontSize: 12
        }
      }
    },
    series: [{
      name: title || '空气质量综合评估',
      type: 'radar',
      data: seriesData,
      emphasis: {
        lineStyle: {
          width: 1
        }
      }
    }]
  }
}

// 热力图（v3.0格式）
const buildHeatmapOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'heatmap')
  if (optimizedConfig) {
    return optimizedConfig
  }

  // v3.0格式：chartData = { xAxis: [...], yAxis: [...], data: [[x, y, value], ...] }
  const xAxisData = chartData.xAxis || []
  const yAxisData = chartData.yAxis || []
  const heatmapData = chartData.data || []

  // 计算数值范围用于视觉映射
  let minValue = Infinity
  let maxValue = -Infinity

  heatmapData.forEach(item => {
    const value = item[2]
    if (value < minValue) minValue = value
    if (value > maxValue) maxValue = value
  })

  // 转换数据格式为 ECharts 热力图需要的格式
  const formattedData = heatmapData.map(item => [item[0], item[1], item[2] || 0])

  return {
    title: {
      text: title,
      left: 'center',
      top: 10,
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      position: 'top',
      formatter: function(params) {
        const xLabel = xAxisData[params.data[0]] || params.data[0]
        const yLabel = yAxisData[params.data[1]] || params.data[1]
        const value = params.data[2]
        return `${xLabel}<br/>${yLabel}: ${value} ${meta.unit || ''}`
      }
    },
    grid: {
      top: 60,
      left: '10%',
      right: '10%',
      bottom: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: xAxisData,
      splitArea: {
        show: true
      },
      axisLabel: {
        rotate: xAxisData.length > 10 ? 45 : 0,
        fontSize: 12
      }
    },
    yAxis: {
      type: 'category',
      data: yAxisData,
      splitArea: {
        show: true
      },
      axisLabel: {
        fontSize: 12
      }
    },
    visualMap: {
      min: minValue,
      max: maxValue,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '0%',
      inRange: {
        color: ['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#ffffbf', '#fee090', '#fdae61', '#f46d43', '#d73027', '#a50026']
      },
      text: ['高', '低'],
      textStyle: {
        fontSize: 12
      }
    },
    toolbox: createToolboxConfig(title || '热力图'),
    series: [{
      name: title || '浓度',
      type: 'heatmap',
      data: formattedData,
      label: {
        show: true,
        fontSize: 10,
        formatter: function(params) {
          return params.data[2].toFixed(1)
        }
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      }
    }]
  }
}

// 通用配置（v3.0格式）
const buildGenericOption = (chartData, title, meta) => {
  // 检测完整ECharts配置（包括3D图表和极坐标图表）
  if (chartData && typeof chartData === 'object') {
    // 3D图表检测：包含 grid3D 或 xAxis3D/yAxis3D/zAxis3D
    if ('grid3D' in chartData ||
        ('xAxis3D' in chartData && 'yAxis3D' in chartData && 'zAxis3D' in chartData) ||
        'xAxis3D' in chartData) {
      console.log('[ChartPanel] buildGenericOption 检测到完整3D图表配置，直接返回')
      return chartData
    }

    // 极坐标图表检测：包含 polar、angleAxis、radiusAxis、series
    if ('polar' in chartData && 'angleAxis' in chartData && 'radiusAxis' in chartData && 'series' in chartData) {
      console.log('[ChartPanel] buildGenericOption 检测到完整极坐标图表配置，直接返回')
      return chartData
    }

    // 雷达图检测：包含 radar、series
    if ('radar' in chartData && 'series' in chartData) {
      console.log('[ChartPanel] buildGenericOption 检测到完整雷达图配置，直接返回')
      return chartData
    }

    // 标准图表检测：包含 xAxis、yAxis、series
    if ('xAxis' in chartData && 'yAxis' in chartData && 'series' in chartData) {
      console.log('[ChartPanel] buildGenericOption 检测到完整ECharts配置，直接返回')
      return chartData
    }

    // 通用 series 检测：任何包含有效 series 的配置
    if ('series' in chartData && Array.isArray(chartData.series) && chartData.series.length > 0) {
      console.log('[ChartPanel] buildGenericOption 检测到包含 series 的配置，直接返回')
      return chartData
    }
  }

  // 默认返回空配置
  console.warn('[ChartPanel] buildGenericOption 无法识别图表格式，返回默认配置')
  return {
    title: { text: title || '图表', left: 'center' },
    tooltip: {},
    xAxis: { type: 'category', data: [] },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: [] }]
  }
}

// 风向玫瑰图（v3.0格式）
const buildWindRoseOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'wind_rose')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const sectors = chartData.sectors || []
  const legend = chartData.legend || {}

  return {
    title: {
      text: title || '风向玫瑰图',
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      trigger: 'item',
      formatter: function(params) {
        const data = params.data
        if (data && data.avg_speed !== undefined) {
          return `${data.direction}: ${data.count}次<br/>平均风速: ${data.avg_speed} m/s`
        }
        return params.name
      }
    },
    legend: {
      data: sectors.map(s => legend[s.direction] || s.direction),
      top: '10%'
    },
    toolbox: createToolboxConfig(title || '风向玫瑰图'),
    series: [{
      name: '风速分布',
      type: 'pie',
      radius: ['15%', '80%'],
      center: ['50%', '60%'],
      roseType: 'area',
      data: sectors.map(s => ({
        name: legend[s.direction] || s.direction,
        value: s.avg_speed,
        count: s.count,
        avg_speed: s.avg_speed
      })),
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      }
    }]
  }
}

// 带风向指针的气象时序图（v3.2新增）
const buildWeatherTimeseriesOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'weather_timeseries')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const xData = chartData.x || []
  const series = chartData.series || []
  const windStats = chartData.wind_statistics || {}
  
  // 分离风速数据和其他气象要素
  const windSeries = series.find(s => s.type === 'wind')
  const otherSeries = series.filter(s => s.type !== 'wind')
  
  // 颜色方案
  const colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272']
  
  // 构建ECharts系列
  const chartSeries = []
  
  // 风速系列（带风向箭头标记）
  if (windSeries) {
    const windData = windSeries.data || []
    
    // 风速曲线
    chartSeries.push({
      name: '风速',
      type: 'line',
      yAxisIndex: 0,
      data: windData.map(d => d.value),
      smooth: true,
      showSymbol: true,
      symbol: 'circle',
      symbolSize: 6,
      itemStyle: { color: '#5470c6' },
      lineStyle: { width: 1 },
      emphasis: { focus: 'series' }
    })
    
    // 风向箭头标记（每隔几个点显示一个）
    const arrowInterval = Math.max(1, Math.floor(windData.length / 20))  // 最多显示20个箭头
    const markPoints = []
    
    windData.forEach((d, idx) => {
      if (idx % arrowInterval === 0 && d.direction !== undefined) {
        // 风向箭头：从风来的方向指向中心
        // 气象学风向是风来的方向，箭头应该指向风去的方向（加180度）
        const arrowAngle = (d.direction + 180) % 360
        markPoints.push({
          coord: [xData[idx], d.value],
          symbol: 'arrow',
          symbolSize: [8, 14],
          symbolRotate: arrowAngle - 90,  // ECharts箭头默认朝右，需要调整
          itemStyle: { 
            color: '#1976d2',
            borderColor: '#fff',
            borderWidth: 1
          },
          label: { show: false }
        })
      }
    })
    
    // 添加风向标记系列
    chartSeries.push({
      name: '风向',
      type: 'scatter',
      yAxisIndex: 0,
      data: windData.map((d, idx) => {
        if (idx % arrowInterval === 0) {
          return {
            value: [xData[idx], d.value],
            direction: d.direction,
            symbolRotate: (d.direction + 180) % 360 - 90
          }
        }
        return null
      }).filter(Boolean),
      symbol: 'arrow',
      symbolSize: [8, 14],
      itemStyle: { 
        color: '#1976d2',
        borderColor: '#fff',
        borderWidth: 1
      },
      label: { show: false },
      tooltip: {
        formatter: function(params) {
          const dir = params.data.direction
          const dirNames = {
            0: '北风', 45: '东北风', 90: '东风', 135: '东南风',
            180: '南风', 225: '西南风', 270: '西风', 315: '西北风'
          }
          const nearestDir = Math.round(dir / 45) * 45 % 360
          return `风向: ${dirNames[nearestDir] || dir + '°'}`
        }
      }
    })
  }
  
  // 颜色映射
  const colorMap = {
    '温度': '#ee6666',
    '降水': '#73c0de',
    '湿度': '#91cc75',
    '云量': '#fac858'
  }
  
  // 其他气象要素系列
  otherSeries.forEach((s) => {
    chartSeries.push({
      name: s.name,
      type: 'line',
      yAxisIndex: s.yAxisIndex || 0,
      data: s.data,
      smooth: true,
      showSymbol: false,
      itemStyle: { color: colorMap[s.name] || colors[chartSeries.length % colors.length] },
      lineStyle: { width: 1 },
      emphasis: { focus: 'series' }
    })
  })
  
  // 双Y轴配置
  // 左轴(0): 风速、温度、降水
  // 右轴(1): 湿度、云量 (%)
  const leftAxisItems = ['风速', '温度', '降水'].filter(n => 
    chartSeries.some(s => s.name === n || s.name === '风速')
  )
  const rightAxisItems = otherSeries.filter(s => s.yAxisIndex === 1).map(s => s.name)
  
  const yAxis = [
    {
      type: 'value',
      name: '风速/温度/降水',
      position: 'left',
      axisLine: { show: true, lineStyle: { color: '#5470c6' } },
      axisLabel: { formatter: '{value}' },
      splitLine: { show: true, lineStyle: { type: 'dashed' } }
    },
    {
      type: 'value',
      name: '湿度/云量 (%)',
      position: 'right',
      min: 0,
      max: 100,
      axisLine: { show: true, lineStyle: { color: '#91cc75' } },
      axisLabel: { formatter: '{value}%' },
      splitLine: { show: false }
    }
  ]
  
  // 图例数据
  const legendData = ['风速', '风向', ...otherSeries.map(s => s.name)]
  
  // dataZoom配置
  const needsDataZoom = xData.length > 20
  const dataZoomConfig = needsDataZoom ? [
    {
      type: 'slider',
      show: true,
      start: 0,
      end: 100,
      height: 24,
      bottom: 5,
      borderColor: '#ddd',
      fillerColor: 'rgba(25, 118, 210, 0.15)',
      handleStyle: { color: '#1976d2' },
      textStyle: { fontSize: 10 },
      brushSelect: false
    },
    {
      type: 'inside',
      start: 0,
      end: 100,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true
    }
  ] : []
  
  // 主导风向信息
  const dominantDir = windStats.dominant_direction || ''
  const avgSpeed = windStats.avg_speed || 0
  const subtitleText = dominantDir ? `主导风向: ${dominantDir}  平均风速: ${avgSpeed} m/s` : ''
  
  return {
    title: {
      text: title,
      subtext: subtitleText,
      left: 'center',
      top: 5,
      textStyle: { fontSize: 16, fontWeight: 'bold' },
      subtextStyle: { fontSize: 12, color: '#666' }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: function(params) {
        let result = params[0]?.axisValue + '<br/>'
        params.forEach(p => {
          if (p.seriesName === '风向') return  // 风向单独处理
          result += `${p.marker} ${p.seriesName}: ${p.value}<br/>`
        })
        // 添加风向信息
        const windParam = params.find(p => p.seriesName === '风速')
        if (windParam && windSeries) {
          const idx = windParam.dataIndex
          const wd = windSeries.data[idx]?.direction
          if (wd !== undefined) {
            const dirNames = ['北风', '东北风', '东风', '东南风', '南风', '西南风', '西风', '西北风']
            const dirIdx = Math.round(wd / 45) % 8
            result += `<span style="color:#1976d2">▲</span> 风向: ${dirNames[dirIdx]} (${wd}°)<br/>`
          }
        }
        return result
      }
    },
    legend: {
      data: legendData,
      top: 50,
      selected: {
        '风向': true  // 默认显示风向
      }
    },
    grid: {
      top: 100,
      left: '3%',
      right: '4%',
      bottom: needsDataZoom ? '18%' : '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: {
        rotate: xData.length > 24 ? 45 : 0,
        fontSize: 10
      }
    },
    yAxis: yAxis,
    dataZoom: dataZoomConfig,
    series: chartSeries
  }
}

// 气压+边界层高度双Y轴图
const buildPressurePblOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'pressure_pbl_timeseries')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const xData = chartData.x || []
  const series = chartData.series || []

  // 颜色配置
  const pressureColor = '#5470c6'  // 蓝色 - 气压
  const pblColor = '#ee6666'       // 红色 - 边界层高度

  // 提取气压数据，计算合适的Y轴范围
  const pressureSeries = series.find(s => s.name === '气压')
  let pressureMin = 980, pressureMax = 1040  // 默认范围

  if (pressureSeries && pressureSeries.data) {
    const validData = pressureSeries.data.filter(v => v !== null && v !== undefined)
    if (validData.length > 0) {
      const dataMin = Math.min(...validData)
      const dataMax = Math.max(...validData)
      const range = dataMax - dataMin
      // 扩展5%的边距，确保曲线不贴边
      const padding = Math.max(range * 0.1, 2)  // 至少2 hPa的边距
      pressureMin = Math.floor(dataMin - padding)
      pressureMax = Math.ceil(dataMax + padding)
    }
  }

  // 构建ECharts系列
  const chartSeries = []

  series.forEach(s => {
    const color = s.name === '气压' ? pressureColor : pblColor
    chartSeries.push({
      name: s.name,
      type: 'line',
      yAxisIndex: s.yAxisIndex || 0,
      data: s.data,
      smooth: true,
      showSymbol: false,
      itemStyle: { color },
      lineStyle: { width: 1 },
      emphasis: { focus: 'series' }
    })
  })

  // 双Y轴配置
  const yAxis = [
    {
      type: 'value',
      name: '气压 (hPa)',
      position: 'left',
      min: pressureMin,
      max: pressureMax,
      axisLine: { show: true, lineStyle: { color: pressureColor } },
      axisLabel: { formatter: '{value}' },
      splitLine: { show: true, lineStyle: { type: 'dashed' } }
    },
    {
      type: 'value',
      name: '边界层高度 (m)',
      position: 'right',
      axisLine: { show: true, lineStyle: { color: pblColor } },
      axisLabel: { formatter: '{value}' },
      splitLine: { show: false }
    }
  ]

  // dataZoom配置
  const needsDataZoom = xData.length > 20
  const dataZoomConfig = needsDataZoom ? [
    {
      type: 'slider',
      show: true,
      start: 0,
      end: 100,
      height: 24,
      bottom: 5,
      borderColor: '#ddd',
      fillerColor: 'rgba(25, 118, 210, 0.15)',
      handleStyle: { color: '#1976d2' },
      textStyle: { fontSize: 10 },
      brushSelect: false
    },
    {
      type: 'inside',
      start: 0,
      end: 100,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true
    }
  ] : []

  return {
    title: {
      text: title,
      left: 'center',
      top: 10,
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: function(params) {
        let result = params[0]?.axisValue + '<br/>'
        params.forEach(p => {
          const unit = p.seriesName === '气压' ? ' hPa' : ' m'
          result += `${p.marker} ${p.seriesName}: ${p.value}${unit}<br/>`
        })
        return result
      }
    },
    legend: {
      data: series.map(s => s.name),
      top: 40
    },
    grid: {
      top: 80,
      left: '3%',
      right: '4%',
      bottom: needsDataZoom ? '18%' : '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: {
        rotate: xData.length > 24 ? 45 : 0,
        fontSize: 10
      }
    },
    yAxis: yAxis,
    dataZoom: dataZoomConfig,
    series: chartSeries
  }
}

// 堆叠时序图（颗粒物离子堆叠+PM2.5双Y轴）
const buildStackedTimeseriesOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'stacked_timeseries')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const xData = chartData.x || []
  const series = chartData.series || []
  const yAxisConfig = chartData.yAxis || []
  const legendData = chartData.legend?.data || series.map(s => s.name)

  // 分离堆叠系列（使用stack属性）和PM2.5系列（右Y轴）
  const stackedSeries = series.filter(s => s.stack === 'total' || s.stack === 'stack')
  const pm25Series = series.filter(s => s.name === 'PM2.5' || s.yAxisIndex === 1)

  // 构建ECharts系列
  const chartSeries = []

  // 堆叠系列（使用传入的配置）
  stackedSeries.forEach((s, index) => {
    chartSeries.push({
      name: s.name,
      type: 'line',
      data: s.data,
      stack: s.stack || 'total',
      areaStyle: s.areaStyle || {},
      smooth: s.smooth !== false,
      showSymbol: false,
      itemStyle: s.itemStyle || {
        color: ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#ff9f7f', '#3ba272'][index % 8]
      },
      lineStyle: { width: 1 },
      emphasis: { focus: 'series' },
      yAxisIndex: 0  // 堆叠系列使用左Y轴
    })
  })

  // PM2.5系列（使用右Y轴）
  pm25Series.forEach(s => {
    chartSeries.push({
      name: s.name,
      type: 'line',
      data: s.data,
      smooth: s.smooth !== false,
      showSymbol: s.symbol !== false,
      symbol: s.symbol || 'circle',
      symbolSize: s.symbolSize || 8,
      itemStyle: s.itemStyle || { color: '#E74C3C' },
      lineStyle: s.lineStyle || { width: 3 },
      emphasis: { focus: 'series' },
      yAxisIndex: 1  // PM2.5使用右Y轴
    })
  })

  // 双Y轴配置
  const yAxis = [
    {
      type: 'value',
      name: '离子浓度 (μg/m³)',
      position: 'left',
      axisLine: { show: true, lineStyle: { color: '#5470c6' } },
      axisLabel: { formatter: '{value}', color: '#5470c6' },
      splitLine: { show: true, lineStyle: { type: 'dashed' } }
    },
    {
      type: 'value',
      name: 'PM2.5 (μg/m³)',
      position: 'right',
      offset: 0,
      axisLine: { show: true, lineStyle: { color: '#E74C3C' } },
      axisLabel: { formatter: '{value}', color: '#E74C3C' },
      splitLine: { show: false }
    }
  ]

  // dataZoom配置
  const needsDataZoom = xData.length > 20
  const dataZoomConfig = needsDataZoom ? [
    {
      type: 'slider',
      show: true,
      start: 0,
      end: 100,
      height: 24,
      bottom: 5,
      borderColor: '#ddd',
      fillerColor: 'rgba(25, 118, 210, 0.15)',
      handleStyle: { color: '#1976d2' },
      textStyle: { fontSize: 10 },
      brushSelect: false
    },
    {
      type: 'inside',
      start: 0,
      end: 100,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true
    }
  ] : []

  return {
    title: {
      text: title,
      left: 'center',
      top: 10,
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: function(params) {
        let result = params[0]?.axisValue + '<br/>'
        let total = 0
        params.forEach(p => {
          if (p.seriesName !== 'PM2.5') {
            total += (p.value || 0)
            result += `${p.marker} ${p.seriesName}: ${p.value}<br/>`
          }
        })
        // 添加堆叠总和
        if (stackedSeries.length > 0) {
          result += `<strong>堆叠总和: ${total.toFixed(2)} μg/m³</strong><br/>`
        }
        // 添加PM2.5值
        const pm25Param = params.find(p => p.seriesName === 'PM2.5')
        if (pm25Param) {
          result += `${pm25Param.marker} <strong>PM2.5: ${pm25Param.value}</strong><br/>`
        }
        return result
      }
    },
    legend: {
      data: legendData,
      top: 40
    },
    grid: {
      top: 80,
      left: '3%',
      right: '4%',
      bottom: needsDataZoom ? '18%' : '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: xData,
      boundaryGap: false,
      axisLabel: {
        rotate: xData.length > 24 ? 45 : 0,
        fontSize: 10
      }
    },
    yAxis: yAxis,
    dataZoom: dataZoomConfig,
    series: chartSeries
  }
}

// 3D散点图（v3.0格式）
const buildScatter3dOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'scatter3d')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const points = chartData.data?.points || []
  const axisLabels = chartData.data?.axis_labels || {}

  return {
    title: {
      text: title || '3D散点图',
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      formatter: function(params) {
        const data = params.data
        return `X: ${data.x}<br/>Y: ${data.y}<br/>Z: ${data.z}`
      }
    },
    grid3D: {
      boxWidth: 120,
      boxDepth: 120,
      boxHeight: 80,
      environment: 'auto',
      viewControl: {
        autoRotate: false
      },
      light: {
        main: {
          intensity: 1.2,
          shadow: true
        },
        ambient: {
          intensity: 0.3
        }
      }
    },
    xAxis3D: {
      name: axisLabels.x || 'X轴'
    },
    yAxis3D: {
      name: axisLabels.y || 'Y轴'
    },
    zAxis3D: {
      name: axisLabels.z || 'Z轴'
    },
    series: [{
      type: 'scatter3D',
      data: points,
      emphasis: {
        itemStyle: {
          color: '#ee6666'
        }
      }
    }]
  }
}

// 3D曲面图（v3.0格式）
const buildSurface3dOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'surface3d')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const x = chartData.data?.x || []
  const y = chartData.data?.y || []
  const z = chartData.data?.z || []
  const axisLabels = chartData.data?.axis_labels || {}

  return {
    title: {
      text: title || '3D曲面图',
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      formatter: function(params) {
        return `X: ${params.data[0]}<br/>Y: ${params.data[1]}<br/>Z: ${params.data[2]}`
      }
    },
    grid3D: {
      boxWidth: 120,
      boxDepth: 120,
      boxHeight: 80,
      environment: 'auto',
      viewControl: {
        autoRotate: false
      },
      light: {
        main: {
          intensity: 1.2,
          shadow: true
        },
        ambient: {
          intensity: 0.3
        }
      }
    },
    xAxis3D: {
      name: axisLabels.x || 'X轴'
    },
    yAxis3D: {
      name: axisLabels.y || 'Y轴'
    },
    zAxis3D: {
      name: axisLabels.z || 'Z轴'
    },
    series: [{
      type: 'surface',
      data: z
    }]
  }
}

// 3D线图（v3.0格式）
const buildLine3dOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'line3d')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const trajectory = chartData.data?.trajectory || []
  const axisLabels = chartData.data?.axis_labels || {}

  return {
    title: {
      text: title || '3D轨迹图',
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      formatter: function(params) {
        return `X: ${params.data[0]}<br/>Y: ${params.data[1]}<br/>Z: ${params.data[2]}`
      }
    },
    grid3D: {
      boxWidth: 120,
      boxDepth: 120,
      boxHeight: 80,
      environment: 'auto',
      viewControl: {
        autoRotate: false
      },
      light: {
        main: {
          intensity: 1.2,
          shadow: true
        },
        ambient: {
          intensity: 0.3
        }
      }
    },
    xAxis3D: {
      name: axisLabels.x || 'X轴'
    },
    yAxis3D: {
      name: axisLabels.y || 'Y轴'
    },
    zAxis3D: {
      name: axisLabels.z || 'Z轴'
    },
    series: [{
      type: 'line3D',
      data: trajectory,
      lineStyle: {
        color: '#5470c6',
        width: 3
      },
      emphasis: {
        lineStyle: {
          color: '#ee6666',
          width: 5
        }
      }
    }]
  }
}

// 3D柱状图（v3.0格式）
const buildBar3dOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'bar3d')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const bars = chartData.data?.bars || []
  const axisLabels = chartData.data?.axis_labels || {}

  return {
    title: {
      text: title || '3D柱状图',
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      formatter: function(params) {
        return `X: ${params.data[0]}<br/>Y: ${params.data[1]}<br/>Z: ${params.data[2]}`
      }
    },
    grid3D: {
      boxWidth: 120,
      boxDepth: 120,
      boxHeight: 80,
      environment: 'auto',
      viewControl: {
        autoRotate: false
      },
      light: {
        main: {
          intensity: 1.2,
          shadow: true
        },
        ambient: {
          intensity: 0.3
        }
      }
    },
    xAxis3D: {
      name: axisLabels.x || 'X轴'
    },
    yAxis3D: {
      name: axisLabels.y || 'Y轴'
    },
    zAxis3D: {
      name: axisLabels.z || 'Z轴'
    },
    series: [{
      type: 'bar3D',
      data: bars.map(bar => [bar.x, bar.y, bar.z]),
      emphasis: {
        itemStyle: {
          color: '#ee6666'
        }
      }
    }]
  }
}

// 3D体素图（v3.0格式）
const buildVolume3dOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'volume3d')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const voxels = chartData.data?.voxels || []
  const valueRange = chartData.data?.value_range || { min: 0, max: 1 }
  const axisLabels = chartData.data?.axis_labels || {}

  return {
    title: {
      text: title || '3D体素图',
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      formatter: function(params) {
        return `X: ${params.data[0]}<br/>Y: ${params.data[1]}<br/>Z: ${params.data[2]}<br/>值: ${params.data[3]}`
      }
    },
    grid3D: {
      boxWidth: 120,
      boxDepth: 120,
      boxHeight: 80,
      environment: 'auto',
      viewControl: {
        autoRotate: false
      },
      light: {
        main: {
          intensity: 1.2,
          shadow: true
        },
        ambient: {
          intensity: 0.3
        }
      }
    },
    xAxis3D: {
      name: axisLabels.x || 'X轴'
    },
    yAxis3D: {
      name: axisLabels.y || 'Y轴'
    },
    zAxis3D: {
      name: axisLabels.z || 'Z轴'
    },
    visualMap: {
      show: false,
      min: valueRange.min,
      max: valueRange.max,
      inRange: {
        color: ['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#ffffbf', '#fee090', '#fdae61', '#f46d43', '#d73027', '#a50026']
      }
    },
    series: [{
      type: 'scatter3D',
      data: voxels,
      symbolSize: 2,
      emphasis: {
        itemStyle: {
          color: '#ee6666'
        }
      }
    }]
  }
}

// 边界层廓线图（v3.0格式）
const buildProfileOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'profile')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const altitudes = chartData.altitudes || []
  const elements = chartData.elements || []

  return {
    title: {
      text: title || '边界层廓线',
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    legend: {
      data: elements.map(e => e.name),
      top: '10%'
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'value',
      name: '数值',
      splitLine: { show: true }
    },
    yAxis: {
      type: 'value',
      name: '高度 (m)',
      data: altitudes,
      inverse: true  // 高度从上到下递减
    },
    series: elements.map((element, index) => ({
      name: element.name,
      type: 'line',
      data: element.data,
      smooth: true,
      showSymbol: true,
      symbol: 'circle',
      symbolSize: 6,
      itemStyle: {
        color: ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272'][index % 6]
      },
      emphasis: {
        focus: 'series'
      }
    }))
  }
}

// 分面时序图（多污染物×多站点场景）
const buildFacetTimeseriesOption = (chartData, title, meta) => {
  // 检测完整 ECharts 配置格式
  const optimizedConfig = detectAndOptimizeEChartsConfig(chartData, 'facet_timeseries')
  if (optimizedConfig) {
    return optimizedConfig
  }

  const facets = chartData.facets || []
  const layout = chartData.layout || 'vertical'

  // 站点颜色映射
  const stationColors = [
    '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
    '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#ff9f7f'
  ]

  // 构建 ECharts grid 配置（垂直分面：每个 facet 一个子图上下排列）
  const grids = []
  const xAxes = []
  const yAxes = []
  const series = []
  const titles = []

  const facetCount = facets.length
  const leftMargin = '12%'
  const rightMargin = '2%'

  if (layout === 'vertical') {
    // 垂直分面：子图上下排列
    // 空间分配：标题约20% + 图例约5% + dataZoom约8% + grids约67%
    const headerSpace = 30   // 标题+图例+facet小标题的总空间
    const footerSpace = 8    // dataZoom空间
    const spacing = 3        // 子图之间的间距百分比
    const availableHeight = 100 - headerSpace - footerSpace - (facetCount - 1) * spacing
    const gridHeight = Math.max(availableHeight / facetCount, 20) // 至少20%高度

    facets.forEach((facet, facetIndex) => {
      // 每个子图的顶部位置 = 标题空间 + facet_index * (grid高度 + 间距)
      const topPercent = headerSpace + facetIndex * (gridHeight + spacing)
      // bottom = 100 - top - grid高度 (避免与下一个重叠)
      const bottomPercent = 100 - topPercent - gridHeight

      // 每个 facet 的 grid
      grids.push({
        left: leftMargin,
        right: rightMargin,
        top: `${topPercent}%`,
        bottom: `${bottomPercent}%`,
        show: true,
        borderWidth: 1,
        borderColor: '#eee'
      })

      // 每个 facet 的 x 轴 - 添加 id 以便 series 正确绑定
      xAxes.push({
        id: `xAxis_${facetIndex}`,
        type: 'category',
        gridIndex: facetIndex,
        data: facet.x,
        boundaryGap: false,
        axisLabel: {
          show: facetIndex === facetCount - 1,  // 只在最后一个子图显示 x 轴标签
          fontSize: 10,
          rotate: facet.x.length > 24 ? 45 : 0
        }
      })

      // 每个 facet 的 y 轴 - 添加 id 以便 series 正确绑定
      yAxes.push({
        id: `yAxis_${facetIndex}`,
        type: 'value',
        gridIndex: facetIndex,
        name: facet.pollutant_name || facet.pollutant,
        nameLocation: 'middle',
        nameGap: 30,
        axisLabel: { fontSize: 10 }
      })

      // 每个 facet 的 series - 正确绑定到对应的 xAxis 和 yAxis
      facet.series.forEach((s, sIndex) => {
        series.push({
          name: s.name,
          type: 'line',
          xAxisIndex: facetIndex,
          yAxisIndex: facetIndex,
          data: s.data,
          smooth: true,
          showSymbol: false,
          itemStyle: {
            color: stationColors[sIndex % stationColors.length]
          },
          emphasis: { focus: 'series' }
        })
      })

      // 每个 facet 的小标题
      titles.push({
        text: facet.pollutant_name || facet.pollutant,
        left: '3%',
        top: `${topPercent + 2}%`,
        textStyle: {
          fontSize: 12,
          fontWeight: 'bold',
          color: '#333'
        }
      })
    })
  } else {
    // 水平分面：子图左右排列（暂未实现，使用垂直分面）
    return buildGenericOption(chartData, title, meta)
  }

  // 收集所有站点名称用于图例
  const stationNames = facets.length > 0 ? facets[0].series.map(s => s.name) : []

  // dataZoom配置（多子图场景）
  const xDataCount = facets.length > 0 ? facets[0].x?.length || 0 : 0
  const needsDataZoom = xDataCount > 20
  const dataZoomConfig = needsDataZoom ? [
    {
      type: 'slider',
      show: true,
      start: 0,
      end: 100,
      height: 24,
      bottom: 5,
      borderColor: '#ddd',
      fillerColor: 'rgba(25, 118, 210, 0.15)',
      handleStyle: { color: '#1976d2' },
      textStyle: { fontSize: 10 },
      brushSelect: false
    },
    {
      type: 'inside',
      start: 0,
      end: 100,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true
    }
  ] : []

  return {
    title: {
      text: title || '多污染物时序变化（分面图）',
      left: 'center',
      top: 5,
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: function(params) {
        // 只显示当前子图的 tooltip
        const facetIndex = params[0]?.xAxisIndex || 0
        const facet = facets[facetIndex]
        let result = `${params[0]?.axisValue}<br/>`
        params.forEach(p => {
          result += `${p.marker} ${p.seriesName}: ${p.value}<br/>`
        })
        return result
      }
    },
    legend: {
      data: stationNames,
      top: 30,
      show: stationNames.length > 1
    },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom: dataZoomConfig,
    series: series
  }
}

const MAX_INIT_RETRY = 100 // 增加到100次，总时间约8秒（处理v-show切换延迟）
const INIT_RETRY_DELAY = 80 // ms

let deferredInitTimer = null

// 清除延迟初始化定时器
const clearDeferredInitTimer = () => {
  if (deferredInitTimer) {
    clearTimeout(deferredInitTimer)
    deferredInitTimer = null
  }
}

// 延迟初始化：在放弃初始化后，仍然定期检查容器是否变为可见
const scheduleDeferredInit = () => {
  clearDeferredInitTimer()
  deferredInitTimer = setTimeout(() => {
    if (waitingForVisible && chartContainer.value && !chartInstance) {
      if (isContainerVisible()) {
        waitingForVisible = false
        initChart(0)
      } else {
        scheduleDeferredInit()
      }
    }
  }, 200)
}

// 等待容器具备尺寸后再初始化，避免 clientWidth/clientHeight 为 0
const initChart = (retry = 0) => {
  const el = chartContainer.value

  if (!el || !hasValidData.value) {
    return
  }

  const { clientWidth, clientHeight } = el
  if (!clientWidth || !clientHeight) {
    if (retry >= MAX_INIT_RETRY) {
      waitingForVisible = true
      scheduleDeferredInit()
      return
    }
    if (!el.style.minHeight) el.style.minHeight = '360px'
    if (!el.style.width) el.style.width = '100%'
    const parent = el.parentElement
    if (parent) {
      if (!parent.style.minHeight) parent.style.minHeight = '360px'
      if (!parent.style.width) parent.style.width = '100%'
    }
    const grand = parent?.parentElement
    if (grand) {
      if (!grand.style.minHeight) grand.style.minHeight = '360px'
      if (!grand.style.width) grand.style.width = '100%'
    }
    el.style.minHeight = el.style.minHeight || '320px'
    el.style.width = el.style.width || '100%'
    setTimeout(() => initChart(retry + 1), INIT_RETRY_DELAY)
    return
  }

  try {
    clearDeferredInitTimer()

    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }

    updateChartWidth()
    chartInstance = echarts.init(el, null, {
      renderer: 'canvas',
      useDirtyRect: false
    })
    const option = buildOption()

    if (!option || Object.keys(option).length === 0) {
      return
    }

    // 详细日志：确认最终配置
    console.log('[ChartPanel] ===== setOption 前的配置详情 =====')
    console.log('[ChartPanel] 标题配置:', JSON.stringify(option.title))
    console.log('[ChartPanel] 图例配置:', JSON.stringify(option.legend))
    console.log('[ChartPanel] 极坐标配置:', JSON.stringify(option.polar))
    console.log('[ChartPanel] radiusAxis配置:', JSON.stringify(option.radiusAxis))
    console.log('[ChartPanel] 图表容器尺寸:', JSON.stringify({ clientWidth, clientHeight }))
    console.log('[ChartPanel] 计算后的布局:', {
      标题高度: 30,
      可用图表高度: clientHeight - 30 - 80,
      极坐标半径: option.polar?.radius,
      图例距离: option.legend?.bottom
    })
    console.log('[ChartPanel] ===== 配置详情结束 =====')

    chartInstance.setOption(option, { notMerge: true })

    emit('ready')
  } catch (error) {
    console.error('[ChartPanel] initChart 错误:', error)
  }
}

onMounted(() => {
  initChart()

  if ('ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        updateChartWidth()
        if (waitingForVisible && chartContainer.value) {
          const { clientWidth, clientHeight } = chartContainer.value
          if (clientWidth > 0 && clientHeight > 0) {
            clearDeferredInitTimer()
            waitingForVisible = false
            initChart()
          }
        }
      })
    })
    if (scrollContainer.value) {
      resizeObserver.observe(scrollContainer.value)
    }
    if (chartContainer.value) {
      resizeObserver.observe(chartContainer.value)
    }
  }

  window.addEventListener('resize', handleWindowResize)
  document.addEventListener('click', handleGlobalClick)
})

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  clearDeferredInitTimer()
  window.removeEventListener('resize', handleWindowResize)
  document.removeEventListener('click', handleGlobalClick)
})

const updateChartWidth = () => {
  chartWidth.value = '100%'
  requestAnimationFrame(() => {
    if (chartInstance) {
      chartInstance.resize()
    }
  })
}

watch(() => props.data, (newData, oldData) => {
  nextTick(() => {
    try {
      if (chartInstance && hasValidData.value) {
        updateChartWidth()
        const option = buildOption()

        if (!option || Object.keys(option).length === 0) {
          return
        }

        const newType = newData?.type
        const oldType = oldData?.type

        if (newType !== oldType) {
          if (!isContainerVisible()) {
            waitingForVisible = true
            scheduleDeferredInit()
            return
          }
          chartInstance.dispose()
          chartInstance = null
          initChart()
        } else {
          console.log('[ChartPanel] watch更新图表，配置:', {
            titleTop: option.title?.top,
            legendBottom: option.legend?.bottom,
            polarRadius: option.polar?.radius
          })
          chartInstance.setOption(option, true)
        }
      } else if (!chartInstance && hasValidData.value) {
        if (!isContainerVisible()) {
          waitingForVisible = true
          scheduleDeferredInit()
          return
        }
        initChart()
      }
    } catch (error) {
      console.error('[ChartPanel] watch 回调错误:', error)
    }
  })
}, { deep: true, immediate: true })

// ==================== 导出功能：状态暴露方法 ====================

/**
 * 获取当前图表的用户交互状态
 * 用于导出时保持用户的自定义视图
 */
const getChartState = () => {
  if (!chartInstance) return null
  
  try {
    const option = chartInstance.getOption()
    
    return {
      // Legend状态：哪些系列被用户隐藏
      legendSelected: option.legend?.[0]?.selected || {},
      
      // DataZoom状态：用户选择的数据范围
      dataZoom: option.dataZoom?.map(dz => ({
        start: dz.start,
        end: dz.end,
        startValue: dz.startValue,
        endValue: dz.endValue
      })) || [],
      
      // 3D图表视角（如有）
      grid3D: option.grid3D?.[0]?.viewControl || null,
      
      // 图表类型
      chartType: props.data?.type || 'unknown'
    }
  } catch (error) {
    console.error('[ChartPanel] getChartState error:', error)
    return null
  }
}

/**
 * 获取图表截图（Base64格式）
 * 用于导出预览和PDF生成
 * 支持异步等待渲染完成
 */
const getChartImage = async (options = {}) => {
  try {
    const {
      pixelRatio = 2,        // 分辨率倍数
      backgroundColor = '#fff', // 背景色
      type = 'png',          // 图片格式
      waitForRender = true   // 是否等待渲染完成
    } = options

    // 等待图表渲染完成的辅助函数
    const waitForChartRender = (instance, timeout = 2000) => {
      return new Promise((resolve) => {
        if (!instance) {
          resolve(false)
          return
        }
        
        // 检查图表是否已经渲染（通过检查是否有图形元素）
        const checkRender = () => {
          try {
            const option = instance.getOption()
            if (option && Object.keys(option).length > 0) {
              // 使用 finished 事件确保渲染完成
              const handler = () => {
                instance.off('finished', handler)
                resolve(true)
              }
              instance.on('finished', handler)
              
              // 如果图表已经渲染完成，立即触发
              setTimeout(() => {
                instance.off('finished', handler)
                resolve(true)
              }, 100)
              
              // 超时保护
              setTimeout(() => {
                instance.off('finished', handler)
                resolve(true) // 超时也返回true，避免无限等待
              }, timeout)
            } else {
              resolve(false)
            }
          } catch (e) {
            resolve(false)
          }
        }
        
        checkRender()
      })
    }

    const tryUseInstance = async () => {
      if (!chartInstance || !isContainerVisible()) return null
      
      // 如果要求等待渲染，先等待一下
      if (waitForRender) {
        await waitForChartRender(chartInstance, 1500)
        // 额外等待一小段时间确保渲染稳定
        await new Promise(resolve => setTimeout(resolve, 100))
      }
      
      return chartInstance.getDataURL({
        type,
        pixelRatio,
        backgroundColor
      })
    }

    let dataUrl = await tryUseInstance()

    // 如果实例不可用，使用离屏容器渲染
    if (!dataUrl && hasValidData.value) {
      const tempDiv = document.createElement('div')
      tempDiv.style.position = 'absolute'
      tempDiv.style.left = '-9999px'
      tempDiv.style.top = '0'
      tempDiv.style.width = '1200px'
      tempDiv.style.height = '420px'
      tempDiv.style.zIndex = '-1'
      document.body.appendChild(tempDiv)
      try {
        const tempInstance = echarts.init(tempDiv, null, {
          renderer: 'canvas'
        })
        const option = buildOption()
        if (option && Object.keys(option).length > 0) {
          tempInstance.setOption(option, { notMerge: true, lazyUpdate: false })
          await waitForChartRender(tempInstance, 2000)
          await new Promise(resolve => setTimeout(resolve, 200))
          dataUrl = tempInstance.getDataURL({
            type,
            pixelRatio,
            backgroundColor
          })
        }
        tempInstance.dispose()
      } catch (err) {
        console.error('[ChartPanel] getChartImage 离屏渲染失败:', err)
      } finally {
        tempDiv.remove()
      }
    }

    return dataUrl
  } catch (error) {
    console.error('[ChartPanel] getChartImage error:', error)
    return null
  }
}

/**
 * 获取ECharts实例
 * 用于高级操作
 */
const getChartInstance = () => {
  return chartInstance
}

/**
 * 获取图表的原始配置数据
 */
const getChartData = () => {
  return props.data
}

/**
 * 处理右键菜单
 */
const handleContextMenu = async (event) => {
  const imageData = await getChartImage({ pixelRatio: 2, waitForRender: true })

  if (!imageData) {
    return
  }

  contextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    imageData: imageData
  }
}

/**
 * 复制图片到剪贴板
 */
const copyImageToClipboard = async () => {
  try {
    const imageData = contextMenu.value.imageData
    if (!imageData) return

    const img = new Image()

    await new Promise((resolve, reject) => {
      img.onload = resolve
      img.onerror = reject
      img.src = imageData
    })

    const canvas = document.createElement('canvas')
    canvas.width = img.width
    canvas.height = img.height
    const ctx = canvas.getContext('2d')
    ctx.drawImage(img, 0, 0)

    if (navigator.clipboard?.write && window.ClipboardItem) {
      try {
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
        await navigator.clipboard.write([
          new ClipboardItem({ 'image/png': blob })
        ])
        hideContextMenu()
        return
      } catch (e) {
        console.warn('[ChartPanel] Clipboard API 不可用:', e.message)
      }
    }

    try {
      img.style.position = 'fixed'
      img.style.left = '-9999px'
      img.style.top = '-9999px'
      document.body.appendChild(img)
      await new Promise(resolve => setTimeout(resolve, 100))

      const selection = window.getSelection()
      selection.removeAllRanges()
      const range = document.createRange()
      range.selectNode(img)
      selection.addRange(range)

      const success = document.execCommand('copy')
      selection.removeAllRanges()
      document.body.removeChild(img)

      if (success) {
        hideContextMenu()
        return
      }
    } catch (e) {
      console.warn('[ChartPanel] execCommand 失败:', e.message)
    }

    // 降级：下载 PNG
    const base64Data = imageData.split(',')[1]
    const byteString = atob(base64Data)
    const ab = new ArrayBuffer(byteString.length)
    const ia = new Uint8Array(ab)
    for (let i = 0; i < byteString.length; i++) {
      ia[i] = byteString.charCodeAt(i)
    }
    const blob = new Blob([ab], { type: 'image/png' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${props.data?.title || '图表'}_${Date.now()}.png`
    link.click()
    URL.revokeObjectURL(url)

  } catch (error) {
    console.error('[ChartPanel] 复制失败:', error)
  } finally {
    hideContextMenu()
  }
}

/**
 * 保存图片为 PNG 文件
 */
const saveImageAsPNG = () => {
  try {
    const imageData = contextMenu.value.imageData
    if (!imageData) return

    const base64Data = imageData.split(',')[1]
    const byteString = atob(base64Data)
    const ab = new ArrayBuffer(byteString.length)
    const ia = new Uint8Array(ab)
    for (let i = 0; i < byteString.length; i++) {
      ia[i] = byteString.charCodeAt(i)
    }
    const blob = new Blob([ab], { type: 'image/png' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${props.data?.title || '图表'}_${Date.now()}.png`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('[ChartPanel] 保存图片失败:', error)
  } finally {
    hideContextMenu()
  }
}

/**
 * 隐藏右键菜单
 */
const hideContextMenu = () => {
  contextMenu.value.visible = false
  contextMenu.value.imageData = null
}

// 点击其他地方关闭右键菜单
const handleGlobalClick = (event) => {
  if (contextMenu.value.visible) {
    hideContextMenu()
  }
}

// 暴露方法给父组件
defineExpose({
  getChartState,
  getChartImage,
  getChartInstance,
  getChartData,
  // 重新初始化图表（当容器从不可见变为可见时调用）
  reinitChart: () => {
    if (waitingForVisible && chartContainer.value && !chartInstance) {
      const { clientWidth, clientHeight } = chartContainer.value
      if (clientWidth > 0 && clientHeight > 0) {
        clearDeferredInitTimer()
        waitingForVisible = false
        initChart(0)
      }
    } else if (chartInstance) {
      chartInstance.resize()
    } else {
      initChart(0)
    }
  }
})
</script>

<style lang="scss" scoped>
.chart-panel {
  width: 100%;
  /* 移除固定高度，使用动态高度 */
  min-height: 280px;
  /* 移除背景、边框、阴影和内边距，让图表填满整个空间 */
  background: transparent;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
  position: relative;
  overflow: hidden;
}

.chart-empty {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #999;
  font-size: 14px;
  gap: 8px;

  .debug-info {
    font-size: 11px;
    color: #ccc;
    font-family: monospace;
    max-width: 90%;
    word-break: break-all;
  }
}

.chart-scroll {
  width: 100%;
  height: 100%;
  overflow: auto;
}

.chart-canvas {
  height: 100%;
}

// 自定义右键菜单样式
.chart-context-menu {
  position: fixed;
  z-index: 100000;  // 非常高的 z-index，确保在浏览器原生菜单之上
  min-width: 160px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15), 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 6px 0;
  animation: contextMenuFadeIn 0.15s ease-out;

  .context-menu-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    cursor: pointer;
    font-size: 14px;
    color: #333;
    transition: all 0.15s;

    svg {
      flex-shrink: 0;
      color: #666;
    }

    &:hover {
      background: #f5f5f5;
      color: #1976d2;

      svg {
        color: #1976d2;
      }
    }

    &:active {
      background: #e8e8e8;
    }
  }
}

@keyframes contextMenuFadeIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
