<template>
  <div class="weather-dashboard">
    <!-- 分页控制器 -->
    <div class="pagination-controls" v-if="totalPages > 1">
      <div class="page-info">
        <span class="page-label">分析图表</span>
        <span class="page-number">第 {{ currentPage }} / {{ totalPages }} 页</span>
        <span class="total-count">(共 {{ sortedVisualizations.length }} 个图表)</span>
      </div>
      <div class="page-actions">
        <button 
          class="page-btn" 
          @click="prevPage" 
          :disabled="currentPage === 1"
          title="上一页"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
        </button>
        <div class="page-dots">
          <span 
            v-for="page in totalPages" 
            :key="page"
            class="page-dot"
            :class="{ active: page === currentPage }"
            @click="goToPage(page)"
          ></span>
        </div>
        <button 
          class="page-btn" 
          @click="nextPage" 
          :disabled="currentPage === totalPages"
          title="下一页"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </button>
      </div>
    </div>

    <!-- 分析图表 -->
    <div class="smart-grid" v-if="pagedVisualizations.length">
      <DashboardCard
        v-for="item in pagedVisualizations"
        :key="item.viz.id || item.index"
        :title="item.viz.title || '分析结果'"
        :class="['grid-item', item.layoutClass, 'clickable']"
        @click="enlargeChart(item.viz)"
      >
        <div class="card-content">
          <div class="enlarge-hint">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
            </svg>
            点击放大
          </div>
          <TrajectoryMapPanel
            v-if="item.viz.type === 'map' && isTrajectoryMap(item.viz)"
            :config="item.viz.data"
          />
          <MapPanel
            v-else-if="item.viz.type === 'map'"
            :config="item.viz.data"
          />
          <ChartPanel
            v-else-if="isChartType(item.viz.type)"
            :data="item.viz"
          />
          <DataTable
            v-else-if="item.viz.type === 'table'"
            :rows="getTableRows(item.viz)"
          />
          <ImagePanel
            v-else-if="item.viz.type === 'image'"
            :src="item.viz.data"
          />
          <div v-else class="text-content">
            {{ item.viz.content || item.viz.text || '暂无内容' }}
          </div>
        </div>
      </DashboardCard>
    </div>

    <!-- 放大弹窗 -->
    <Teleport to="body">
      <div v-if="enlargedChart" class="chart-modal-overlay" @click="closeModal">
        <div class="chart-modal" @click.stop>
          <div class="modal-header">
            <h3>{{ enlargedChart.title || '图表详情' }}</h3>
            <button class="close-btn" @click="closeModal" title="关闭">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
          <div class="modal-body">
            <TrajectoryMapPanel
              v-if="enlargedChart.type === 'map' && isTrajectoryMap(enlargedChart)"
              :config="enlargedChart.data"
            />
            <MapPanel
              v-else-if="enlargedChart.type === 'map'"
              :config="enlargedChart.data"
            />
            <ChartPanel
              v-else-if="isChartType(enlargedChart.type)"
              :data="enlargedChart"
              customHeight="500px"
            />
            <DataTable
              v-else-if="enlargedChart.type === 'table'"
              :rows="getTableRows(enlargedChart)"
            />
            <ImagePanel
              v-else-if="enlargedChart.type === 'image'"
              :src="enlargedChart.data"
            />
            <div v-else class="text-content">
              {{ enlargedChart.content || enlargedChart.text || '暂无内容' }}
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 底部专家分析总结 -->
    <div class="expert-summary-bar" v-if="expertAnalysis">
      <div class="summary-header">
        <span class="summary-icon">🌤️</span>
        <span class="summary-title">气象分析专家总结</span>
      </div>
      <div class="summary-body">
        <p class="summary-text">{{ expertAnalysis.summary }}</p>
        <div class="key-findings" v-if="expertAnalysis.key_findings?.length">
          <span class="findings-label">关键发现:</span>
          <ul class="findings-list">
            <li v-for="(finding, index) in expertAnalysis.key_findings" :key="index">
              {{ finding }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- 降级：显示text类型的摘要 -->
    <div class="value-bar" v-else-if="summaryText">
      <span class="value-label">分析结论：</span>
      <span class="value-text">{{ summaryText }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import DashboardCard from './DashboardCard.vue'
import ChartPanel from '../visualization/ChartPanel.vue'
import MapPanel from '../visualization/MapPanel.vue'
import TrajectoryMapPanel from '../visualization/TrajectoryMapPanel.vue'
import DataTable from '../visualization/DataTable.vue'
import ImagePanel from '../visualization/ImagePanel.vue'

const props = defineProps({
  visualizations: {
    type: Array,
    default: () => []
  },
  expertResults: {
    type: Object,
    default: null
  }
})


const CHART_TYPES = [
  'chart',
  'pie',
  'bar',
  'line',
  'timeseries',
  'radar',
  'wind_rose',
  'scatter3d',
  'surface3d',
  'profile',
  'heatmap',
  // 气象专用时序图
  'weather_timeseries',
  'pressure_pbl_timeseries'
]

const isChartType = (type) => CHART_TYPES.includes(type)

// 获取表格数据行（兼容多种格式）
const getTableRows = (viz) => {
  const data = viz?.data
  if (!data) return []
  
  // 格式1: data已经是数组
  if (Array.isArray(data)) {
    return data
  }
  
  // 格式2: {columns: [...], rows: [[...], [...]]}
  if (data.columns && Array.isArray(data.rows)) {
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
  
  return []
}

const isTrajectoryMap = (viz) => {
  return viz.data?.layers?.some(l => l.type === 'trajectory_layer')
}

const getLayoutClass = (viz) => {
  // 大屏模式：所有图表统一布局，每行两个（包括地图）
  return 'layout-standard'
}

const getTypePriority = (type) => {
  // 轨迹地图(map)和轨迹高度剖面(profile)相邻排列，确保同一行展示
  const priorities = {
    'map': 1,
    'profile': 2,      // 紧跟map，确保同行
    'wind_rose': 3,
    'timeseries': 4,
    'line': 5,
    'bar': 6,
    'heatmap': 7,
    'pie': 8,
    'radar': 9,
    'table': 10
  }
  return priorities[type] || 11
}

const sortedVisualizations = computed(() => {
  const nonTextViz = props.visualizations.filter(v => v.type !== 'text')
  
  return nonTextViz
    .map((viz, index) => ({
      viz,
      index,
      layoutClass: getLayoutClass(viz),
      priority: getTypePriority(viz.type)
    }))
    .sort((a, b) => a.priority - b.priority)
})

// 分页逻辑（仅气象图表，去除空白第一页）
const PAGE_SIZE = 4  // 每页显示4个图表
const currentPage = ref(1)

const totalPages = computed(() => {
  const chartPages = Math.ceil(sortedVisualizations.value.length / PAGE_SIZE)
  return chartPages || 1
})

const pagedVisualizations = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return sortedVisualizations.value.slice(start, start + PAGE_SIZE)
})

const prevPage = () => {
  if (currentPage.value > 1) {
    currentPage.value--
  }
}

const nextPage = () => {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
  }
}

