<template>
  <div class="viz-panel" :class="{ 'has-content': visualizations.length }">
    <!-- 可视化内容 -->
    <div v-if="visualizations.length > 0" class="viz-content-section">
      <div class="panel-header">
        <div class="panel-title-group">
          <h3>{{ visualizationPanelTitle }}</h3>
          <span v-if="visualizations.length" class="viz-count">共 {{ visualizations.length }} 个结果</span>
        </div>
        <div class="header-actions">
          <!-- 右侧面板不需要操作按钮 -->
        </div>
      </div>

      <!-- 可视化内容列表 -->
      <div class="panel-body">
        <div
          v-for="(viz, index) in visualizations"
          :key="viz.id || `${viz.type || 'viz'}_${index}`"
          class="viz-item"
          :class="getLayoutClass(viz.meta?.layout_hint)"
        >
          <div class="viz-item-header">
            <div class="viz-title">
              <span class="viz-type-tag">{{ getTypeLabel(viz.type) }}</span>
              <span class="viz-title-text">{{ viz.title || `第${index + 1}个${getTypeLabel(viz.type)}` }}</span>
            </div>
            <span v-if="formatTimestamp(viz.timestamp)" class="viz-time">
              {{ formatTimestamp(viz.timestamp) }}
            </span>
          </div>

          <div class="viz-meta">
            <div class="meta-row" v-if="viz.meta">
              <div class="meta-item" v-if="viz.meta.generator">
                <label>生成器:</label>
                <span class="generator-tag">{{ viz.meta.generator }}</span>
              </div>
            </div>
          </div>

          <!-- 轨迹地图 -->
          <TrajectoryMapPanel
            v-if="viz.type === 'map' && isTrajectoryMap(viz)"
            :ref="el => setChartRef(viz.id || `viz_${index}`, el)"
            :config="viz.data"
            @ready="onPanelReady"
          />

          <!-- 普通地图 -->
          <MapPanel
            v-else-if="viz.type === 'map'"
            :ref="el => setChartRef(viz.id || `viz_${index}`, el)"
            :config="viz.data"
            @ready="onPanelReady"
          />

          <!-- 图表 -->
          <ChartPanel
            v-else-if="isChartType(viz)"
            :ref="el => setChartRef(viz.id || `viz_${index}`, el)"
            :key="viz.id || viz.title || `chart_${index}`"
            :data="viz"
            @ready="onPanelReady"
          />

          <!-- 表格 -->
          <DataTable
            v-else-if="viz.type === 'table'"
            :rows="getTableRows(viz)"
            @ready="onPanelReady"
          />

          <!-- 图片 -->
          <ImagePanel
            v-else-if="viz.type === 'image'"
            :ref="el => setChartRef(viz.id || `viz_${index}`, el)"
            :src="viz.image_url || viz.markdown_image?.match(/]\((.+?)\)/)?.[1] || (typeof viz.data === 'string' ? viz.data : viz.data?.url)"
            @ready="onPanelReady"
          />

          <!-- 文本 -->
          <div v-else-if="viz.type === 'text' || viz.text" class="text-panel">
            <MarkdownRenderer :content="viz.text || viz.content || viz.data" />
          </div>

          <!-- 未知类型 -->
          <div v-else class="unknown-panel">
            暂未识别的可视化类型：{{ viz.type || '未知' }}
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="visualizations.length === 0" class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M3 9h18" />
        <path d="M9 3v18" />
      </svg>
      <p class="empty-title">暂无内容</p>
      <p class="empty-tip">当生成可视化图表或检索到知识文档时，将在此处显示</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { useReactStore } from '@/stores/reactStore'
import MapPanel from './visualization/MapPanel.vue'
import TrajectoryMapPanel from './visualization/TrajectoryMapPanel.vue'
import ChartPanel from './visualization/ChartPanel.vue'
import DataTable from './visualization/DataTable.vue'
import ImagePanel from './visualization/ImagePanel.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const store = useReactStore()

const props = defineProps({
  content: {
    type: Object,
    default: null
  },
  history: {
    type: Array,
    default: () => []
  },
  selectedMessageId: {
    type: String,
    default: null
  },
  assistantMode: {
    type: String,
    default: 'general-agent'
  },
  expertResults: {
    type: Object,
    default: null
  }
})

defineEmits([])

const expandedGroups = ref(['weather', 'component'])

// 图表组件引用（用于刷新和截图）
const chartRefs = ref({})
const mapRefs = ref({})

// ==================== 清理函数（需要在defineExpose之前定义）================
const clearChartRefs = () => {
  const chartIds = Object.keys(chartRefs.value)
  chartRefs.value = {}
  console.log('[VisualizationPanel] 清理所有图表引用')
}

