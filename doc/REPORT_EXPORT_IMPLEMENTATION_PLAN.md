# 报告导出功能实施方案

## 一、功能概述

在现有可视化区域增加报告导出功能，支持：
- 图表勾选（选择要导出的图表）
- 保持用户交互状态（legend隐藏、dataZoom范围等）
- 导出前预览
- 支持PDF/Word/HTML三种格式

**设计原则**：不影响分析流程，仅在导出环节进行排版整合。

---

## 二、技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    VisualizationPanel.vue                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  图表区域 (增加勾选框)                                        ││
│  │  ☑ 图表1: O3浓度时序图  [状态: legend隐藏NO2, zoom 20%-80%]  ││
│  │  ☑ 图表2: 源解析饼图                                         ││
│  │  □ 图表3: 风向玫瑰图                                         ││
│  │  ☑ 地图1: 上风向企业分布                                     ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                   │
│  [导出报告] 按钮 → 打开 ExportPreviewModal                        │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ExportPreviewModal.vue                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  预览区域 (模拟A4页面布局)                                    ││
│  │  ┌─────────────────────────────────────────────────────────┐││
│  │  │ 报告标题                                                 │││
│  │  │ 执行摘要...                                              │││
│  │  │ ┌─────────┐ ┌─────────┐                                 │││
│  │  │ │ 图表1   │ │ 图表2   │                                 │││
│  │  │ └─────────┘ └─────────┘                                 │││
│  │  │ 气象分析章节...                                          │││
│  │  │ ┌───────────────────┐                                   │││
│  │  │ │ 地图 (整宽)       │                                   │││
│  │  │ └───────────────────┘                                   │││
│  │  └─────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                   │
│  格式: ○PDF  ○Word  ○HTML     [取消] [导出]                      │
└───────────────────────────────────────────────────────────────────┘
                              │
                              │ POST /api/export/report
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    后端导出服务                                    │
│  1. 接收图表数据 + 用户状态 + 报告内容                            │
│  2. 使用ECharts SSR渲染图表为PNG（应用用户状态）                  │
│  3. 组装HTML报告模板                                              │
│  4. 转换为目标格式（PDF/DOCX/HTML）                               │
│  5. 返回文件流                                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、前端改造

### 3.1 ChartPanel.vue 增加状态暴露

**修改文件**: `frontend/src/components/visualization/ChartPanel.vue`

```javascript
// 新增：暴露图表状态获取方法
const getChartState = () => {
  if (!chartInstance) return null
  
  const option = chartInstance.getOption()
  
  return {
    // Legend状态：哪些系列被隐藏
    legendSelected: option.legend?.[0]?.selected || {},
    
    // DataZoom状态：时间范围
    dataZoom: option.dataZoom?.map(dz => ({
      start: dz.start,
      end: dz.end
    })) || [],
    
    // 3D图表视角（如有）
    grid3D: option.grid3D?.[0]?.viewControl || null
  }
}

// 新增：获取图表截图（用于预览）
const getChartImage = () => {
  if (!chartInstance) return null
  return chartInstance.getDataURL({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: '#fff'
  })
}

// 暴露方法给父组件
defineExpose({
  getChartState,
  getChartImage,
  getChartInstance: () => chartInstance
})
```

### 3.2 VisualizationPanel.vue 增加勾选和导出

**修改文件**: `frontend/src/components/VisualizationPanel.vue`

