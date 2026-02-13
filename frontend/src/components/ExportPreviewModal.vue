<template>
  <div class="export-modal-overlay" @click.self="$emit('close')">
    <div class="export-modal">
      <div class="modal-header">
        <h2>导出分析报告</h2>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>
      
      <div class="modal-body">
        <!-- 预览区域 -->
        <div class="preview-container">
          <div class="a4-preview" ref="previewRef">
            <!-- 封面 -->
            <div class="report-header section cover-section">
              <h1>{{ reportTitle }}</h1>
              <p class="report-meta">
                生成时间：{{ formatDate(new Date()) }}
              </p>
              <p v-if="summary" class="subtitle">（摘要见下）</p>
            </div>
            
            <!-- 摘要 -->
            <div v-if="summary" class="section">
              <h2>执行摘要</h2>
              <div class="summary-content" v-html="summaryHtml"></div>
            </div>
            
            <!-- 结论与建议 -->
            <div v-if="conclusions.length || recommendations.length" class="section">
              <h2>结论与建议</h2>
              <div v-if="conclusions.length" class="conclusions">
                <h3>主要结论</h3>
                <ul>
                  <li v-for="(c, i) in conclusions" :key="i">{{ c }}</li>
                </ul>
              </div>
              <div v-if="recommendations.length" class="recommendations">
                <h3>控制建议</h3>
                <ul>
                  <li v-for="(r, i) in recommendations" :key="i">{{ r }}</li>
                </ul>
              </div>
            </div>
            
            <div class="page-break" />
            
            <!-- 气象分析 -->
            <div v-if="groupedCharts.weather.length" class="section">
              <h2>气象分析</h2>
              <div class="charts-grid">
                <div
                  v-for="(chart, index) in groupedCharts.weather"
                  :key="chart.vizId || chart.id || index"
                  class="chart-preview-item full-width"
                  draggable="true"
                  @dragstart="onDragStart(getOrderedIndex(chart, index), $event)"
                  @dragover.prevent
                  @drop="onDrop(getOrderedIndex(chart, index))"
                >
                  <div class="chart-drag-handle" title="拖拽调整顺序">
                    <span>⋮⋮</span>
                  </div>
                  <img
                    v-if="chart.previewImage"
                    :src="chart.previewImage"
                    :alt="chart.title"
                    class="chart-image"
                  />
                  <div v-else class="chart-placeholder">
                    <span>{{ chart.title || '图表' }}</span>
                    <small>({{ chart.type }})</small>
                  </div>
                  <p class="chart-caption">图 {{ getDisplayIndex(chart, index) }}：{{ chart.title || '分析图表' }}</p>
                  <div v-if="hasUserState(chart)" class="state-indicator">
                    <span v-if="chart.userState?.dataZoom?.length" class="state-tag">
                      已调整范围
                    </span>
                    <span v-if="hasHiddenLegend(chart)" class="state-tag">
                      已隐藏指标
                    </span>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- 组分分析 -->
            <div v-if="groupedCharts.component.length" class="section">
              <h2>组分分析</h2>
              <div class="charts-grid">
                <div
                  v-for="(chart, index) in groupedCharts.component"
                  :key="chart.vizId || chart.id || index"
                  class="chart-preview-item full-width"
                  draggable="true"
                  @dragstart="onDragStart(getOrderedIndex(chart, index), $event)"
                  @dragover.prevent
                  @drop="onDrop(getOrderedIndex(chart, index))"
                >
                  <div class="chart-drag-handle" title="拖拽调整顺序">
                    <span>⋮⋮</span>
                  </div>
                  <img
                    v-if="chart.previewImage"
                    :src="chart.previewImage"
                    :alt="chart.title"
                    class="chart-image"
                  />
                  <div v-else class="chart-placeholder">
                    <span>{{ chart.title || '图表' }}</span>
                    <small>({{ chart.type }})</small>
                  </div>
                  <p class="chart-caption">图 {{ getDisplayIndex(chart, index) }}：{{ chart.title || '分析图表' }}</p>
                  <div v-if="hasUserState(chart)" class="state-indicator">
                    <span v-if="chart.userState?.dataZoom?.length" class="state-tag">
                      已调整范围
                    </span>
                    <span v-if="hasHiddenLegend(chart)" class="state-tag">
                      已隐藏指标
                    </span>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- 其他分析 -->
            <div v-if="groupedCharts.other.length" class="section">
              <h2>其他分析图表</h2>
              <div class="charts-grid">
                <div
                  v-for="(chart, index) in groupedCharts.other"
                  :key="chart.vizId || chart.id || index"
                  class="chart-preview-item full-width"
                  draggable="true"
                  @dragstart="onDragStart(getOrderedIndex(chart, index), $event)"
                  @dragover.prevent
                  @drop="onDrop(getOrderedIndex(chart, index))"
                >
                  <div class="chart-drag-handle" title="拖拽调整顺序">
                    <span>⋮⋮</span>
                  </div>
                  <img
                    v-if="chart.previewImage"
                    :src="chart.previewImage"
                    :alt="chart.title"
                    class="chart-image"
                  />
                  <div v-else class="chart-placeholder">
                    <span>{{ chart.title || '图表' }}</span>
                    <small>({{ chart.type }})</small>
                  </div>
                  <p class="chart-caption">图 {{ getDisplayIndex(chart, index) }}：{{ chart.title || '分析图表' }}</p>
                  <div v-if="hasUserState(chart)" class="state-indicator">
                    <span v-if="chart.userState?.dataZoom?.length" class="state-tag">
                      已调整范围
                    </span>
                    <span v-if="hasHiddenLegend(chart)" class="state-tag">
                      已隐藏指标
                    </span>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- 详细分析内容 -->
            <div v-if="detailContent" class="section">
              <h2>详细分析</h2>
              <div class="detail-content" v-html="detailHtml"></div>
            </div>
            
            <!-- 页脚 -->
            <div class="report-footer">
              <p>本报告由大气污染溯源分析系统自动生成</p>
            </div>
          </div>
        </div>
        
        <!-- 侧边栏：导出选项 -->
        <div class="export-options">
          <h3>导出设置</h3>
          
          <!-- 格式选择 -->
          <div class="option-group">
            <label class="option-label">导出格式</label>
            <div class="format-radios">
              <label class="format-option" :class="{ selected: exportFormat === 'pdf' }">
                <input type="radio" v-model="exportFormat" value="pdf" />
                <span class="format-icon">📄</span>
                <span class="format-name">PDF</span>
                <span class="format-desc">推荐</span>
              </label>
              <label class="format-option" :class="{ selected: exportFormat === 'docx' }">
                <input type="radio" v-model="exportFormat" value="docx" />
                <span class="format-icon">📝</span>
                <span class="format-name">Word</span>
                <span class="format-desc">可编辑</span>
              </label>
              <label class="format-option" :class="{ selected: exportFormat === 'html' }">
                <input type="radio" v-model="exportFormat" value="html" />
                <span class="format-icon">🌐</span>
                <span class="format-name">HTML</span>
                <span class="format-desc">网页</span>
              </label>
            </div>
          </div>
          
          <!-- 图表数量提示 -->
          <div class="option-group">
            <label class="option-label">已选图表</label>
            <div class="chart-count-info">
              <span class="count">{{ exportCharts.length }}</span> / {{ selectedCharts.length }} 个
              <small>勾选控制导出范围，拖拽左侧卡片可调整顺序</small>
            </div>
          </div>
          
          <!-- 图表勾选 -->
          <div class="option-group">
            <label class="option-label">图表选择</label>
            <div class="chart-select-list">
              <label
                v-for="(chart, idx) in orderedCharts"
                :key="chart.id || chart.vizId || idx"
                class="chart-select-item"
              >
                <input
                  type="checkbox"
                  :checked="isChartSelected(chart, idx)"
                  @change="toggleChartSelection(chart.id || chart.vizId || idx)"
                />
                <span class="order-num">{{ idx + 1 }}</span>
                <span class="chart-title">{{ chart.title || '图表' }}</span>
                <span class="chart-tag">{{ getChartCategory(chart) === 'weather' ? '气象' : getChartCategory(chart) === 'component' ? '组分' : '其他' }}</span>
              </label>
            </div>
          </div>
          
          <!-- 导出按钮 -->
          <div class="export-actions">
            <button 
              class="action-btn primary"
              :disabled="exporting || selectedCharts.length === 0"
              @click="doExport"
            >
              <span v-if="exporting" class="loading-icon">⏳</span>
              {{ exporting ? '导出中...' : '确认导出' }}
            </button>
            <button class="action-btn secondary" @click="$emit('close')">
              取消
            </button>
          </div>
          
          <!-- 导出提示 -->
          <div class="export-tips">
            <p>提示：</p>
            <ul>
              <li>图表将保持您当前的显示状态</li>
              <li>PDF格式适合打印和分享</li>
              <li>Word格式可进行二次编辑</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { exportReportApi } from '@/services/exportApi'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt()