// ==================== 图表刷新方法 ====================
// 内部方法：刷新所有图表（当新图表数据到达时调用）
const refreshAllChartsInternal = () => {
  console.log('[VisualizationPanel] refreshAllChartsInternal 触发，图表数量:', Object.keys(chartRefs.value).length)

  // 遍历所有图表引用，调用重新初始化方法
  for (const [chartId, chartRef] of Object.entries(chartRefs.value)) {
    if (chartRef && typeof chartRef.reinitChart === 'function') {
      console.log('[VisualizationPanel] 调用图表重新初始化:', chartId)
      try {
        chartRef.reinitChart()
      } catch (error) {
        console.error('[VisualizationPanel] 图表重新初始化失败:', chartId, error)
      }
    }
  }

  console.log('[VisualizationPanel] refreshAllChartsInternal 完成')
}

// ==================== 对外暴露的方法 ====================
// 暴露方法给父组件（用于报告截图注入）
defineExpose({
  // 清理所有图表引用
  clearChartRefs,

  // 获取所有图表的截图（排除地图类型），返回Promise<{chartId: base64Image}>
  // @param {Object} options - 选项
  // @param {boolean} options.excludeMaps - 是否排除地图（默认true）
  getAllChartImages: async (options = {}) => {
    const { excludeMaps = true } = options
    const results = {}

    console.log('[VisualizationPanel] getAllChartImages 开始，chartRefs数量:', Object.keys(chartRefs.value).length)
    console.log('[VisualizationPanel] chartIds:', Object.keys(chartRefs.value))
    console.log('[VisualizationPanel] excludeMaps:', excludeMaps)

    // 创建 chartId -> viz 的映射，用于获取图表类型
    const chartIdToViz = new Map()
    visualizations.value.forEach((viz, idx) => {
      const vizId = viz.id || `viz_${idx}`
      chartIdToViz.set(vizId, viz)
    })
    console.log('[VisualizationPanel] chartIdToViz映射:', Array.from(chartIdToViz.keys()))

    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/d7da9dc0-913c-4a71-877d-8ad5d396d494', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sessionId: 'debug-session',
        runId: 'pre-fix',
        hypothesisId: 'H1',
        location: 'VisualizationPanel.vue:getAllChartImages',
        message: 'start_get_all_chart_images',
        data: { chartIds: Object.keys(chartRefs.value) },
        timestamp: Date.now()
      })
    }).catch(() => {})
    // #endregion agent log

    // 遍历所有图表引用
    for (const [chartId, chartRef] of Object.entries(chartRefs.value)) {
      // 【新增】如果需要排除地图类型，检查当前图表是否为地图
      const viz = chartIdToViz.get(chartId)
      if (excludeMaps && viz && viz.type === 'map') {
        // 检查是否是轨迹地图（轨迹地图也属于地图类型）
        const isMap = viz.type === 'map'
        const isTrajMap = isTrajectoryMap(viz)
        console.log(`[VisualizationPanel] 跳过地图类型: ${chartId}, isMap=${isMap}, isTrajectory=${isTrajMap}`)
        continue  // 跳过地图类型，不获取截图
      }

      console.log(`[VisualizationPanel] 处理图表 ${chartId}:`, {
        hasRef: !!chartRef,
        hasMethod: typeof chartRef?.getChartImage === 'function'
      })

      if (chartRef && typeof chartRef.getChartImage === 'function') {
        try {
          // 【关键修复】传入 waitForRender=true 确保等待图表渲染完成
          const imageResult = chartRef.getChartImage({ waitForRender: true })
          console.log(`[VisualizationPanel] ${chartId} getChartImage返回:`, typeof imageResult, imageResult ? '有值' : 'null/undefined')

          // 如果是 Promise，等待结果
          let finalImage = null
          if (imageResult instanceof Promise) {
            const resolvedValue = await imageResult
            console.log(`[VisualizationPanel] ${chartId} Promise解析结果:`, typeof resolvedValue, resolvedValue ? `有值（长度: ${resolvedValue?.length || 0}）` : 'null/undefined')
            finalImage = resolvedValue
          } else {
            finalImage = imageResult
            if (imageResult) {
              console.log(`[VisualizationPanel] ${chartId} 同步返回截图，长度: ${imageResult.length}`)
            }
          }

          // 【关键修复】验证截图数据有效性
          if (!finalImage || typeof finalImage !== 'string') {
            console.warn(`[VisualizationPanel] ⚠️ 图表 ${chartId} 的截图无效`, {
              type: typeof finalImage,
              value: finalImage,
              isNull: finalImage === null,
              isUndefined: finalImage === undefined
            })
            // 不存储无效数据，避免后续处理错误
          } else if (finalImage.length < 100) {
            // 长度太短，可能是错误信息或空数据
            console.warn(`[VisualizationPanel] ⚠️ 图表 ${chartId} 的截图长度异常（${finalImage.length}）`, {
              preview: finalImage.substring(0, 100),
              isDataUrl: finalImage.startsWith('data:image/'),
              fullValue: finalImage // 输出完整值以便调试
            })
            // 【关键修复】不存储无效数据，避免后续处理错误
            // 不存储，让后续验证逻辑过滤掉
          } else {
            results[chartId] = finalImage
            console.log(`[VisualizationPanel] ✓ 图表 ${chartId} 截图获取成功（长度: ${finalImage.length}）`)
          }

          // #region agent log
          fetch('http://127.0.0.1:7243/ingest/d7da9dc0-913c-4a71-877d-8ad5d396d494', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              sessionId: 'debug-session',
              runId: 'pre-fix',
              hypothesisId: 'H3',
              location: 'VisualizationPanel.vue:getAllChartImages',
              message: 'single_chart_result',
              data: { chartId, hasImage: !!results[chartId] },
              timestamp: Date.now()
            })
          }).catch(() => {})
          // #endregion agent log
        } catch (error) {
          console.error(`[VisualizationPanel] ❌ 获取图表 ${chartId} 截图失败:`, error)
        }
      } else {
        console.warn(`[VisualizationPanel] ⚠️ 图表 ${chartId} 没有有效的引用或方法`)
      }
    }

    console.log('[VisualizationPanel] getAllChartImages 完成，结果数量:', Object.keys(results).length)
    console.log('[VisualizationPanel] 成功获取截图的图表:', Object.keys(results).filter(k => results[k]))

    return results
  },

  // 获取图表引用（用于调试）
  getChartRefs: () => {
    return chartRefs.value
  },

  // 刷新所有图表（当面板从不可见变为可见时调用）
  refreshAllCharts: refreshAllChartsInternal
})