```vue
<template>
  <div class="viz-panel">
    <!-- 头部增加导出按钮 -->
    <div class="panel-header">
      <div class="panel-title-group">
        <h3>{{ panelTitle }}</h3>
        <span v-if="visualizations.length" class="viz-count">
          共 {{ visualizations.length }} 个结果
        </span>
      </div>
      <div class="header-actions">
        <!-- 新增：导出模式切换 -->
        <button 
          v-if="visualizations.length" 
          @click="toggleExportMode" 
          class="export-mode-btn"
          :class="{ active: exportMode }"
        >
          {{ exportMode ? '取消选择' : '选择导出' }}
        </button>
        
        <!-- 新增：导出按钮 -->
        <button 
          v-if="exportMode && selectedCharts.length > 0"
          @click="openExportPreview"
          class="export-btn"
        >
          导出报告 ({{ selectedCharts.length }})
        </button>
        
        <!-- 原有按钮 -->
        <button @click="$emit('fullscreen')" class="fullscreen-btn">展开大屏</button>
      </div>
    </div>

    <!-- 图表列表增加勾选框 -->
    <div class="panel-body">
      <div
        v-for="(viz, index) in visualizations"
        :key="viz.id || index"
        class="viz-item"
        :class="{ 'selected-for-export': isSelectedForExport(viz.id) }"
      >
        <!-- 新增：勾选框（导出模式下显示） -->
        <div v-if="exportMode" class="export-checkbox">
          <input 
            type="checkbox" 
            :id="`export-${viz.id}`"
            :checked="isSelectedForExport(viz.id)"
            @change="toggleChartSelection(viz)"
          />
          <label :for="`export-${viz.id}`">选择</label>
        </div>

        <!-- 原有图表头部 -->
        <div class="viz-item-header">...</div>

        <!-- 图表组件（增加ref用于获取状态） -->
        <ChartPanel
          v-if="isChartType(viz.type)"
          :ref="el => setChartRef(viz.id, el)"
          :data="viz"
        />
        
        <MapPanel
          v-else-if="viz.type === 'map'"
          :ref="el => setMapRef(viz.id, el)"
          :config="viz.data"
        />
      </div>
    </div>

    <!-- 新增：导出预览弹窗 -->
    <ExportPreviewModal
      v-if="showExportPreview"
      :selected-charts="selectedChartsData"
      :report-content="reportContent"
      @close="showExportPreview = false"
      @export="handleExport"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import ExportPreviewModal from './ExportPreviewModal.vue'

// 导出模式状态
const exportMode = ref(false)
const selectedCharts = ref([])  // 选中的图表ID列表
const chartRefs = ref({})       // 图表组件引用
const mapRefs = ref({})         // 地图组件引用
const showExportPreview = ref(false)

// 切换导出模式
const toggleExportMode = () => {
  exportMode.value = !exportMode.value
  if (!exportMode.value) {
    selectedCharts.value = []
  }
}

// 图表选择切换
const toggleChartSelection = (viz) => {
  const id = viz.id
  const index = selectedCharts.value.indexOf(id)
  if (index > -1) {
    selectedCharts.value.splice(index, 1)
  } else {
    selectedCharts.value.push(id)
  }
}

// 检查是否被选中
const isSelectedForExport = (id) => {
  return selectedCharts.value.includes(id)
}

// 保存图表组件引用
const setChartRef = (id, el) => {
  if (el) chartRefs.value[id] = el
}
const setMapRef = (id, el) => {
  if (el) mapRefs.value[id] = el
}

// 收集选中图表的完整数据（包含用户状态）
const selectedChartsData = computed(() => {
  return selectedCharts.value.map(id => {
    const viz = visualizations.value.find(v => v.id === id)
    if (!viz) return null
    
    // 获取图表当前状态
    let chartState = null
    let chartImage = null
    
    if (chartRefs.value[id]) {
      chartState = chartRefs.value[id].getChartState?.()
      chartImage = chartRefs.value[id].getChartImage?.()
    }
    
    return {
      ...viz,
      userState: chartState,    // 用户交互状态
      previewImage: chartImage  // 预览用截图
    }
  }).filter(Boolean)
})

// 打开导出预览
const openExportPreview = () => {
  showExportPreview.value = true
}

// 处理导出
const handleExport = async (format) => {
  // 调用导出API
}
</script>
```

### 3.3 新增 ExportPreviewModal.vue

**新建文件**: `frontend/src/components/ExportPreviewModal.vue`

