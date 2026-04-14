<template>
  <div class="viz-panel" :class="{ 'has-content': visualizations.length || hasKnowledgeSources }">
    <!-- 知识溯源面板（优先显示） -->
    <KnowledgeSourcePanel
      v-if="hasKnowledgeSources"
      :sources="knowledgeSources"
      :expanded="expanded"
      @toggle-expand="toggleExpand"
    />

    <!-- 原有可视化内容 -->
    <div v-if="visualizations.length > 0" class="viz-content-section">
      <div class="panel-header">
        <div class="panel-title-group">
          <h3>{{ visualizationPanelTitle }}</h3>
          <span v-if="visualizations.length" class="viz-count">共 {{ visualizations.length }} 个结果</span>
        </div>
        <div class="header-actions">
          <!-- 导出模式按钮 -->
          <button
            v-if="visualizations.length"
            @click="toggleExportMode"
            class="export-mode-btn"
            :class="{ active: exportMode }"
            :title="exportMode ? '取消选择' : '选择导出图表'"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            {{ exportMode ? '取消' : '导出' }}
          </button>
          <button
            v-if="visualizations.length && !exportMode"
            @click="toggleExpand"
            class="expand-btn"
          >
            {{ expanded ? '收起' : '展开' }}
          </button>
        </div>
      </div>

      <!-- 可视化内容列表 -->
      <div v-if="expanded" class="panel-body">
        <div
          v-for="(viz, index) in visualizations"
          :key="viz.id || `${viz.type || 'viz'}_${index}`"
          class="viz-item"
          :class="[
            getLayoutClass(viz.meta?.layout_hint),
            { 'export-selected': exportMode && isChartSelected(viz.id || `viz_${index}`) }
          ]"
        >
          <!-- 导出模式勾选框 -->
          <div v-if="exportMode" class="export-checkbox-wrapper">
            <label class="export-checkbox">
              <input
                type="checkbox"
                :checked="isChartSelected(viz.id || `viz_${index}`)"
                @change="toggleChartSelection(viz.id || `viz_${index}`)"
              />
              <span class="checkmark"></span>
            </label>
          </div>

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
    <div v-if="!hasKnowledgeSources && visualizations.length === 0" class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M3 9h18" />
        <path d="M9 3v18" />
      </svg>
      <p class="empty-title">暂无内容</p>
      <p class="empty-tip">当生成可视化图表或检索到知识文档时，将在此处显示</p>
    </div>

    <!-- 导出预览弹窗 -->
    <ExportPreviewModal
      v-if="showExportPreview"
      :selected-charts="selectedChartsData"
      :report-content="reportContent"
      @close="closeExportPreview"
      @export-complete="handleExportComplete"
    />
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { useReactStore } from '@/stores/reactStore'
import KnowledgeSourcePanel from './visualization/panels/KnowledgeSourcePanel.vue'
import MapPanel from './visualization/MapPanel.vue'
import TrajectoryMapPanel from './visualization/TrajectoryMapPanel.vue'
import ChartPanel from './visualization/ChartPanel.vue'
import DataTable from './visualization/DataTable.vue'
import ImagePanel from './visualization/ImagePanel.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ExportPreviewModal from './ExportPreviewModal.vue'

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

const expanded = ref(true)
const expandedGroups = ref(['weather', 'component'])

// ==================== 导出功能状态 ====================
const exportMode = ref(false)              // 是否处于导出选择模式
const selectedChartIds = ref([])           // 选中的图表ID列表
const showExportPreview = ref(false)       // 是否显示导出预览弹窗
const chartRefs = ref({})                  // 图表组件引用（用于获取状态）
const mapRefs = ref({})                    // 地图组件引用

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

// 切换导出模式
const toggleExportMode = () => {
  exportMode.value = !exportMode.value
  if (!exportMode.value) {
    selectedChartIds.value = []
  }
}

// 图表选择切换
const toggleChartSelection = (vizId) => {
  const index = selectedChartIds.value.indexOf(vizId)
  if (index > -1) {
    selectedChartIds.value.splice(index, 1)
  } else {
    selectedChartIds.value.push(vizId)
  }
}