// 保存图表组件引用
const setChartRef = (vizId, el) => {
  if (el) {
    chartRefs.value[vizId] = el
    console.log('[VisualizationPanel] setChartRef 注册图表引用', {
      vizId,
      hasEl: !!el,
      width: el?.$el?.clientWidth || el?.clientWidth || null,
      height: el?.$el?.clientHeight || el?.clientHeight || null
    })
  }
}

// 保存地图组件引用
const setMapRef = (vizId, el) => {
  if (el) {
    mapRefs.value[vizId] = el
  }
}

// 判断是否为多专家模式
const isQuickTracingMode = computed(() => {
  const hasExpertResults = props.expertResults?.expert_results && Object.keys(props.expertResults.expert_results).length > 0
  const hasGroupedViz = store.groupedVisualizations && (
    (store.groupedVisualizations.weather?.length > 0) ||
    (store.groupedVisualizations.component?.length > 0) ||
    (store.groupedVisualizations.viz?.length > 0)
  )
  console.log('[VisualizationPanel] isQuickTracingMode检查:', {hasExpertResults, hasGroupedViz, result: hasExpertResults || hasGroupedViz})
  return hasExpertResults || hasGroupedViz
})

// 直接使用 store 中已分组的数据（优化：避免重复处理）
const groupedVisualizations = computed(() => {
  if (!isQuickTracingMode.value) return {}
  return store.groupedVisualizations
})

// 检查是否有分组数据
const hasGroupedVisualizations = computed(() => {
  const groups = groupedVisualizations.value
  return (groups.weather?.length > 0) || (groups.component?.length > 0)
})

// 获取专家标签
const getExpertLabel = (expertType) => {
  const labelMap = {
    'weather': '气象专家',
    'component': '组分分析专家',
    'default': '其他'
  }
  return labelMap[expertType] || expertType
}

// 获取表格数据行（兼容多种格式）
const getTableRows = (viz) => {
  const data = viz?.data
  if (!data) return []
  
  // 格式1: data已经是数组 [{col1: val1, col2: val2}, ...]
  if (Array.isArray(data)) {
    return data
  }
  
  // 格式2: {columns: [...], rows: [[...], [...]]} - Enhanced OBM格式
  if (data.columns && Array.isArray(data.rows)) {
    // 将二维数组转换为对象数组
    return data.rows.map(row => {
      const obj = {}
      data.columns.forEach((col, idx) => {
        obj[col] = row[idx]
      })
      return obj
    })
  }
  
  // 格式3: {rows: [...]}
  if (Array.isArray(data.rows)) {
    return data.rows
  }
  
  console.warn('[VisualizationPanel] 无法识别的表格数据格式:', data)
  return []
}