```vue
<template>
  <div class="export-modal-overlay" @click.self="$emit('close')">
    <div class="export-modal">
      <div class="modal-header">
        <h2>报告导出预览</h2>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>
      
      <div class="modal-body">
        <!-- 预览区域 -->
        <div class="preview-container">
          <div class="a4-preview">
            <!-- 报告标题 -->
            <div class="report-header">
              <h1>{{ reportTitle }}</h1>
              <p class="report-meta">
                生成时间：{{ formatDate(new Date()) }} | 
                置信度：{{ confidence }}%
              </p>
            </div>
            
            <!-- 执行摘要 -->
            <div class="report-section">
              <h2>执行摘要</h2>
              <div class="summary-content" v-html="summaryHtml"></div>
            </div>
            
            <!-- 图表预览 -->
            <div class="charts-preview">
              <div 
                v-for="chart in selectedCharts" 
                :key="chart.id"
                class="chart-preview-item"
                :class="getChartSizeClass(chart)"
              >
                <img 
                  v-if="chart.previewImage" 
                  :src="chart.previewImage" 
                  :alt="chart.title"
                />
                <div v-else class="chart-placeholder">
                  {{ chart.title || '图表' }}
                </div>
                <p class="chart-caption">{{ chart.title }}</p>
                
                <!-- 显示用户状态提示 -->
                <div v-if="hasUserState(chart)" class="state-indicator">
                  <span v-if="chart.userState?.dataZoom?.length" class="state-tag">
                    已调整时间范围
                  </span>
                  <span v-if="hasHiddenLegend(chart)" class="state-tag">
                    已隐藏部分指标
                  </span>
                </div>
              </div>
            </div>
            
            <!-- 分析内容 -->
            <div class="report-content" v-html="reportHtml"></div>
          </div>
        </div>
        
        <!-- 侧边栏：导出选项 -->
        <div class="export-options">
          <h3>导出设置</h3>
          
          <!-- 格式选择 -->
          <div class="option-group">
            <label>导出格式</label>
            <div class="format-radios">
              <label class="format-option">
                <input type="radio" v-model="exportFormat" value="pdf" />
                <span class="format-icon">📄</span>
                <span>PDF</span>
              </label>
              <label class="format-option">
                <input type="radio" v-model="exportFormat" value="docx" />
                <span class="format-icon">📝</span>
                <span>Word</span>
              </label>
              <label class="format-option">
                <input type="radio" v-model="exportFormat" value="html" />
                <span class="format-icon">🌐</span>
                <span>HTML</span>
              </label>
            </div>
          </div>
          
          <!-- 图表顺序调整 -->
          <div class="option-group">
            <label>图表顺序 (拖拽调整)</label>
            <div class="chart-order-list">
              <div 
                v-for="(chart, index) in selectedCharts"
                :key="chart.id"
                class="order-item"
                draggable="true"
                @dragstart="onDragStart(index)"
                @dragover.prevent
                @drop="onDrop(index)"
              >
                <span class="order-num">{{ index + 1 }}</span>
                <span class="order-title">{{ chart.title }}</span>
                <span class="drag-handle">⋮⋮</span>
              </div>
            </div>
          </div>
          
          <!-- 导出按钮 -->
          <div class="export-actions">
            <button 
              class="export-btn primary"
              :disabled="exporting"
              @click="doExport"
            >
              {{ exporting ? '导出中...' : '确认导出' }}
            </button>
            <button class="export-btn secondary" @click="$emit('close')">
              取消
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { exportReportApi } from '@/services/exportApi'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt()

const props = defineProps({
  selectedCharts: { type: Array, required: true },
  reportContent: { type: Object, default: null }
})

const emit = defineEmits(['close', 'export'])

const exportFormat = ref('pdf')
const exporting = ref(false)
const dragIndex = ref(null)

// 报告标题
const reportTitle = computed(() => {
  return props.reportContent?.title || '大气污染溯源分析报告'
})

// 置信度
const confidence = computed(() => {
  return Math.round((props.reportContent?.confidence || 0.85) * 100)
})

// 摘要HTML
const summaryHtml = computed(() => {
  const summary = props.reportContent?.summary || ''
  return md.render(summary)
})

// 报告内容HTML
const reportHtml = computed(() => {
  const content = props.reportContent?.sections?.[0]?.markdown_content || ''
  return md.render(content)
})

// 检查是否有用户状态
const hasUserState = (chart) => {
  return chart.userState && (
    chart.userState.dataZoom?.length > 0 ||
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
  return 'half-width'
}

// 拖拽排序
const onDragStart = (index) => {
  dragIndex.value = index
}

const onDrop = (targetIndex) => {
  if (dragIndex.value === null) return
  const charts = [...props.selectedCharts]
  const [moved] = charts.splice(dragIndex.value, 1)
  charts.splice(targetIndex, 0, moved)
  // 这里需要emit更新父组件的顺序
  dragIndex.value = null
}

// 执行导出
const doExport = async () => {
  exporting.value = true
  
  try {
    const exportData = {
      format: exportFormat.value,
      report_content: props.reportContent,
      charts: props.selectedCharts.map(chart => ({
        id: chart.id,
        type: chart.type,
        title: chart.title,
        data: chart.data,
        meta: chart.meta,
        user_state: chart.userState  // 用户交互状态
      }))
    }
    
    const blob = await exportReportApi(exportData)
    
    // 下载文件
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `溯源分析报告_${formatDate(new Date())}.${exportFormat.value}`
    a.click()
    URL.revokeObjectURL(url)
    
    emit('close')
  } catch (error) {
    console.error('导出失败:', error)
    alert('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

const formatDate = (date) => {
  return date.toISOString().split('T')[0]
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
}

.modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
  
  h2 { margin: 0; font-size: 18px; }
  .close-btn {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: #666;
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
  background: #f5f5f5;
}

.a4-preview {
  background: white;
  width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  padding: 20mm;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  font-family: "SimSun", "Microsoft YaHei", sans-serif;
  font-size: 12pt;
  line-height: 1.6;
}

.report-header {
  text-align: center;
  border-bottom: 2px solid #333;
  padding-bottom: 16px;
  margin-bottom: 24px;
  
  h1 { font-size: 24px; margin: 0 0 8px 0; }
  .report-meta { color: #666; font-size: 12px; }
}

.charts-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin: 24px 0;
}

.chart-preview-item {
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 12px;
  
  &.half-width { width: calc(50% - 8px); }
  &.full-width { width: 100%; }
  
  img {
    width: 100%;
    height: auto;
    border-radius: 4px;
  }
  
  .chart-caption {
    text-align: center;
    font-size: 10pt;
    color: #666;
    margin: 8px 0 0 0;
  }
  
  .state-indicator {
    display: flex;
    gap: 8px;
    margin-top: 8px;
    
    .state-tag {
      font-size: 10px;
      background: #e3f2fd;
      color: #1976d2;
      padding: 2px 8px;
      border-radius: 4px;
    }
  }
}

.export-options {
  width: 280px;
  background: #fafafa;
  border-left: 1px solid #eee;
  padding: 24px;
  overflow-y: auto;
  
  h3 { margin: 0 0 16px 0; font-size: 16px; }
}

.option-group {
  margin-bottom: 24px;
  
  > label {
    display: block;
    font-weight: 500;
    margin-bottom: 12px;
    font-size: 14px;
  }
}

.format-radios {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.format-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  
  &:hover { background: #f5f5f5; }
  
  input:checked + .format-icon + span {
    font-weight: 600;
  }
  
  input:checked ~ * {
    color: #1976d2;
  }
  
  .format-icon { font-size: 20px; }
}

.chart-order-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.order-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: grab;
  
  .order-num {
    width: 20px;
    height: 20px;
    background: #1976d2;
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
  }
  
  .order-title {
    flex: 1;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .drag-handle {
    color: #999;
    cursor: grab;
  }
}

.export-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 32px;
}

.export-btn {
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  
  &.primary {
    background: #1976d2;
    color: white;
    border: none;
    
    &:hover { background: #1565c0; }
    &:disabled { background: #ccc; cursor: not-allowed; }
  }
  
  &.secondary {
    background: white;
    color: #666;
    border: 1px solid #ddd;
    
    &:hover { background: #f5f5f5; }
  }
}
</style>
```