// 检查图表是否被选中
const isChartSelected = (vizId) => {
  return selectedChartIds.value.includes(vizId)
}

// 全选/取消全选
const toggleSelectAll = () => {
  if (selectedChartIds.value.length === visualizations.value.length) {
    selectedChartIds.value = []
  } else {
    selectedChartIds.value = visualizations.value.map((v, i) => v.id || `viz_${i}`)
  }
}

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

// 收集选中图表的完整数据（包含用户交互状态）- 异步版本支持地图截图
const selectedChartsData = ref([])

// 异步收集所有选中图表的数据和截图
const collectChartsData = async () => {
  const results = []
  
  for (const vizId of selectedChartIds.value) {
    const index = visualizations.value.findIndex((v, i) => (v.id || `viz_${i}`) === vizId)
    if (index === -1) continue
    
    const viz = visualizations.value[index]
    
    // 获取图表当前用户状态和截图
    let chartState = null
    let chartImage = null
    
    const chartRef = chartRefs.value[vizId]
    if (chartRef) {
      // 获取状态
      if (typeof chartRef.getChartState === 'function') {
        chartState = chartRef.getChartState()
      }
      // 获取截图（支持异步，如地图）
      if (typeof chartRef.getChartImage === 'function') {
        const imageResult = chartRef.getChartImage()
        // 如果是 Promise，等待结果
        if (imageResult instanceof Promise) {
          chartImage = await imageResult
        } else {
          chartImage = imageResult
        }
      }
    }
    
    results.push({
      ...viz,
      vizId: vizId,
      userState: chartState,
      previewImage: chartImage
    })
  }
  
  selectedChartsData.value = results
}

// 获取报告内容（从expertResults中提取）
const reportContent = computed(() => {
  if (props.expertResults?.expert_results?.report) {
    const reportResult = props.expertResults.expert_results.report
    if (reportResult.tool_results && reportResult.tool_results.length > 0) {
      return reportResult.tool_results[0].result
    }
  }
  return null
})

// 打开导出预览（异步收集图表截图后再显示）
const openExportPreview = async () => {
  // 先收集所有图表数据和截图（包括地图的异步截图）
  await collectChartsData()
  showExportPreview.value = true
}

// 关闭导出预览
const closeExportPreview = () => {
  showExportPreview.value = false
}