// 获取专家图标
const getExpertIcon = (expertType) => {
  const iconMap = {
    'weather': '🌤️',
    'component': '🔬',
    'default': '📋'
  }
  return iconMap[expertType] || '📋'
}

// 切换专家组的展开/收起状态
const toggleExpertGroup = (expertType) => {
  const index = expandedGroups.value.indexOf(expertType)
  if (index > -1) {
    expandedGroups.value.splice(index, 1)
  } else {
    expandedGroups.value.push(expertType)
  }
}

// 检查viz是否为静态图片（需要过滤）
const isDirectUrlImage = (viz) => {
  if (!viz) return false

  // 规则1: type === 'image' 的是静态图片
  if (viz.type === 'image') {
    console.log('[isDirectUrlImage] 过滤静态图片 (type=image):', {
      id: viz.id?.substring(0, 20),
      type: viz.type,
      title: viz.title?.substring(0, 30)
    })
    return true
  }

  // 规则2: 检查 meta.chart_type 是否为 matplotlib 生成的图表类型
  // 这些图表在左侧Markdown已通过 image_url 显示，右侧不需要重复渲染
  const matplotlibChartTypes = new Set([
    'ternary_SNA',
    'sor_nor_scatter',
    'charge_balance',
    'ec_oc_scatter',
    'crustal_boxplot',
    'ion_timeseries',
    'carbon_bar'
  ])

  const chartType = viz.meta?.chart_type || viz.type
  if (matplotlibChartTypes.has(chartType)) {
    console.log('[isDirectUrlImage] 过滤matplotlib图表 (chart_type):', {
      id: viz.id?.substring(0, 20),
      type: viz.type,
      chart_type: chartType,
      title: viz.title?.substring(0, 30)
    })
    return true
  }

  return false
}

const visualizations = computed(() => {
  let allVisualizations = []

  // 多专家模式：从 store.groupedVisualizations 获取所有图表
  if (isQuickTracingMode.value) {
    const groups = store.groupedVisualizations
    const rawVisuals = [...(groups.weather || []), ...(groups.component || []), ...(groups.viz || [])]

    // 转换payload格式：如果viz.type是通用类型（chart/image），则使用payload中的具体类型
    allVisualizations = rawVisuals.map(v => {
      if (v.payload && v.type === 'chart') {
        // 将payload数据提升到顶层，保留meta
        const transformed = { ...v.payload, meta: v.meta || v.payload.meta }
        return transformed
      }
      return v
    })
  }
  // 普通模式：从 messages 的 tool_result 事件中提取visuals
  else {
    if (props.history && Array.isArray(props.history)) {
      props.history.forEach((msg, msgIndex) => {
        // 只处理 tool_result 类型的消息
        if (msg.type !== 'tool_result') {
          return
        }

        // ✅ 检查两种格式：
        // 1. 单个工具：msg.data.result.visuals
        // 2. 多个工具：msg.data.results[].visuals
        const result = msg.data?.result
        const results = msg.data?.results

        // 格式1：单个工具 result.visuals
        if (result && result.visuals && Array.isArray(result.visuals) && result.visuals.length > 0) {
          // 兼容两种格式：
          // 1. VisualBlock格式: {payload: {...}, meta: {...}}
          // 2. 直接格式: {id, type, data, meta, ...}
          const extractedVisuals = result.visuals.map((v) => {
            if (v.payload) {
              return { ...v.payload, meta: v.meta }
            } else {
              return v
            }
          })

          allVisualizations = allVisualizations.concat(extractedVisuals)
        }

        // 格式2：多个工具 results[].visuals
        if (results && Array.isArray(results)) {
          results.forEach((r, rIdx) => {
            if (r.visuals && Array.isArray(r.visuals) && r.visuals.length > 0) {
              const extractedVisuals = r.visuals.map((v) => {
                if (v.payload) {
                  return { ...v.payload, meta: v.meta }
                } else {
                  return v
                }
              })

              allVisualizations = allVisualizations.concat(extractedVisuals)
            }
          })
        }
      })
    }
  }

  // 去重逻辑
  const seen = new Map()  // key -> viz (存储保留的可视化)
  const customChartTypes = new Set(['ternary_SNA', 'sor_nor_scatter', 'charge_balance', 'ec_oc_scatter', 'ion_timeseries', 'crustal_boxplot'])

  allVisualizations.forEach(viz => {
    if (!viz) return

    // 生成唯一key：优先使用id+title，其次使用type+title+source_data_ids
    const key = viz.id
      ? `${viz.id}_${viz.title || ''}`
      : `${viz.type || 'viz'}_${viz.title || ''}_${viz.meta?.source_data_ids?.[0] || ''}`

    const existing = seen.get(key)

    if (!existing) {
      // 首次出现，保留
      seen.set(key, viz)
    } else {
      // 已存在，检查是否需要替换
      const existingIsImage = existing.type === 'image'
      const currentIsImage = viz.type === 'image'
      const existingIsCustom = customChartTypes.has(existing.type)
      const currentIsCustom = customChartTypes.has(viz.type)

      // 替换策略：image > custom chart type
      if (currentIsImage && !existingIsImage) {
        // 当前是image，现有不是，替换
        const vizToStore = {
          ...viz,
          meta: {
            ...(viz.meta || {}),
            chartType: existing.type  // 保留原有图表类型（如 ternary_SNA）
          }
        }
        seen.set(key, vizToStore)
      } else if (currentIsImage && existingIsImage) {
        // 两者都是image，保留较新的（覆盖），但保留meta中的chartType
        const existingChartType = existing.meta?.chartType
        const vizToStore = {
          ...viz,
          meta: {
            ...(viz.meta || {}),
            chartType: existingChartType || viz.type
          }
        }
        seen.set(key, vizToStore)
      }
      // existingIsImage && currentIsCustom: 不替换
      // 其他情况：保留原有的
    }
  })

  const deduplicated = Array.from(seen.values())
  return deduplicated
})