### 3.4 新增导出API服务

**新建文件**: `frontend/src/services/exportApi.js`

```javascript
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/**
 * 导出报告API
 * @param {Object} data - 导出数据
 * @returns {Promise<Blob>} - 返回文件Blob
 */
export const exportReportApi = async (data) => {
  const response = await axios.post(`${API_BASE}/api/export/report`, data, {
    responseType: 'blob',
    timeout: 120000  // 2分钟超时（PDF生成可能较慢）
  })
  
  return response.data
}
```

---

## 四、后端实现

### 4.1 新增导出路由

**新建文件**: `backend/app/routers/export.py`

```python
"""
报告导出路由

支持PDF/Word/HTML三种格式导出
"""

from fastapi import APIRouter, Response, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import structlog
import io

from app.services.report_exporter import ReportExporter

logger = structlog.get_logger()
router = APIRouter(prefix="/api/export", tags=["export"])


class ChartUserState(BaseModel):
    """图表用户交互状态"""
    legendSelected: Optional[Dict[str, bool]] = None  # legend选中状态
    dataZoom: Optional[List[Dict[str, float]]] = None  # dataZoom范围
    grid3D: Optional[Dict[str, Any]] = None  # 3D视角


class ChartExportData(BaseModel):
    """单个图表导出数据"""
    id: str
    type: str
    title: Optional[str] = None
    data: Dict[str, Any]
    meta: Optional[Dict[str, Any]] = None
    user_state: Optional[ChartUserState] = None


class ReportExportRequest(BaseModel):
    """报告导出请求"""
    format: str = Field(default="pdf", description="导出格式: pdf/docx/html")
    report_content: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="报告专家生成的内容"
    )
    charts: List[ChartExportData] = Field(
        default_factory=list,
        description="选中的图表列表（含用户状态）"
    )


@router.post("/report")
async def export_report(request: ReportExportRequest):
    """
    导出综合分析报告
    
    支持格式：
    - pdf: PDF文档（推荐）
    - docx: Word文档
    - html: HTML网页
    
    用户状态保持：
    - legendSelected: 保持用户隐藏的图例
    - dataZoom: 保持用户选择的时间范围
    """
    logger.info(
        "export_report_request",
        format=request.format,
        chart_count=len(request.charts)
    )
    
    try:
        exporter = ReportExporter()
        
        # 生成报告
        result = await exporter.generate(
            format=request.format,
            report_content=request.report_content,
            charts=[c.dict() for c in request.charts]
        )
        
        # 确定MIME类型和文件名
        mime_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "html": "text/html"
        }
        extensions = {"pdf": "pdf", "docx": "docx", "html": "html"}
        
        mime_type = mime_types.get(request.format, "application/octet-stream")
        extension = extensions.get(request.format, "bin")
        filename = f"pollution_tracing_report.{extension}"
        
        return Response(
            content=result,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except Exception as e:
        logger.error("export_report_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")
```

### 4.2 新增报告导出服务

**新建文件**: `backend/app/services/report_exporter.py`