const props = defineProps({
  selectedCharts: {
    type: Array,
    required: true
  },
  reportContent: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'export-complete'])

const exportFormat = ref('pdf')
const exporting = ref(false)
const dragIndex = ref(null)
const previewRef = ref(null)
const selectedChartIds = ref(new Set())

// 图表顺序（可拖拽调整）
const chartOrder = ref([])

// 初始化图表顺序与勾选状态
if (props.selectedCharts.length > 0 && chartOrder.value.length === 0) {
  chartOrder.value = props.selectedCharts.map((_, i) => i)
}
if (selectedChartIds.value.size === 0) {
  props.selectedCharts.forEach((c, i) => {
    selectedChartIds.value.add(c.id || c.vizId || i)
  })
}

// 同步勾选状态（当传入图表变化）
watch(
  () => props.selectedCharts,
  (charts) => {
    charts.forEach((c, i) => {
      const key = c.id || c.vizId || i
      if (!selectedChartIds.value.has(key)) {
        selectedChartIds.value.add(key)
      }
    })
  },
  { deep: true }
)

// 按顺序排列的图表
const orderedCharts = computed(() => {
  const charts = chartOrder.value.length === 0
    ? props.selectedCharts
    : chartOrder.value.map(i => props.selectedCharts[i]).filter(Boolean)

  return charts.map(c => {
    const isImage = c.type === 'image'
    const isMap = c.type === 'map'

    // 地图截图兜底：使用 data.snapshot / data.image / data.snapshotUrl
    const mapFallback =
      (isMap && c.data && (c.data.snapshot || c.data.image || c.data.snapshotUrl)) ||
      null

    const previewImage =
      c.previewImage ||
      (isImage ? c.data : null) ||
      mapFallback

    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/d7da9dc0-913c-4a71-877d-8ad5d396d494',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId:'debug-session',runId:'run1',hypothesisId:'H5',location:'ExportPreviewModal.vue:orderedCharts',message:'chart mapping',data:{type:c.type,title:c.title,hasPreview:!!c.previewImage,hasData:!!c.data,hasFallback:!!mapFallback,finalHas:!!previewImage},timestamp:Date.now()})}).catch(()=>{})
    // #endregion

    return {
      ...c,
      previewImage
    }
  })
})