const latestVisualization = computed(() => {
  const list = visualizations.value
  if (!list.length) return null
  return list[list.length - 1]
})

const panelTitle = computed(() => {
  return latestVisualization.value?.title || '可视化内容'
})

const visualizationPanelTitle = computed(() => {
  // 可视化部分标题（仅当有可视化时显示）
  return latestVisualization.value?.title || '可视化内容'
})

const typeLabelMap = {
  map: '地图',
  chart: '图表',
  pie: '图表',
  bar: '图表',
  line: '图表',
  timeseries: '时序',
  stacked_timeseries: '堆叠时序',
  weather_timeseries: '气象时序',
  pressure_pbl_timeseries: '气压边界层',
  facet_timeseries: '分面时序',
  radar: '雷达',
  heatmap: '热力图',
  table: '表格',
  image: '图片',
  text: '文本',
  // 颗粒物分析图表类型
  ternary_SNA: '三元图',
  sor_nor_scatter: 'SOR/NOR散点图',
  charge_balance: '电荷平衡图',
  ec_oc_scatter: 'EC/OC散点图',
  ion_timeseries: '离子时序图',
  crustal_boxplot: '地壳元素箱线图',
  polar_line: '极坐标折线图',
  polar_heatmap: '极坐标热力图',
}

const getTypeLabel = (type) => typeLabelMap[type] || '可视化'

// 判断是否为图表类型（支持动态检测 ECharts 配置）
const isChartType = (viz) => {
  // 确保 viz 是有效对象
  if (!viz || typeof viz !== 'object') {
    return false
  }

  // 安全地获取类型字符串
  const type = String(viz.type || '').toLowerCase()

  // 已知图表类型白名单
  const knownChartTypes = [
    'chart', 'pie', 'bar', 'polar_bar', 'line', 'timeseries',
    'stacked_timeseries', 'weather_timeseries', 'pressure_pbl_timeseries',
    'facet_timeseries', 'radar', 'wind_rose', 'scatter',
    'scatter3d', 'surface3d', 'line3d', 'bar3d', 'volume3d',
    'profile', 'heatmap', 'polar_line', 'polar_heatmap'
  ]

  // 如果类型在白名单中，直接返回 true
  if (knownChartTypes.includes(type)) {
    return true
  }

  // 动态检测：检查 data 是否包含有效的 ECharts 配置
  const chartData = viz.data
  if (!chartData || typeof chartData !== 'object') {
    return false
  }

  // 检测标准 ECharts 配置特征
  const hasSeries = 'series' in chartData && Array.isArray(chartData.series)

  // 极坐标图表检测（polar + angleAxis + radiusAxis + series）
  const hasPolarConfig = 'polar' in chartData &&
                        'angleAxis' in chartData &&
                        'radiusAxis' in chartData &&
                        hasSeries

  // 标准图表检测（xAxis + yAxis + series）
  const hasStandardConfig = ('xAxis' in chartData || 'xAxis3D' in chartData) &&
                           ('yAxis' in chartData || 'yAxis3D' in chartData) &&
                           hasSeries

  // 雷达图检测
  const hasRadarConfig = 'radar' in chartData && hasSeries

  // 3D图表检测
  const has3DConfig = 'grid3D' in chartData && hasSeries

  // 饼图检测
  const hasPieConfig = hasSeries && chartData.series.some(s => s.type === 'pie')

  // 如果包含任何有效配置特征，认为是图表类型
  if (hasPolarConfig || hasStandardConfig || hasRadarConfig || has3DConfig || hasPieConfig) {
    console.log('[VisualizationPanel] 动态检测到图表类型:', type, '配置特征:', {
      hasPolarConfig, hasStandardConfig, hasRadarConfig, has3DConfig, hasPieConfig
    })
    return true
  }

  return false
}