```python
"""
报告导出服务

负责：
1. 渲染ECharts图表为图片（应用用户状态）
2. 组装HTML报告模板
3. 转换为PDF/DOCX格式
"""

from typing import Dict, Any, List, Optional
import structlog
import asyncio
import base64
import io
from datetime import datetime

logger = structlog.get_logger()


class ReportExporter:
    """报告导出服务"""
    
    def __init__(self):
        self.template_path = "app/templates/report_template.html"
    
    async def generate(
        self,
        format: str,
        report_content: Optional[Dict[str, Any]],
        charts: List[Dict[str, Any]]
    ) -> bytes:
        """
        生成报告
        
        Args:
            format: 导出格式 (pdf/docx/html)
            report_content: 报告内容
            charts: 图表列表（含用户状态）
            
        Returns:
            bytes: 生成的文件内容
        """
        logger.info(
            "generating_report",
            format=format,
            chart_count=len(charts)
        )
        
        # 1. 渲染图表为图片
        chart_images = await self._render_charts(charts)
        
        # 2. 组装HTML
        html_content = self._compose_html(report_content, chart_images)
        
        # 3. 转换格式
        if format == "pdf":
            return await self._html_to_pdf(html_content)
        elif format == "docx":
            return await self._html_to_docx(html_content)
        else:
            return html_content.encode("utf-8")
    
    async def _render_charts(
        self, 
        charts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        渲染图表为图片
        
        应用用户状态：
        - legendSelected: 在渲染时过滤隐藏的系列
        - dataZoom: 在渲染时应用时间范围裁剪
        """
        results = []
        
        for chart in charts:
            try:
                # 应用用户状态到图表配置
                modified_data = self._apply_user_state(
                    chart.get("data", {}),
                    chart.get("user_state")
                )
                
                # 渲染为图片
                image_base64 = await self._render_single_chart(
                    chart_type=chart.get("type"),
                    chart_data=modified_data,
                    title=chart.get("title", "")
                )
                
                results.append({
                    "id": chart.get("id"),
                    "title": chart.get("title", ""),
                    "type": chart.get("type"),
                    "image_base64": image_base64,
                    "has_user_state": bool(chart.get("user_state"))
                })
                
            except Exception as e:
                logger.error(
                    "chart_render_failed",
                    chart_id=chart.get("id"),
                    error=str(e)
                )
                results.append({
                    "id": chart.get("id"),
                    "title": chart.get("title", ""),
                    "error": str(e)
                })
        
        return results
    
    def _apply_user_state(
        self,
        chart_data: Dict[str, Any],
        user_state: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        应用用户交互状态到图表数据
        
        处理：
        1. legendSelected: 过滤被隐藏的系列
        2. dataZoom: 裁剪数据范围
        """
        if not user_state:
            return chart_data
        
        modified = dict(chart_data)
        
        # 处理legend隐藏
        legend_selected = user_state.get("legendSelected", {})
        if legend_selected and "series" in modified:
            hidden_series = {
                name for name, visible in legend_selected.items() 
                if visible is False
            }
            if hidden_series:
                modified["series"] = [
                    s for s in modified["series"]
                    if s.get("name") not in hidden_series
                ]
                logger.info(
                    "legend_state_applied",
                    hidden=list(hidden_series)
                )
        
        # 处理dataZoom范围
        data_zoom = user_state.get("dataZoom", [])
        if data_zoom and "x" in modified:
            zoom = data_zoom[0] if data_zoom else {}
            start_pct = zoom.get("start", 0) / 100
            end_pct = zoom.get("end", 100) / 100
            
            x_data = modified.get("x", [])
            if x_data:
                total_len = len(x_data)
                start_idx = int(total_len * start_pct)
                end_idx = int(total_len * end_pct)
                
                # 裁剪x轴数据
                modified["x"] = x_data[start_idx:end_idx]
                
                # 裁剪series数据
                if "series" in modified:
                    for s in modified["series"]:
                        if "data" in s:
                            s["data"] = s["data"][start_idx:end_idx]
                
                # 裁剪y数据（单序列格式）
                if "y" in modified:
                    modified["y"] = modified["y"][start_idx:end_idx]
                
                logger.info(
                    "datazoom_state_applied",
                    start_pct=start_pct,
                    end_pct=end_pct,
                    original_len=total_len,
                    new_len=end_idx - start_idx
                )
        
        return modified
    
    async def _render_single_chart(
        self,
        chart_type: str,
        chart_data: Dict[str, Any],
        title: str
    ) -> str:
        """
        渲染单个图表为Base64图片
        
        使用pyecharts进行服务端渲染
        """
        try:
            from pyecharts.charts import Pie, Bar, Line, Radar
            from pyecharts import options as opts
            from pyecharts.render import make_snapshot
            from snapshot_selenium import snapshot
            
            chart = None
            
            if chart_type == "pie":
                chart = self._build_pie_chart(chart_data, title)
            elif chart_type == "bar":
                chart = self._build_bar_chart(chart_data, title)
            elif chart_type in ("line", "timeseries"):
                chart = self._build_line_chart(chart_data, title)
            elif chart_type == "radar":
                chart = self._build_radar_chart(chart_data, title)
            else:
                # 其他类型使用占位图
                return self._generate_placeholder_image(chart_type, title)
            
            if chart:
                # 渲染为临时HTML后截图
                html_path = f"/tmp/chart_{id(chart)}.html"
                chart.render(html_path)
                
                # 使用selenium截图
                img_path = f"/tmp/chart_{id(chart)}.png"
                make_snapshot(snapshot, html_path, img_path)
                
                # 读取并转为base64
                with open(img_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            
        except ImportError as e:
            logger.warning(
                "pyecharts_not_available",
                error=str(e),
                fallback="placeholder"
            )
            return self._generate_placeholder_image(chart_type, title)
        except Exception as e:
            logger.error(
                "chart_render_error",
                chart_type=chart_type,
                error=str(e)
            )
            return self._generate_placeholder_image(chart_type, title)
    
    def _build_pie_chart(self, data: Dict, title: str):
        """构建饼图"""
        from pyecharts.charts import Pie
        from pyecharts import options as opts
        
        pie_data = data if isinstance(data, list) else data.get("data", [])
        
        chart = (
            Pie()
            .add(
                "",
                [(item.get("name", ""), item.get("value", 0)) for item in pie_data],
                radius=["40%", "70%"]
            )
            .set_global_opts(
                title_opts=opts.TitleOpts(title=title),
                legend_opts=opts.LegendOpts(orient="vertical", pos_left="left")
            )
            .set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {d}%"))
        )
        return chart
    
    def _build_bar_chart(self, data: Dict, title: str):
        """构建柱状图"""
        from pyecharts.charts import Bar
        from pyecharts import options as opts
        
        x_data = data.get("x", [])
        series = data.get("series", [])
        y_data = data.get("y", [])
        
        chart = Bar()
        chart.add_xaxis(x_data)
        
        if series:
            for s in series:
                chart.add_yaxis(s.get("name", ""), s.get("data", []))
        elif y_data:
            chart.add_yaxis("", y_data)
        
        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45))
        )
        
        return chart
    
    def _build_line_chart(self, data: Dict, title: str):
        """构建折线图"""
        from pyecharts.charts import Line
        from pyecharts import options as opts
        
        x_data = data.get("x", [])
        series = data.get("series", [])
        y_data = data.get("y", [])
        
        chart = Line()
        chart.add_xaxis(x_data)
        
        if series:
            for s in series:
                chart.add_yaxis(
                    s.get("name", ""),
                    s.get("data", []),
                    is_smooth=True,
                    is_symbol_show=False
                )
        elif y_data:
            chart.add_yaxis("", y_data, is_smooth=True, is_symbol_show=False)
        
        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
            datazoom_opts=[opts.DataZoomOpts()]
        )
        
        return chart
    
    def _build_radar_chart(self, data: Dict, title: str):
        """构建雷达图"""
        from pyecharts.charts import Radar
        from pyecharts import options as opts
        
        indicators = data.get("indicator", [])
        series = data.get("series", [])
        
        # 兼容旧格式
        if not indicators and data.get("x"):
            indicators = [{"name": x, "max": 100} for x in data.get("x", [])]
            series = [{"name": title, "value": data.get("y", [])}]
        
        chart = (
            Radar()
            .add_schema(schema=[
                opts.RadarIndicatorItem(name=ind.get("name"), max_=ind.get("max", 100))
                for ind in indicators
            ])
        )
        
        for s in series:
            chart.add(s.get("name", ""), [s.get("value", [])])
        
        chart.set_global_opts(title_opts=opts.TitleOpts(title=title))
        
        return chart
    
    def _generate_placeholder_image(self, chart_type: str, title: str) -> str:
        """生成占位图片（当渲染失败时使用）"""
        # 简单的SVG占位图
        svg = f'''
        <svg width="600" height="400" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" fill="#f5f5f5"/>
            <text x="50%" y="45%" text-anchor="middle" font-size="24" fill="#999">
                {title}
            </text>
            <text x="50%" y="55%" text-anchor="middle" font-size="14" fill="#ccc">
                ({chart_type} 图表)
            </text>
        </svg>
        '''
        return base64.b64encode(svg.encode()).decode()
    
    def _compose_html(
        self,
        report_content: Optional[Dict[str, Any]],
        chart_images: List[Dict[str, Any]]
    ) -> str:
        """
        组装HTML报告
        """
        from jinja2 import Template
        
        # 报告模板
        template_str = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <style>
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: "SimSun", "Microsoft YaHei", sans-serif;
            font-size: 12pt;
            line-height: 1.8;
            color: #333;
            max-width: 210mm;
            margin: 0 auto;
            padding: 20mm;
        }
        .report-header {
            text-align: center;
            border-bottom: 2px solid #1976d2;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .report-header h1 {
            color: #1976d2;
            margin: 0 0 10px 0;
            font-size: 24pt;
        }
        .report-meta {
            color: #666;
            font-size: 10pt;
        }
        .section {
            margin: 30px 0;
            page-break-inside: avoid;
        }
        .section h2 {
            color: #1976d2;
            border-left: 4px solid #1976d2;
            padding-left: 12px;
            margin-bottom: 16px;
        }
        .chart-container {
            margin: 20px 0;
            text-align: center;
            page-break-inside: avoid;
        }
        .chart-container img {
            max-width: 100%;
            height: auto;
            border: 1px solid #eee;
            border-radius: 8px;
        }
        .chart-caption {
            font-size: 10pt;
            color: #666;
            margin-top: 8px;
        }
        .user-state-note {
            font-size: 9pt;
            color: #1976d2;
            background: #e3f2fd;
            padding: 4px 8px;
            border-radius: 4px;
            display: inline-block;
            margin-top: 4px;
        }
        .charts-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            justify-content: center;
        }
        .chart-half {
            width: calc(50% - 10px);
        }
        .chart-full {
            width: 100%;
        }
        .content-section {
            text-align: justify;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            font-size: 10pt;
            color: #999;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }
        th {
            background: #f5f5f5;
        }
    </style>
</head>
<body>
    <div class="report-header">
        <h1>{{ title }}</h1>
        <p class="report-meta">
            生成时间：{{ generated_at }} | 
            分析置信度：{{ confidence }}%
        </p>
    </div>
    
    {% if summary %}
    <div class="section">
        <h2>执行摘要</h2>
        <div class="content-section">{{ summary | safe }}</div>
    </div>
    {% endif %}
    
    {% if charts %}
    <div class="section">
        <h2>分析图表</h2>
        <div class="charts-grid">
            {% for chart in charts %}
            <div class="chart-container {{ 'chart-full' if chart.type in ['map', 'heatmap'] else 'chart-half' }}">
                {% if chart.image_base64 %}
                <img src="data:image/png;base64,{{ chart.image_base64 }}" alt="{{ chart.title }}">
                {% else %}
                <div style="padding: 40px; background: #f5f5f5; border-radius: 8px;">
                    <p>{{ chart.title or '图表' }}</p>
                    {% if chart.error %}
                    <p style="color: #999; font-size: 10pt;">渲染失败: {{ chart.error }}</p>
                    {% endif %}
                </div>
                {% endif %}
                <p class="chart-caption">图 {{ loop.index }}：{{ chart.title }}</p>
                {% if chart.has_user_state %}
                <span class="user-state-note">已应用用户自定义视图</span>
                {% endif %}
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}
    
    {% if content_html %}
    <div class="section">
        <h2>详细分析</h2>
        <div class="content-section">{{ content_html | safe }}</div>
    </div>
    {% endif %}
    
    {% if conclusions %}
    <div class="section">
        <h2>主要结论</h2>
        <ul>
            {% for conclusion in conclusions %}
            <li>{{ conclusion }}</li>
            {% endfor %}
        </ul>
    </div>
    {% endif %}
    
    {% if recommendations %}
    <div class="section">
        <h2>控制建议</h2>
        <ul>
            {% for rec in recommendations %}
            <li>{{ rec }}</li>
            {% endfor %}
        </ul>
    </div>
    {% endif %}
    
    <div class="footer">
        <p>本报告由大气污染溯源分析系统自动生成</p>
        <p>报告仅供参考，具体决策请结合实际情况</p>
    </div>
</body>
</html>
        '''
        
        template = Template(template_str)
        
        # 解析报告内容
        title = "大气污染溯源分析报告"
        summary = ""
        content_html = ""
        conclusions = []
        recommendations = []
        confidence = 85
        
        if report_content:
            title = report_content.get("title", title)
            summary = report_content.get("summary", "")
            confidence = int(report_content.get("confidence", 0.85) * 100)
            conclusions = report_content.get("conclusions", [])
            recommendations = report_content.get("recommendations", [])
            
            # 从sections获取Markdown内容
            sections = report_content.get("sections", [])
            if sections and isinstance(sections[0], dict):
                md_content = sections[0].get("markdown_content", "")
                if md_content:
                    import markdown
                    content_html = markdown.markdown(md_content)
        
        html = template.render(
            title=title,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            confidence=confidence,
            summary=summary,
            charts=chart_images,
            content_html=content_html,
            conclusions=conclusions,
            recommendations=recommendations
        )
        
        return html
    
    async def _html_to_pdf(self, html_content: str) -> bytes:
        """
        HTML转PDF
        
        使用weasyprint或wkhtmltopdf
        """
        try:
            from weasyprint import HTML
            
            pdf_bytes = HTML(string=html_content).write_pdf()
            return pdf_bytes
            
        except ImportError:
            logger.warning("weasyprint_not_available, trying wkhtmltopdf")
            
            # 备选方案：使用wkhtmltopdf命令行
            import subprocess
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_content)
                html_path = f.name
            
            pdf_path = html_path.replace('.html', '.pdf')
            
            result = subprocess.run(
                ['wkhtmltopdf', '--encoding', 'utf-8', html_path, pdf_path],
                capture_output=True
            )
            
            if result.returncode != 0:
                raise Exception(f"wkhtmltopdf failed: {result.stderr.decode()}")
            
            with open(pdf_path, 'rb') as f:
                return f.read()
    
    async def _html_to_docx(self, html_content: str) -> bytes:
        """
        HTML转Word文档
        
        使用python-docx
        """
        try:
            from docx import Document
            from docx.shared import Inches, Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from bs4 import BeautifulSoup
            import base64
            import io
            
            doc = Document()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 添加标题
            title_elem = soup.find('h1')
            if title_elem:
                heading = doc.add_heading(title_elem.get_text(), 0)
                heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # 添加元数据
            meta_elem = soup.find('p', class_='report-meta')
            if meta_elem:
                p = doc.add_paragraph(meta_elem.get_text())
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            doc.add_paragraph()  # 空行
            
            # 处理各section
            for section in soup.find_all('div', class_='section'):
                h2 = section.find('h2')
                if h2:
                    doc.add_heading(h2.get_text(), 1)
                
                # 处理段落
                for p_elem in section.find_all('p'):
                    doc.add_paragraph(p_elem.get_text())
                
                # 处理列表
                for ul in section.find_all('ul'):
                    for li in ul.find_all('li'):
                        doc.add_paragraph(li.get_text(), style='List Bullet')
                
                # 处理图片
                for img in section.find_all('img'):
                    src = img.get('src', '')
                    if src.startswith('data:image'):
                        # 提取base64数据
                        _, data = src.split(',', 1)
                        img_bytes = base64.b64decode(data)
                        
                        img_stream = io.BytesIO(img_bytes)
                        doc.add_picture(img_stream, width=Inches(5))
                        
                        # 添加图片说明
                        alt = img.get('alt', '')
                        if alt:
                            caption = doc.add_paragraph(alt)
                            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # 保存到内存
            output = io.BytesIO()
            doc.save(output)
            return output.getvalue()
            
        except ImportError as e:
            logger.error("python-docx_not_available", error=str(e))
            raise Exception("Word导出功能需要安装python-docx库")
```

