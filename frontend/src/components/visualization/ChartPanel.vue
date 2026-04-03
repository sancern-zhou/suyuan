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
      ></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import { chartScreenshotManager } from '@/utils/chartScreenshotManager'

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
    'bar': '380px',
    'line': '380px',
    'timeseries': '420px',
    'stacked_timeseries': '480px',  // 堆叠时序图（多离子堆叠+PM2.5双Y轴）
    'weather_timeseries': '450px',  // 带风向指针的气象时序图
    'pressure_pbl_timeseries': '400px',  // 气压+边界层高度双Y轴图
    'facet_timeseries': '600px',  // 分面时序图（多污染物×多站点）
    'heatmap': '480px',
    'radar': '420px',
    'wind_rose': '380px',
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
  const ok = clientWidth > 0 && clientHeight > 0
  if (!ok) {
    logContainerMetrics(el, 'check_visible_fail')
  }
  return ok
}

const logContainerMetrics = (el, label = 'container') => {
  if (!el) {
    console.log('[ChartPanel] logContainerMetrics: 无容器', { label })
    return
  }
  const parent = el.parentElement
  const grand = parent?.parentElement
  const rect = el.getBoundingClientRect()
  console.log('[ChartPanel] logContainerMetrics', {
    label,
    chartId: getChartIdForLog(),
    title: props.data?.title,
    width: el.clientWidth,
    height: el.clientHeight,
    rectWidth: rect?.width,
    rectHeight: rect?.height,
    parentDisplay: parent ? getComputedStyle(parent).display : null,
    parentWidth: parent?.clientWidth,
    parentHeight: parent?.clientHeight,
    grandDisplay: grand ? getComputedStyle(grand).display : null,
    grandWidth: grand?.clientWidth,
    grandHeight: grand?.clientHeight
  })
}
const handleWindowResize = () => {
  updateChartWidth()
}