// 判断是否为轨迹地图
const isTrajectoryMap = (viz) => {
  // 检查是否包含trajectory_layer
  if (!viz.data || !viz.data.layers || !Array.isArray(viz.data.layers)) {
    return false
  }

  // 检查是否是轨迹地图：trajectory_layer OR 包含轨迹相关的图层类型
  const hasTrajectoryLayer = viz.data.layers.some(layer => layer.type === 'trajectory_layer')
  const hasTrajectoryFeatures = viz.data.layers.some(layer =>
    ['heatmap', 'polyline', 'markers', 'marker'].includes(layer.type)
  )

  return hasTrajectoryLayer || hasTrajectoryFeatures
}

// v3.1: 布局系统 - 根据layout_hint返回对应的CSS class
const getLayoutClass = (layoutHint) => {
  const layoutMap = {
    'wide': 'layout-wide',       // 全宽
    'tall': 'layout-tall',        // 双倍高度
    'map-full': 'layout-map-full', // 地图全屏
    'side': 'layout-side',        // 半宽（默认）
    'main': 'layout-main',         // 主区域
    'default': 'layout-default'    // 默认自适应
  }
  return layoutMap[layoutHint] || 'layout-default'
}

const formatTimestamp = (ts) => {
  if (!ts) return ''
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return ''
  const datePart = date.toLocaleDateString()
  const timePart = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return `${datePart} ${timePart}`
}

// 已移除脱敏限制

const onPanelReady = () => {
  // 子面板渲染完成时的占位函数
}

const reuseChart = (viz) => {
  // 复用图表：将当前图表配置复制到剪贴板
  try {
    const config = JSON.stringify(viz, null, 2)
    navigator.clipboard.writeText(config).then(() => {
      // 静默成功，不显示弹窗
    }).catch(() => {
      // 如果剪贴板API不可用，输出到控制台
      console.log('图表配置:', viz)
    })
  } catch (error) {
    console.error('复用图表失败:', error)
  }
}

const regenerateChart = async (viz) => {
  // 重新生成图表：触发重新分析
  try {
    // 获取当前对话中的查询
    const query = await getCurrentQuery()
    if (!query) {
      return
    }

    // 检查是否有source_data_ids
    if (viz.meta?.source_data_ids && viz.meta.source_data_ids.length > 0) {
      const dataId = viz.meta.source_data_ids[0]
      // 调用重新生成API
      await triggerRegenerate(query, {
        source_data_id: dataId,
        template: viz.meta.generator,
        scenario: viz.meta.scenario,
        chart_config: viz
      })
    } else {
      // 没有源数据ID，仅使用查询重新生成
      await triggerRegenerate(query, {
        template: viz.meta.generator,
        scenario: viz.meta.scenario,
        chart_config: viz
      })
    }
  } catch (error) {
    console.error('重新生成图表失败:', error)
  }
}

// 辅助函数：获取当前查询
const getCurrentQuery = async () => {
  // 从消息历史中获取最后一条用户消息
  const messages = JSON.parse(localStorage.getItem('react_messages') || '[]')
  const userMessages = messages.filter(m => m.type === 'user')
  if (userMessages.length > 0) {
    return userMessages[userMessages.length - 1].content
  }
  return null
}

// 触发重新生成
const triggerRegenerate = async (query, options) => {
  // TODO: 实现实际的重新生成API调用
  console.log('触发重新生成:', { query, options })
}

// 复制到剪贴板
const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text)
    // 静默成功
  } catch (error) {
    console.error('复制失败:', error)
  }
}

// 检查是否为有效的dataId
const isValidDataId = (dataId) => {
  return dataId && typeof dataId === 'string' && dataId.includes(':')
}

// 查看源数据
const viewSourceData = async (dataId) => {
  // TODO: 实现查看源数据的逻辑
  console.log('查看源数据:', dataId)
}