### 4.3 注册路由

**修改文件**: `backend/app/main.py`

```python
# 在路由注册部分添加
from app.routers import export

app.include_router(export.router)
```

### 4.4 依赖安装

**修改文件**: `backend/requirements.txt`

```
# 报告导出相关
weasyprint==60.1          # HTML转PDF
python-docx==1.1.0        # 生成Word文档
pyecharts==2.0.4          # 图表服务端渲染
snapshot-selenium==0.0.2  # 图表截图
jinja2==3.1.2             # HTML模板引擎
markdown==3.5.1           # Markdown解析
beautifulsoup4==4.12.2    # HTML解析
```

---

## 五、用户状态捕获详细设计

### 5.1 捕获的状态类型

| 状态类型 | 来源 | 用途 |
|---------|------|------|
| `legendSelected` | ECharts legend组件 | 保持用户隐藏的数据系列 |
| `dataZoom` | ECharts dataZoom组件 | 保持用户选择的时间/数据范围 |
| `grid3D.viewControl` | ECharts GL 3D图表 | 保持3D视角（旋转、缩放） |

### 5.2 状态获取时机

```javascript
// ChartPanel.vue 中的状态获取
const getChartState = () => {
  if (!chartInstance) return null
  
  // 获取当前ECharts配置
  const option = chartInstance.getOption()
  
  return {
    legendSelected: option.legend?.[0]?.selected || {},
    dataZoom: option.dataZoom?.map(dz => ({
      start: dz.start,
      end: dz.end
    })) || [],
    grid3D: option.grid3D?.[0]?.viewControl || null
  }
}
```