const goToPage = (page) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
  }
}

// 放大弹窗逻辑
const enlargedChart = ref(null)

const enlargeChart = (viz) => {
  enlargedChart.value = viz
}

const closeModal = () => {
  enlargedChart.value = null
}

const summaryText = computed(() => {
  const textViz = props.visualizations.find(v => v.type === 'text')
  return textViz?.content || textViz?.text || ''
})

// 已移除脱敏限制

// 获取气象专家的分析结果
const expertAnalysis = computed(() => {
  if (!props.expertResults?.expert_results) return null

  // 从 expert_results 中提取气象专家数据（注意：后端存储在.analysis字段中）
  const weatherResult = props.expertResults.expert_results.weather?.analysis
  if (!weatherResult) return null

  // 返回完整的分析信息
  return {
    summary: weatherResult.summary || '',
    key_findings: weatherResult.key_findings || [],
    confidence: weatherResult.confidence || null,
    data_quality: weatherResult.data_quality || null
  }
})
</script>

<style lang="scss" scoped>
.weather-dashboard {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  padding-bottom: 20px;  /* 确保底部内容有空间 */
}

// 分页控制器样式
.pagination-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f8f9fa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  flex-shrink: 0;
}

.page-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-label {
  font-weight: 600;
  color: #333;
}