// 调试未知可视化类型
const debugUnknownViz = (viz) => {
  console.log('===== 未知可视化类型调试 =====')
  console.log('viz.type:', viz.type)
  console.log('viz.id:', viz.id)
  console.log('viz.title:', viz.title)
  console.log('viz完整结构:', JSON.stringify(viz, null, 2))
  console.log('viz.meta:', viz.meta)
  console.log('viz.data:', viz.data)
  console.log('viz.data类型:', typeof viz.data)
  console.log('viz.data?.type:', viz.data?.type)
  console.log('viz.payload:', viz.payload)
  console.log('================================')

  // 如果有 payload，打印 payload 结构
  if (viz.payload) {
    console.log('===== Payload结构 =====')
    console.log('payload.type:', viz.payload.type)
    console.log('payload完整结构:', JSON.stringify(viz.payload, null, 2))
  }

  // 如果有 meta.chart_type，打印
  if (viz.meta?.chart_type) {
    console.log('===== meta.chart_type =====')
    console.log('meta.chart_type:', viz.meta.chart_type)
  }

  alert(`未知类型: ${viz.type}\n详细结构已输出到控制台`)
}
</script>

<style lang="scss" scoped>
.viz-panel {
  width: 100%;
  min-width: 360px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-left: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fafafa;
}

.panel-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.viz-count {
  font-size: 12px;
  color: #888;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.expand-btn {
  padding: 4px 12px;
  border: 1px solid #e0e0e0;
  background: white;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: #1976d2;
    color: #1976d2;
  }
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.viz-item {
  position: relative;
  /* 移除所有边框、内边距和阴影，让图表填满整个空间 */
  border: none;
  border-radius: 0;
  padding: 0;  /* 完全移除内边距 */
  display: flex;
  flex-direction: column;
  gap: 0;
  box-shadow: none;
  flex: 0 0 auto;
  min-height: 320px;
}

// v3.1: 布局系统classes
.layout-default {
  // 默认样式（继承.viz-item）
}

.layout-wide {
  // 全宽显示，不强制高度
  width: 100%;
  /* min-height: 500px; - 移除固定高度 */

  .chart-panel {
    /* min-height: 450px; - 移除固定高度，让内容自适应 */
  }
}

.layout-tall {
  // 双倍高度，不强制高度
  /* min-height: 600px; - 移除固定高度 */

  .chart-panel {
    /* min-height: 550px; - 移除固定高度，让内容自适应 */
  }
}

.layout-map-full {
  // 地图全屏显示，不强制高度
  width: 100%;
  /* min-height: 800px; - 移除固定高度 */

  .chart-panel, .map-panel {
    /* min-height: 750px; - 移除固定高度，让内容自适应 */
  }
}

.layout-side {
  // 侧边显示（默认宽度）
  width: 100%;
}

.layout-main {
  // 主区域显示，不强制高度
  width: 100%;
  /* min-height: 450px; - 移除固定高度 */

  .chart-panel {
    /* min-height: 400px; - 移除固定高度，让内容自适应 */
  }
}

.viz-item-header {
  display: none;  /* 隐藏标题栏，图表已有标题 */
}

.viz-title {
  display: flex;
  align-items: center;
  gap: 6px;  /* 减少间距 */
  font-weight: 600;
}

.viz-type-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 6px;  /* 减少内边距 */
  background: #eef4ff;
  color: #4169e1;
  border-radius: 999px;
  font-size: 11px;  /* 减小字体 */
}

.viz-title-text {
  font-size: 13px;  /* 减小字体 */
  color: #333;
}

.viz-time {
  font-size: 11px;  /* 减小字体 */
  color: #999;
}

.viz-meta {
  display: none;  /* 隐藏元数据栏，节省空间 */
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;

  label {
    color: #666;
    font-weight: 500;
    white-space: nowrap;
  }

  span {
    color: #333;
  }
}

// UDF v2.0 新增元数据样式
.source-data-ids {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.data-id-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: #f0f8ff;
  border: 1px solid #b6d7ff;
  border-radius: 4px;
  font-size: 11px;
  color: #1976d2;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #e3f2fd;
    border-color: #64b5f6;
  }
}

.copy-btn, .view-btn {
  background: none;
  border: none;
  padding: 0 2px;
  cursor: pointer;
  font-size: 10px;
  opacity: 0.7;
  transition: opacity 0.2s;

  &:hover {
    opacity: 1;
  }
}

.generator-tag, .scenario-tag, .version-tag {
  display: inline-block;
  padding: 2px 8px;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 11px;
  color: #666;
  font-family: monospace;
}

.generator-tag {
  background: #e8f5e9;
  border-color: #c8e6c9;
  color: #2e7d32;
}

.scenario-tag {
  background: #fff3e0;
  border-color: #ffe0b2;
  color: #f57c00;
}

.version-tag {
  background: #e3f2fd;
  border-color: #bbdefb;
  color: #1976d2;
  font-weight: 600;
}

.viz-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #e0e0e0;
  background: white;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  svg {
    flex-shrink: 0;
  }
}

.reuse-btn {
  color: #1976d2;
  border-color: #1976d2;

  &:hover {
    background: #e3f2fd;
  }
}