// 检查是否有有效数据（v3.0格式）
const hasValidData = computed(() => {
  if (!props.data) {
    console.log('[ChartPanel] hasValidData: false, props.data is null')
    return false
  }

  const chartType = props.data.type
  if (!chartType) {
    console.log('[ChartPanel] hasValidData: false, missing chart type')
    return false
  }

  // v3.0格式：数据统一在data字段中
  const chartData = props.data.data
  if (!chartData) {
    console.log('[ChartPanel] hasValidData: false, missing data field')
    return false
  }

  console.log('[ChartPanel] hasValidData: true', chartType)
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

// 构建ECharts配置（v3.0格式）
const buildOption = () => {
  try {
    if (!hasValidData.value) {
      console.log('[ChartPanel] buildOption: hasValidData is false, return empty option')
      return {}
    }

    // v3.0格式：直接从data.data获取图表类型、数据和元数据
    const chartType = props.data.type
    const title = props.data.title || ''
    const meta = props.data.meta || {}
    const chartData = props.data.data

    // 适配v3.0格式：如果chartData是对象且包含type字段，说明是嵌套格式
    let actualData = chartData
    if (typeof chartData === 'object' && chartData.type) {
      // v3.0格式：{ type: "pie", data: [...] }
      actualData = chartData.data
    }

    console.log('[ChartPanel] buildOption: chartType:', chartType, 'actualData:', actualData, 'title:', title)

    let option = {}
    switch (chartType) {
      case 'pie':
        option = buildPieOption(actualData, title, meta)
        break
      case 'bar':
        option = buildBarOption(actualData, title, meta)
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
        // 【关键修复】智能识别类型：当type为"chart"或其他未知类型时，根据数据格式判断
        // 如果数据包含x和series字段，视为时序图
        const hasTimeseriesFormat = actualData &&
          actualData.x && actualData.series &&
          Array.isArray(actualData.x) && Array.isArray(actualData.series)
        const hasLineFormat = actualData &&
          actualData.x && actualData.y &&
          Array.isArray(actualData.x) && Array.isArray(actualData.y)

        if (hasTimeseriesFormat || hasLineFormat) {
          console.log('[ChartPanel] 智能识别为时序图格式，使用buildLineOption渲染')
          option = buildLineOption(actualData, title, meta)
        } else {
          console.log('[ChartPanel] 使用通用配置buildGenericOption')
          option = buildGenericOption(actualData, title, meta)
        }
    }

    // 验证option不为空
    if (!option || Object.keys(option).length === 0) {
      console.error('[ChartPanel] buildOption 生成空配置')
      return {}
    }

    return option
  } catch (error) {
    console.error('[ChartPanel] buildOption 错误:', error)
    return {}
  }
}

// 饼图
const buildPieOption = (payload, title, meta) => {
  const data = Array.isArray(payload) ? payload : []

  return {
    title: {
      text: title,
      left: 'center',
      textStyle: { fontSize: 16, fontWeight: 'bold' }
    },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', left: 'left', top: '10%' },
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
  const xData = chartData.x || []
  const yData = chartData.y || []
  const series = chartData.series || []

  console.log('[ChartPanel] buildBarOption: xData.length:', xData.length, 'series.length:', series.length, 'hasYData:', yData.length > 0)

  // 支持两种格式：series（多序列）或y（单序列）
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
      console.log('[ChartPanel] 检测到O3双数据源格式，合并数据中...')

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

      console.log('[ChartPanel] 合并完成:', {
        xDataCount: xData.length,
        o3SeriesCount: o3Series.filter(v => v !== null).length,
        o3_8hSeriesCount: o3_8hSeries.filter(v => v !== null).length,
        seriesNames: series.map(s => s.name)
      })

      return { x: xData, series }
    }
  }

  // 默认返回原数据
  return chartData
}

// 线图/时序图（v3.0格式）
const buildLineOption = (chartData, title, meta) => {
  // v3.0格式：chartData = { x: [...], series: [{name, data}, ...] } 或 { x: [...], y: [...] }
  // 也支持原始记录列表格式（包含 O3 和 O3_8h 字段）
  // 也支持 series[].data 为 [{time, value}] 对象数组格式（Agent生成）

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
        // [[time, value], ...] 格式
        xData = firstData.map(d => d[0])
        series = series.map(s => ({
          ...s,
          data: s.data.map(d => (Array.isArray(d) ? d[1] : d) ?? null)
        }))
      } else if (typeof first === 'object' && first !== null && 'time' in first) {
        // [{time, value}, ...] 格式
        xData = firstData.map(d => d.time)
        series = series.map(s => ({
          ...s,
          data: s.data.map(d => d.value ?? null)
        }))
      }
    }
  }

  console.log('[ChartPanel] buildLineOption: xData.length:', xData.length, 'series.length:', series.length, 'hasYData:', yData.length > 0)

  // 支持两种格式：series（多序列）或y（单序列）
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

const MAX_INIT_RETRY = 20
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
      const { clientWidth, clientHeight } = chartContainer.value
      if (clientWidth > 0 && clientHeight > 0) {
        console.log('[ChartPanel] 延迟检查发现容器已可见，重新初始化', {
          clientWidth,
          clientHeight,
          chartId: getChartIdForLog()
        })
        waitingForVisible = false
        initChart(0) // 从0开始重试
      } else {
        // 继续等待
        scheduleDeferredInit()
      }
    }
  }, 500) // 每500ms检查一次
}