### 5.3 状态应用逻辑

```python
# 后端 report_exporter.py 中的状态应用
def _apply_user_state(self, chart_data, user_state):
    if not user_state:
        return chart_data
    
    modified = dict(chart_data)
    
    # 1. 处理legend隐藏 - 过滤被隐藏的series
    legend_selected = user_state.get("legendSelected", {})
    if legend_selected and "series" in modified:
        hidden = {name for name, visible in legend_selected.items() if not visible}
        modified["series"] = [s for s in modified["series"] if s["name"] not in hidden]
    
    # 2. 处理dataZoom - 裁剪数据范围
    data_zoom = user_state.get("dataZoom", [])
    if data_zoom and "x" in modified:
        zoom = data_zoom[0]
        start_pct = zoom.get("start", 0) / 100
        end_pct = zoom.get("end", 100) / 100
        
        total = len(modified["x"])
        start_idx = int(total * start_pct)
        end_idx = int(total * end_pct)
        
        modified["x"] = modified["x"][start_idx:end_idx]
        for s in modified.get("series", []):
            s["data"] = s["data"][start_idx:end_idx]
    
    return modified
```

---

## 六、实施计划

| 阶段 | 任务 | 工作量 | 优先级 |
|------|------|--------|--------|
| **Phase 1** | ChartPanel增加状态暴露方法 | 0.5天 | P0 |
| **Phase 2** | VisualizationPanel增加勾选和导出按钮 | 1天 | P0 |
| **Phase 3** | 新建ExportPreviewModal预览组件 | 1天 | P0 |
| **Phase 4** | 后端导出API和ReportExporter服务 | 1.5天 | P0 |
| **Phase 5** | 安装依赖，联调测试 | 0.5天 | P0 |
| **Phase 6** | 地图截图支持（可选） | 1天 | P1 |

**总计**：约4-5天完成核心功能

---

## 七、注意事项

1. **weasyprint依赖**：需要安装GTK+ 3和相关库，Windows上可能需要额外配置
2. **图表渲染**：服务端渲染需要headless浏览器（selenium+Chrome/Firefox）
3. **地图截图**：高德地图需要特殊处理，建议前端截图后传递
4. **中文字体**：PDF需要确保服务器安装了中文字体

---

## 八、备选方案

如果服务端渲染复杂度过高，可采用**前端截图方案**：

1. 使用`html2canvas`在前端截取图表
2. 将截图base64传递给后端
3. 后端只负责组装PDF/Word

这样可以完美保持用户的交互状态，且减少后端依赖。