.regenerate-btn {
  color: #2e7d32;
  border-color: #2e7d32;

  &:hover {
    background: #e8f5e9;
  }
}

.viz-debug {
  font-size: 11px;
  color: #666;

  details {
    summary {
      cursor: pointer;
      color: #666;
      user-select: none;

      &:hover {
        color: #1976d2;
      }
    }

    pre {
      margin-top: 8px;
      padding: 8px;
      background: #fff;
      border: 1px solid #e0e0e0;
      border-radius: 4px;
      max-height: 200px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
  }
}

.text-panel {
  width: 100%;
  overflow-y: auto;
  padding: 12px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}

.unknown-panel {
  padding: 12px;
  border: 1px dashed #ffc107;
  border-radius: 6px;
  color: #a67c00;
  font-size: 13px;
  background: #fffbea;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #999;
  text-align: center;
  padding: 40px 20px;
}

.empty-state svg {
  margin-bottom: 16px;
  color: #e0e0e0;
}

.empty-title {
  font-size: 16px;
  font-weight: 500;
  color: #666;
  margin: 0 0 8px 0;
}

.empty-tip {
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
}

// 多专家分组样式
.expert-groups {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.expert-group {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.expert-group-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-radius: 8px 8px 0 0;
}

.expert-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
  font-size: 16px;
  color: #333;
}

.expert-icon { font-size: 24px; }
.expert-name { color: #1976d2; }
.expert-count {
  font-size: 13px;
  color: #666;
  font-weight: normal;
}

.expert-group-actions {
  display: flex;
  gap: 8px;
}

.expert-group-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

// 专家总结样式
.expert-summary {
  margin: 0 20px 20px 20px;
  border: 1px solid #e3f2fd;
  border-radius: 8px;
  background: linear-gradient(135deg, #f3f9ff 0%, #e8f4fd 100%);
  box-shadow: 0 2px 4px rgba(25, 118, 210, 0.1);
}

.summary-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px 12px 20px;
  border-bottom: 1px solid #e3f2fd;
}

.summary-icon { font-size: 20px; }
.summary-title {
  font-weight: 600;
  color: #1976d2;
  font-size: 15px;
}

.summary-content { padding: 16px 20px; }
.summary-text {
  margin: 0 0 16px 0;
  color: #333;
  line-height: 1.6;
  font-size: 14px;
}

.key-findings {
  margin: 16px 0;
  padding: 12px;
  background: rgba(25, 118, 210, 0.05);
  border-radius: 6px;
  border-left: 3px solid #1976d2;
}

.key-findings h4 {
  margin: 0 0 8px 0;
  color: #1976d2;
  font-size: 13px;
  font-weight: 600;
}

.key-findings ul {
  margin: 0;
  padding-left: 20px;
}

.key-findings li {
  margin-bottom: 6px;
  color: #555;
  font-size: 13px;
  line-height: 1.5;
}

.summary-meta {
  display: flex;
  gap: 20px;
  padding-top: 12px;
  border-top: 1px solid #e3f2fd;
  font-size: 12px;
}

.confidence {
  color: #2e7d32;
  font-weight: 600;
}

.data-quality {
  color: #f57c00;
  font-weight: 600;
}

.expert-source-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: #fff3e0;
  color: #f57c00;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid #ffe0b2;
}

// 知识溯源面板样式
.knowledge-source-section {
  width: 100%;
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
  margin-bottom: 0;
  min-height: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-icon {
  font-size: 18px;
}

.panel-text {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.source-count {
  font-size: 12px;
  color: #666;
  background: #fff;
  padding: 2px 8px;
  border-radius: 999px;
}

.source-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.source-item {
  padding: 12px 0;
  background: transparent;
  transition: all 0.2s;

  &:hover {
    background: #f8f8f8;
  }
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.source-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.source-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: #1976d2;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.source-name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  word-break: break-word;
}

.source-meta {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.relevance-badge {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: #666;
  white-space: nowrap;
}

.source-info {
  display: flex;
  gap: 12px;
  font-size: 12px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.info-row label {
  color: #666;
  font-weight: 500;
}

.info-row span {
  color: #333;
}

.source-content {
  margin-top: 8px;
  padding: 8px 0;
}

.content-preview {
  font-size: 12px;
  line-height: 1.6;
  color: #555;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 600px;  // 增加到600px，或者移除此限制
  overflow-y: auto;
}

.viz-content-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #999;
  text-align: center;
  padding: 40px 20px;
}

.empty-state svg {
  margin-bottom: 16px;
  color: #e0e0e0;
}

.empty-title {
  font-size: 16px;
  font-weight: 500;
  color: #666;
  margin: 0 0 8px 0;
}

.empty-tip {
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
}
</style>