.page-number {
  color: #1976d2;
  font-weight: 600;
}

.total-count {
  color: #666;
  font-size: 13px;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid #e0e0e0;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  color: #666;

  &:hover:not(:disabled) {
    border-color: #1976d2;
    color: #1976d2;
    background: #e3f2fd;
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
}

.page-dots {
  display: flex;
  gap: 6px;
}

.page-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ddd;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #bbb;
  }

  &.active {
    background: #1976d2;
    transform: scale(1.2);
  }
}

.smart-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  grid-auto-rows: min-content;
  gap: 12px;  /* 更紧凑的间距 */
  flex-shrink: 0;
}

.grid-item {
  min-height: 0;

  /* 取消边框，更简洁的展示 */
  :deep(.dashboard-card) {
    border: none;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    background: #fafafa;
    border-radius: 6px;

    .card-header {
      padding: 8px 12px;
      background: transparent;
      border-bottom: none;

      .card-title {
        font-size: 13px;
        color: #666;
      }
    }

    .card-body {
      padding: 8px;
    }
  }

  &.layout-standard {
    // 默认 1x1，每行两个
  }
}

.card-content {
  width: 100%;
  height: 100%;
  /* 移除固定最小高度，让内容自适应 */
  min-height: 0;
}

.text-content {
  color: #333;
  font-size: 14px;
  line-height: 1.8;
  padding: 8px;
}

.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: #999;
  
  .empty-icon {
    font-size: 48px;
    margin-bottom: 16px;
  }
  
  p {
    margin: 0;
    font-size: 16px;
  }
}

.value-bar {
  padding: 12px 20px;
  background: #f8f9fa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-shrink: 0;
}

.value-label {
  color: #1a73e8;
  font-weight: 600;
  white-space: nowrap;
}

.value-text {
  color: #333;
  font-size: 14px;
  line-height: 1.6;
}

// 专家分析总结样式
.expert-summary-bar {
  padding: 16px 20px;
  background: linear-gradient(135deg, #fff8e1 0%, #fff3cd 100%);
  border: 1px solid #ffeaa7;
  border-radius: 8px;
  flex-shrink: 0;
  box-shadow: 0 2px 4px rgba(255, 193, 7, 0.1);
}

.summary-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #ffeaa7;
}

.summary-icon {
  font-size: 20px;
}

.summary-title {
  font-weight: 600;
  color: #f57c00;
  font-size: 15px;
  flex: 1;
}

.confidence-badge {
  padding: 4px 10px;
  background: #e8f5e9;
  color: #2e7d32;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.summary-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-text {
  margin: 0;
  color: #333;
  font-size: 14px;
  line-height: 1.6;
}

.key-findings {
  background: rgba(255, 193, 7, 0.05);
  border-radius: 6px;
  padding: 12px;
  border-left: 3px solid #f57c00;
}

.findings-label {
  display: block;
  font-weight: 600;
  color: #f57c00;
  font-size: 13px;
  margin-bottom: 8px;
}

.findings-list {
  margin: 0;
  padding-left: 20px;

  li {
    margin-bottom: 6px;
    color: #555;
    font-size: 13px;
    line-height: 1.5;

    &:last-child {
      margin-bottom: 0;
    }
  }
}

// 点击放大提示
.clickable {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);

    .enlarge-hint {
      opacity: 1;
    }
  }
}

.enlarge-hint {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  border-radius: 4px;
  font-size: 11px;
  opacity: 0;
  transition: opacity 0.2s;
  z-index: 10;
  pointer-events: none;
}

.card-content {
  position: relative;
}

// 放大弹窗样式
.chart-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  padding: 40px;
}

.chart-modal {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 1200px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid #e0e0e0;
  background: #f8f9fa;

  h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: #333;
  }
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: #666;
  transition: all 0.2s;

  &:hover {
    background: #ffe5e5;
    color: #d32f2f;
  }
}

.modal-body {
  flex: 1;
  padding: 24px;
  overflow: auto;
  min-height: 400px;
}

</style>