// 勾选后的图表
const exportCharts = computed(() => {
  return orderedCharts.value.filter((chart, idx) => {
    const key = chart.id || chart.vizId || idx
    return selectedChartIds.value.has(key)
  })
})

// chart 索引映射（用于拖拽）
const chartIndexMap = computed(() => {
  const map = new Map()
  orderedCharts.value.forEach((c, i) => {
    map.set(c.id || c.vizId || i, i)
  })
  return map
})

const getOrderedIndex = (chart, fallbackIndex) => {
  return chartIndexMap.value.get(chart.id || chart.vizId || fallbackIndex) ?? fallbackIndex
}

// 报告标题
const reportTitle = computed(() => {
  return props.reportContent?.title || '大气污染溯源分析报告'
})

// 置信度
const confidence = computed(() => {
  const conf = props.reportContent?.confidence
  if (typeof conf === 'number') {
    return conf > 1 ? conf : Math.round(conf * 100)
  }
  return 85
})

// 摘要
const summary = computed(() => {
  return props.reportContent?.summary || ''
})

const summaryHtml = computed(() => {
  if (!summary.value) return ''
  return md.render(summary.value)
})

// 详细内容
const detailContent = computed(() => {
  const sections = props.reportContent?.sections
  if (sections && sections.length > 0) {
    return sections[0]?.markdown_content || ''
  }
  return ''
})