// 导出完成后的处理
const handleExportComplete = () => {
  showExportPreview.value = false
  exportMode.value = false
  selectedChartIds.value = []
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

  console.log('[VisualizationPanel] visualizations计算触发', {
    isQuickTracingMode: isQuickTracingMode.value,
    hasGroupedViz: !!(store.groupedVisualizations),
    hasContent: !!(props.content),
    hasContentVisuals: !!(props.content?.visuals),
    groupedVizKeys: store.groupedVisualizations ? Object.keys(store.groupedVisualizations) : [],
    groupedVizCounts: store.groupedVisualizations ? {
      weather: store.groupedVisualizations.weather?.length || 0,
      component: store.groupedVisualizations.component?.length || 0,
      viz: store.groupedVisualizations.viz?.length || 0
    } : {}
  })

  // 多专家模式：从 store.groupedVisualizations 获取所有图表
  if (isQuickTracingMode.value) {
    const groups = store.groupedVisualizations
    const rawVisuals = [...(groups.weather || []), ...(groups.component || []), ...(groups.viz || [])]
    console.log('[VisualizationPanel] 快速溯源模式 - 原始可视化数量:', rawVisuals.length)
    console.log('[VisualizationPanel] 原始可视化类型:', rawVisuals.map(v => ({id: v.id, type: v.type, hasPayload: !!v.payload})))

    // 转换payload格式：如果viz.type是通用类型（chart/image），则使用payload中的具体类型
    allVisualizations = rawVisuals.map(v => {
      if (v.payload && v.type === 'chart') {
        // 将payload数据提升到顶层，保留meta
        const transformed = { ...v.payload, meta: v.meta || v.payload.meta }
        console.log('[VisualizationPanel] 转换chart payload:', {id: v.id, oldType: v.type, newType: transformed.type})
        return transformed
      }
      return v
    })
    console.log('[VisualizationPanel] 转换后可视化类型:', allVisualizations.map(v => ({id: v.id, type: v.type})))
  }
  // 普通模式：从 props.content 和 props.history 获取所有可视化对象
  else {
    // 1. 从当前消息的 visuals 获取
    if (props.content) {
      if (props.content?.visuals && Array.isArray(props.content.visuals)) {
        console.log('[VisualizationPanel] 普通模式 - 从content.visuals获取，数量:', props.content.visuals.length)
        // 兼容两种格式：
        // 1. VisualBlock格式: {payload: {...}, meta: {...}}
        // 2. 直接格式: {id, type, data, meta, ...} (如EKMA专业图表)
        const currentVisuals = props.content.visuals.map((v) => {
          if (v.payload) {
            // VisualBlock格式
            return { ...v.payload, meta: v.meta }
          } else {
            // 直接格式（EKMA专业图表等）
            return v
          }
        })
        allVisualizations = allVisualizations.concat(currentVisuals)
      } else {
        console.log('[VisualizationPanel] 普通模式 - content.visuals不是数组，使用content本身')
        allVisualizations = allVisualizations.concat([props.content])
      }
    }

    // 2. 从历史消息中收集所有图表（按时间顺序）
    if (props.history && Array.isArray(props.history)) {
      console.log('[VisualizationPanel] 开始从历史消息收集图表，历史消息数量:', props.history.length)

      let foundCount = 0
      props.history.forEach((msg, msgIndex) => {
        // 只处理 observation 类型的消息（图表在observation中）
        const msgType = msg.role || msg.type
        if (msgType !== 'observation') return

        // 检查消息的 data.observation.visuals（正确路径）
        const obs = msg.data?.observation
        if (!obs) return

        const visuals = obs.visuals
        if (visuals && Array.isArray(visuals) && visuals.length > 0) {
          console.log(`[VisualizationPanel] 从历史消息[${msgIndex}]获取图表，数量:`, visuals.length, '消息ID:', msg.id)
          foundCount += visuals.length
          const historyVisuals = visuals.map((v) => {
            if (v.payload) {
              return { ...v.payload, meta: v.meta }
            } else {
              return v
            }
          })
          allVisualizations = allVisualizations.concat(historyVisuals)
        }
      })
      console.log('[VisualizationPanel] 历史消息收集完成，找到图表数量:', foundCount, '当前图表总数:', allVisualizations.length)
    } else {
      console.log('[VisualizationPanel] 历史消息不可用:', {
        hasHistory: !!props.history,
        isArray: Array.isArray(props.history),
        length: props.history?.length
      })
    }
  }

  console.log('[VisualizationPanel] 过滤前的可视化数量:', allVisualizations.length)

  // 注释掉过滤逻辑，允许所有图片在右侧面板显示
  // allVisualizations = allVisualizations.filter(viz => !isDirectUrlImage(viz))

  // 【关键修复】优先保留 type=image 的去重逻辑
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
      // 【关键修复】保留原始图表类型（用于报告匹配），但用image类型渲染
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
            chartType: existingChartType || viz.type  // 保留已有的chartType
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

// ✅ 知识溯源相关computed属性
const hasKnowledgeSources = computed(() => {
  // 1. 优先检查选中消息的sources字段
  if (props.selectedMessageId && props.history && props.history.length > 0) {
    const selectedMsg = props.history.find(msg => msg.id === props.selectedMessageId)
    if (selectedMsg) {
      // 检查data.sources字段
      if (selectedMsg?.data?.sources && Array.isArray(selectedMsg.data.sources) && selectedMsg.data.sources.length > 0) {
        return true
      }
      // 兼容旧格式：直接在msg上的sources字段
      if (selectedMsg?.sources && Array.isArray(selectedMsg.sources) && selectedMsg.sources.length > 0) {
        return true
      }
    }
  }

  // 2. 检查最后一条消息的sources字段
  if (props.history && props.history.length > 0) {
    const lastMsg = props.history[props.history.length - 1]
    // 检查data.sources字段
    if (lastMsg?.data?.sources && Array.isArray(lastMsg.data.sources) && lastMsg.data.sources.length > 0) {
      return true
    }
    // 兼容旧格式：直接在msg上的sources字段
    if (lastMsg?.sources && Array.isArray(lastMsg.sources) && lastMsg.sources.length > 0) {
      return true
    }
  }

  // 3. 检查content.visuals中的knowledge_source类型
  if (props.content?.visuals && Array.isArray(props.content.visuals)) {
    const hasKnowledgeSourceVisuals = props.content.visuals.some(v => v.type === 'knowledge_source')
    if (hasKnowledgeSourceVisuals) {
      return true
    }
  }

  return false
})

const knowledgeSources = computed(() => {
  let sources = []

  // 1. 优先从选中消息的data.sources获取
  if (props.selectedMessageId && props.history && props.history.length > 0) {
    const selectedMsg = props.history.find(msg => msg.id === props.selectedMessageId)
    if (selectedMsg) {
      if (selectedMsg?.data?.sources && Array.isArray(selectedMsg.data.sources)) {
        sources = selectedMsg.data.sources
      }
      // 兼容旧格式：直接在msg上的sources字段
      else if (selectedMsg?.sources && Array.isArray(selectedMsg.sources)) {
        sources = selectedMsg.sources
      }
    }
  }

  // 2. 如果没有选中的消息，从最后一条消息的data.sources获取
  if (sources.length === 0 && props.history && props.history.length > 0) {
    const lastMsg = props.history[props.history.length - 1]
    if (lastMsg?.data?.sources && Array.isArray(lastMsg.data.sources)) {
      sources = lastMsg.data.sources
    }
    // 兼容旧格式：直接在msg上的sources字段
    else if (lastMsg?.sources && Array.isArray(lastMsg.sources)) {
      sources = lastMsg.sources
    }
  }

  // 3. 如果还没有sources，尝试从content.visuals中提取knowledge_source类型
  if (sources.length === 0 && props.content?.visuals && Array.isArray(props.content.visuals)) {
    const knowledgeVisuals = props.content.visuals
      .filter(v => v.type === 'knowledge_source')
      .map((v, index) => ({
        title: v.title || '未知标题',
        document_name: v.title || '未知标题',
        source: v.data?.source || '未知来源',
        knowledge_base_name: v.data?.source || '未知来源',
        relevance: v.data?.relevance || 0,
        score: v.data?.relevance || 0,
        chunk_index: v.data?.chunk_index,
        document_id: v.data?.document_id,
        knowledge_base_id: v.data?.knowledge_base_id,
        content: v.data?.content || ''
      }))
    sources = knowledgeVisuals
  }

  return sources
})

const latestVisualization = computed(() => {
  const list = visualizations.value
  if (!list.length) return null
  return list[list.length - 1]
})

const panelTitle = computed(() => {
  // 主面板标题：优先显示知识溯源
  if (hasKnowledgeSources.value) {
    return '知识溯源'
  }
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

const toggleExpand = () => {
  expanded.value = !expanded.value
}

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

// ==================== 导出功能样式 ====================
.export-mode-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1px solid #e0e0e0;
  background: white;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  color: #666;

  &:hover {
    border-color: #1976d2;
    color: #1976d2;
    background: #e3f2fd;
  }

  &.active {
    border-color: #f44336;
    color: #f44336;
    background: #ffebee;
  }
}

.select-all-btn {
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

.export-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 14px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &.primary {
    background: #1976d2;
    color: white;

    &:hover {
      background: #1565c0;
    }
  }
}

.export-checkbox-wrapper {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 10;
}

.export-checkbox {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  cursor: pointer;

  input {
    width: 18px;
    height: 18px;
    cursor: pointer;
    accent-color: #1976d2;
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

  &.export-selected {
    border-color: #1976d2;
    background: #f3f8ff;
    box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.2);
  }
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