// 等待容器具备尺寸后再初始化，避免 clientWidth/clientHeight 为 0
const initChart = (retry = 0) => {
  const el = chartContainer.value

  if (!el || !hasValidData.value) {
    console.log('[ChartPanel] initChart: 跳过初始化，', {
      hasContainer: !!el,
      hasValidData: hasValidData.value
    })
    return
  }

  const { clientWidth, clientHeight } = el
  if (!clientWidth || !clientHeight) {
    // 父容器可能处于折叠或未渲染完成，稍后重试
    if (retry >= MAX_INIT_RETRY) {
      console.warn('[ChartPanel] 容器尺寸始终为0，放弃初始化，等待容器变为可见', {
        retry,
        clientWidth,
        clientHeight,
        chartId: getChartIdForLog(),
        title: props.data?.title
      })
      logContainerMetrics(el, 'init_fail')
      waitingForVisible = true
      scheduleDeferredInit() // 启动延迟检查
      return
    }
    console.log('[ChartPanel] 容器尺寸为0，等待可见后重试', {
      retry,
      clientWidth,
      clientHeight,
      chartId: getChartIdForLog(),
      title: props.data?.title
    })
    logContainerMetrics(el, 'init_retry_zero_size')
    // 强行撑开本层与父层，避免高度被折叠
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
    // 尝试设置最小高度，帮助占位撑开
    el.style.minHeight = el.style.minHeight || '320px'
    el.style.width = el.style.width || '100%'
    setTimeout(() => initChart(retry + 1), INIT_RETRY_DELAY)
    return
  }

  try {
    // 清除延迟初始化定时器（如果存在）
    clearDeferredInitTimer()

    // 如果已存在实例，先销毁再重建，避免 "already initialized" 警告
    if (chartInstance) {
      // 注销旧实例
      const chartId = props.data?.id || getChartIdForLog()
      chartScreenshotManager.unregisterChart(chartId)
      chartInstance.dispose()
      chartInstance = null
    }

    updateChartWidth()
    chartInstance = echarts.init(el)
    const option = buildOption()

    if (!option || Object.keys(option).length === 0) {
      console.error('[ChartPanel] buildOption 返回空配置:', option)
      return
    }

    console.log('[ChartPanel] setOption:', option)
    console.log('[ChartPanel] initChart success', {
      width: el.clientWidth,
      height: el.clientHeight,
      chartId: getChartIdForLog(),
      title: props.data?.title
    })
    logContainerMetrics(el, 'init_success')

    chartInstance.setOption(option)

    // 注册到截图管理器（图表创建完成后立即注册）
    chartScreenshotManager.registerChart({
      id: props.data?.id || getChartIdForLog(),
      type: props.data?.type || 'chart',
      title: props.data?.title || '',
      instance: chartInstance,
      meta: props.data?.meta || {}
    })

    emit('ready')
  } catch (error) {
    console.error('[ChartPanel] initChart 错误:', error)
  }
}

onMounted(() => {
  initChart()

  if ('ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(() => {
      updateChartWidth()
      // 如果之前因为尺寸为0放弃了初始化，尺寸变化后再尝试一次
      if (waitingForVisible && chartContainer.value) {
        const { clientWidth, clientHeight } = chartContainer.value
        if (clientWidth > 0 && clientHeight > 0) {
          console.log('[ChartPanel] 容器尺寸变化，重新初始化', {
            clientWidth,
            clientHeight,
            chartId: getChartIdForLog()
          })
          clearDeferredInitTimer() // 清除延迟检查，因为已经手动触发了
          waitingForVisible = false
          initChart()
        }
      }
    })
    if (scrollContainer.value) {
      resizeObserver.observe(scrollContainer.value)
    }
    // 也观察 chartContainer，确保能检测到尺寸变化
    if (chartContainer.value) {
      resizeObserver.observe(chartContainer.value)
    }
  }

  window.addEventListener('resize', handleWindowResize)
})

onBeforeUnmount(() => {
  // 注销截图管理器中的图表
  const chartId = props.data?.id || getChartIdForLog()
  chartScreenshotManager.unregisterChart(chartId)

  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  clearDeferredInitTimer() // 清除延迟初始化定时器
  window.removeEventListener('resize', handleWindowResize)
})

const getDataPointCount = () => {
  const chartData = props.data?.data
  if (!chartData) return 0
  if (Array.isArray(chartData?.x)) {
    return chartData.x.length
  }
  if (Array.isArray(chartData?.data)) {
    return chartData.data.length
  }
  if (Array.isArray(chartData)) {
    return chartData.length
  }
  return 0
}

const updateChartWidth = () => {
  // 固定100%宽度，通过dataZoom滑块查看更多数据，避免横向滚动
  chartWidth.value = '100%'
  nextTick(() => {
    if (chartInstance) {
      chartInstance.resize()
    }
  })
}