// 详细内容HTML
const detailHtml = computed(() => {
  if (!detailContent.value) return ''
  return md.render(detailContent.value)
})

// 结论
const conclusions = computed(() => {
  return props.reportContent?.conclusions || []
})

// 建议
const recommendations = computed(() => {
  return props.reportContent?.recommendations || []
})

// 图表分组（与后端保持一致）
const getChartCategory = (chart) => {
  const meta = chart.meta || {}
  const expertTag = String(
    meta.expert ||
    meta.generator ||
    meta.scenario ||
    meta.data_source ||
    ''
  ).toLowerCase()
  if (expertTag.includes('weather') || String(meta.expert || '').includes('气象')) {
    return 'weather'
  }
  if (expertTag.includes('component') || String(meta.expert || '').includes('组分')) {
    return 'component'
  }
  return 'other'
}

const groupedCharts = computed(() => {
  const result = { weather: [], component: [], other: [] }
  exportCharts.value.forEach((chart, index) => {
    const category = getChartCategory(chart)
    result[category].push({ ...chart, _orderedIndex: getOrderedIndex(chart, index) })
  })
  return result
})

const displayIndexMap = computed(() => {
  const map = new Map()
  exportCharts.value.forEach((chart, idx) => {
    map.set(chart.id || chart.vizId || idx, idx + 1)
  })
  return map
})

const getDisplayIndex = (chart, fallbackIndex) => {
  return displayIndexMap.value.get(chart.id || chart.vizId || fallbackIndex) ?? fallbackIndex + 1
}

const toggleChartSelection = (chartKey) => {
  const next = new Set(selectedChartIds.value)
  if (next.has(chartKey)) {
    next.delete(chartKey)
  } else {
    next.add(chartKey)
  }
  selectedChartIds.value = next
}

const isChartSelected = (chart, idx) => {
  const key = chart.id || chart.vizId || idx
  return selectedChartIds.value.has(key)
}

// 检查是否有用户状态
const hasUserState = (chart) => {
  return chart.userState && (
    (chart.userState.dataZoom?.length > 0 && 
     chart.userState.dataZoom.some(dz => dz.start > 0 || dz.end < 100)) ||
    Object.keys(chart.userState.legendSelected || {}).length > 0
  )
}

// 检查是否有隐藏的legend
const hasHiddenLegend = (chart) => {
  const selected = chart.userState?.legendSelected || {}
  return Object.values(selected).some(v => v === false)
}

// 图表尺寸类
const getChartSizeClass = (chart) => {
  if (chart.type === 'map') return 'full-width'
  if (chart.type === 'heatmap') return 'full-width'
  if (chart.type === 'timeseries') return 'full-width'
  return 'half-width'
}

// 拖拽开始
const onDragStart = (index, event) => {
  dragIndex.value = index
  event.dataTransfer.effectAllowed = 'move'
}

// 拖拽放下
const onDrop = (targetIndex) => {
  if (dragIndex.value === null || dragIndex.value === targetIndex) return
  
  const newOrder = [...chartOrder.value]
  if (newOrder.length === 0) {
    // 初始化顺序
    for (let i = 0; i < props.selectedCharts.length; i++) {
      newOrder.push(i)
    }
  }
  
  const [moved] = newOrder.splice(dragIndex.value, 1)
  newOrder.splice(targetIndex, 0, moved)
  chartOrder.value = newOrder
  dragIndex.value = null
}