watch(() => props.data, (newData, oldData) => {
  try {
    // 记录数据变化
    console.log('[ChartPanel] data变化:', {
      newData: newData,
      oldData: oldData,
      hasChartInstance: !!chartInstance,
      hasValidData: hasValidData.value
    })

    // 使用 nextTick 确保数据更新后 DOM 同步
    nextTick(() => {
      try {
        if (chartInstance && hasValidData.value) {
          updateChartWidth()
          const option = buildOption()

          if (!option || Object.keys(option).length === 0) {
            console.error('[ChartPanel] buildOption 返回空配置:', option)
            return
          }

          console.log('[ChartPanel] 更新图表:', option)

          // v3.0格式：使用type字段检查图表类型变化
          const newType = newData?.type
          const oldType = oldData?.type

          if (newType !== oldType) {
            console.log('[ChartPanel] 图表类型变化，销毁重建实例:', { oldType, newType })
          if (!isContainerVisible()) {
            console.warn('[ChartPanel] 类型变化但容器不可见，延迟重建', {
              chartId: getChartIdForLog(),
              title: props.data?.title
            })
            waitingForVisible = true
            return
          }
          chartInstance.dispose()
          chartInstance = null
          initChart()
          } else {
            chartInstance.setOption(option, true)
          }
        } else if (!chartInstance && hasValidData.value) {
          // 实例不存在但有数据，重新初始化
          console.log('[ChartPanel] 重新初始化图表')
        if (!isContainerVisible()) {
          console.warn('[ChartPanel] 重新初始化但容器不可见，延迟重建', {
            chartId: getChartIdForLog(),
            title: props.data?.title
          })
          waitingForVisible = true
          return
        }
        initChart()
        }
      } catch (error) {
        console.error('[ChartPanel] nextTick 回调错误:', error)
      }
    })
  } catch (error) {
    console.error('[ChartPanel] watch 回调错误:', error)
  }
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

    // 如果实例不可用或容器尺寸为0，则使用离屏容器渲染一次截图
    if (!dataUrl && hasValidData.value) {
      console.warn('[ChartPanel] getChartImage: 使用离屏容器获取截图', {
        chartId: getChartIdForLog(),
        title: props.data?.title
      })
      const tempDiv = document.createElement('div')
      tempDiv.style.position = 'absolute'
      tempDiv.style.left = '-9999px'
      tempDiv.style.top = '0'
      tempDiv.style.width = '1200px'
      tempDiv.style.height = '420px'
      tempDiv.style.zIndex = '-1'
      document.body.appendChild(tempDiv)
      try {
        const tempInstance = echarts.init(tempDiv)
        const option = buildOption()
        if (option && Object.keys(option).length > 0) {
          tempInstance.setOption(option, { notMerge: true, lazyUpdate: false })
          
          // 【关键修复】等待离屏图表渲染完成
          await waitForChartRender(tempInstance, 2000)
          // 额外等待确保渲染稳定
          await new Promise(resolve => setTimeout(resolve, 200))
          
          dataUrl = tempInstance.getDataURL({
            type,
            pixelRatio,
            backgroundColor
          })
          
          console.log('[ChartPanel] 离屏容器截图完成', {
            chartId: getChartIdForLog(),
            hasDataUrl: !!dataUrl,
            dataUrlLength: dataUrl ? dataUrl.length : 0
          })
        } else {
          console.error('[ChartPanel] getChartImage 离屏构建option为空', { option })
        }
        tempInstance.dispose()
      } catch (err) {
        console.error('[ChartPanel] getChartImage 离屏渲染失败:', err)
      } finally {
        tempDiv.remove()
      }
    }

    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/d7da9dc0-913c-4a71-877d-8ad5d396d494', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sessionId: 'debug-session',
        runId: 'pre-fix',
        hypothesisId: 'H3',
        location: 'ChartPanel.vue:getChartImage',
        message: 'get_chart_image',
        data: {
          hasInstance: !!chartInstance,
          hasDataUrl: !!dataUrl,
          usedOffscreen: !chartInstance || !isContainerVisible(),
          dataUrlPrefix: typeof dataUrl === 'string' ? dataUrl.substring(0, 32) : null,
          dataUrlLength: dataUrl ? dataUrl.length : 0
        },
        timestamp: Date.now()
      })
    }).catch(() => {})
    // #endregion agent log

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

// 暴露方法给父组件
defineExpose({
  getChartState,
  getChartImage,
  getChartInstance,
  getChartData
})
</script>

<style lang="scss" scoped>
.chart-panel {
  width: 100%;
  /* 移除固定高度，使用动态高度 */
  min-height: 280px;
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
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
</style>