// 执行导出
const doExport = async () => {
  exporting.value = true
  
  try {
    const exportData = {
      format: exportFormat.value,
      report_content: props.reportContent,
      charts: exportCharts.value.map((chart, index) => ({
        id: chart.id || chart.vizId,
        type: chart.type,
        title: chart.title,
        data: chart.data,
        meta: chart.meta,
        user_state: chart.userState,
        preview_image: chart.previewImage,  // 前端截图直接传递
        order: index
      }))
    }
    
    const result = await exportReportApi(exportData)
    const { blob, fallback, originalFormat } = result
    
    // 检查是否发生了格式降级
    if (fallback && originalFormat === 'pdf') {
      alert('提示：PDF导出暂不可用，已自动降级为HTML格式。\n您可以在浏览器中打开HTML文件，然后使用Ctrl+P打印为PDF。')
    }
    
    // 下载文件
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const ext = fallback || (exportFormat.value === 'docx' ? 'docx' : exportFormat.value)
    a.download = `溯源分析报告_${formatDate(new Date())}.${ext}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    
    emit('export-complete')
  } catch (error) {
    console.error('导出失败:', error)
    alert('导出失败: ' + (error.message || '请重试'))
  } finally {
    exporting.value = false
  }
}

// 格式化日期
const formatDate = (date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}${month}${day}`
}
</script>

<style lang="scss" scoped>
.export-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.export-modal {
  background: white;
  border-radius: 12px;
  width: 90vw;
  max-width: 1200px;
  height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fafafa;
  
  h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: #333;
  }
  
  .close-btn {
    background: none;
    border: none;
    font-size: 28px;
    cursor: pointer;
    color: #666;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    transition: all 0.2s;
    
    &:hover {
      background: #eee;
      color: #333;
    }
  }
}

.modal-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.preview-container {
  flex: 1;
  padding: 24px;
  overflow: auto;
  background: #e8e8e8;
}

.a4-preview {
  background: white;
  width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  padding: 25mm 20mm;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  font-family: "SimSun", "Microsoft YaHei", sans-serif;
  font-size: 12pt;
  line-height: 1.8;
}

.section {
  margin: 26px 0;
  page-break-inside: avoid;
}

.page-break {
  margin: 32px 0;
  border-top: 1px dashed #ddd;
  page-break-after: always;
}

.report-header {
  text-align: center;
  border-bottom: 2px solid #1976d2;
  padding-bottom: 20px;
  margin-bottom: 30px;
  
  h1 {
    font-size: 22pt;
    color: #1976d2;
    margin: 0 0 12px 0;
  }
  
  .report-meta {
    color: #666;
    font-size: 10pt;
    margin: 0;
  }

  .subtitle {
    color: #888;
    font-size: 10pt;
    margin: 6px 0 0 0;
  }
}

.report-section {
  margin: 30px 0;
  
  h2 {
    font-size: 14pt;
    color: #1976d2;
    border-left: 4px solid #1976d2;
    padding-left: 12px;
    margin: 0 0 16px 0;
  }
  
  h3 {
    font-size: 12pt;
    color: #333;
    margin: 16px 0 8px 0;
  }
}

.summary-content, .detail-content {
  color: #333;
  
  :deep(p) {
    margin: 8px 0;
    text-align: justify;
  }
  
  :deep(ul), :deep(ol) {
    padding-left: 24px;
  }
  
  :deep(li) {
    margin: 4px 0;
  }
}

.charts-section {
  margin: 30px 0;
  
  h2 {
    font-size: 14pt;
    color: #1976d2;
    border-left: 4px solid #1976d2;
    padding-left: 12px;
    margin: 0 0 16px 0;
  }
}

.charts-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.chart-preview-item {
  position: relative;
  background: #fafafa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px;
  cursor: grab;
  transition: all 0.2s;
  
  &:hover {
    border-color: #1976d2;
    box-shadow: 0 2px 8px rgba(25, 118, 210, 0.2);
  }
  
  &.half-width {
    width: calc(50% - 8px);
  }
  
  &.full-width {
    width: 100%;
  }
  
  &.half-width {
    width: calc(50% - 8px);
  }
  
  .chart-drag-handle {
    position: absolute;
    top: 8px;
    right: 8px;
    color: #999;
    font-size: 14px;
    cursor: grab;
    padding: 4px;
    
    &:hover {
      color: #1976d2;
    }
  }
  
  .chart-image {
    width: 100%;
    height: auto;
    border-radius: 4px;
    background: white;
  }
  
  .chart-placeholder {
    width: 100%;
    height: 150px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #f5f5f5;
    border-radius: 4px;
    color: #999;
    
    small {
      font-size: 10px;
      margin-top: 4px;
    }
  }
  
  .chart-caption {
    text-align: center;
    font-size: 10pt;
    color: #666;
    margin: 10px 0 0 0;
  }
  
  .state-indicator {
    display: flex;
    gap: 6px;
    justify-content: center;
    margin-top: 8px;
    
    .state-tag {
      font-size: 9px;
      background: #e3f2fd;
      color: #1976d2;
      padding: 2px 8px;
      border-radius: 10px;
    }
  }
}

.conclusions, .recommendations {
  margin: 16px 0;
  
  ul {
    padding-left: 24px;
    margin: 8px 0;
  }
  
  li {
    margin: 6px 0;
    color: #333;
  }
}

.report-footer {
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid #ddd;
  text-align: center;
  
  p {
    font-size: 10pt;
    color: #999;
    margin: 0;
  }
}

// 侧边栏
.export-options {
  width: 280px;
  background: #fafafa;
  border-left: 1px solid #eee;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  
  h3 {
    margin: 0 0 20px 0;
    font-size: 16px;
    font-weight: 600;
    color: #333;
  }
}

.option-group {
  margin-bottom: 24px;
  
  .option-label {
    display: block;
    font-weight: 500;
    margin-bottom: 12px;
    font-size: 14px;
    color: #333;
  }
}

.format-radios {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.format-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
  
  &:hover {
    border-color: #1976d2;
    background: #f8fbff;
  }
  
  &.selected {
    border-color: #1976d2;
    background: #e3f2fd;
  }
  
  input {
    display: none;
  }
  
  .format-icon {
    font-size: 20px;
  }
  
  .format-name {
    font-weight: 500;
    color: #333;
  }
  
  .format-desc {
    margin-left: auto;
    font-size: 11px;
    color: #888;
  }
}

.chart-count-info {
  background: white;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  
  .count {
    font-size: 24px;
    font-weight: 600;
    color: #1976d2;
    margin-right: 4px;
  }
  
  small {
    display: block;
    margin-top: 6px;
    font-size: 11px;
    color: #888;
  }
}

.chart-select-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 280px;
  overflow: auto;
}

.chart-select-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: white;
}

.chart-select-item input {
  accent-color: #1976d2;
}

.chart-select-item .order-num {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: #e3f2fd;
  color: #1976d2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 12px;
}

.chart-select-item .chart-title {
  flex: 1;
  color: #333;
  font-size: 13px;
}

.chart-select-item .chart-tag {
  font-size: 11px;
  color: #666;
  padding: 2px 6px;
  background: #f5f5f5;
  border-radius: 6px;
}

.export-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: auto;
  padding-top: 20px;
}

.action-btn {
  padding: 14px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  
  &.primary {
    background: #1976d2;
    color: white;
    border: none;
    
    &:hover:not(:disabled) {
      background: #1565c0;
    }
    
    &:disabled {
      background: #ccc;
      cursor: not-allowed;
    }
  }
  
  &.secondary {
    background: white;
    color: #666;
    border: 1px solid #ddd;
    
    &:hover {
      background: #f5f5f5;
      border-color: #ccc;
    }
  }
  
  .loading-icon {
    animation: spin 1s linear infinite;
  }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.export-tips {
  margin-top: 20px;
  padding: 12px;
  background: #fff8e1;
  border-radius: 8px;
  font-size: 12px;
  color: #666;
  
  p {
    margin: 0 0 8px 0;
    font-weight: 500;
    color: #f57c00;
  }
  
  ul {
    margin: 0;
    padding-left: 16px;
  }
  
  li {
    margin: 4px 0;
  }
}
</style>
