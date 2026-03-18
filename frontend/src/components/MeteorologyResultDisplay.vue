<template>
  <div class="meteorology-result-display">
    <!-- 分析结果头部 -->
    <div class="result-header">
      <div class="header-content">
        <div class="header-icon">🌤️</div>
        <div class="header-text">
          <h2>{{ resultTitle }}</h2>
          <p class="result-summary">{{ summary }}</p>
        </div>
      </div>
      <div class="header-meta">
        <div class="meta-item">
          <span class="meta-label">专家类型</span>
          <span class="meta-value">{{ expertType }}</span>
        </div>
        <div class="meta-item" v-if="location">
          <span class="meta-label">分析区域</span>
          <span class="meta-value">{{ location }}</span>
        </div>
        <div class="meta-item" v-if="timeRange">
          <span class="meta-label">时间范围</span>
          <span class="meta-value">{{ timeRange }}</span>
        </div>
      </div>
    </div>

    <!-- 核心气象指标卡片 -->
    <div v-if="meteorologicalMetrics" class="metrics-grid">
      <div
        v-for="(value, key) in meteorologicalMetrics"
        :key="key"
        class="metric-card"
        :class="getMetricCardClass(key)"
      >
        <div class="metric-icon">
          {{ getMetricIcon(key) }}
        </div>
        <div class="metric-content">
          <div class="metric-label">{{ getMetricLabel(key) }}</div>
          <div class="metric-value">{{ value }}</div>
        </div>
      </div>
    </div>

    <!-- 分析结论 -->
    <div class="analysis-section" v-if="analysisConclusion">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
          <path d="M16 13H8" />
          <path d="M16 17H8" />
          <path d="M10 9H8" />
        </svg>
        分析结论
      </h3>
      <div class="analysis-content">
        <MarkdownRenderer :content="analysisConclusion" />
      </div>
    </div>

    <!-- 轨迹分析结果 -->
    <div v-if="trajectoryData" class="analysis-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
        传输路径分析
      </h3>
      <div class="trajectory-summary">
        <div class="trajectory-metric">
          <span class="metric-label">主导风向</span>
          <span class="metric-value">{{ trajectoryData.dominantDirection || 'N/A' }}</span>
        </div>
        <div class="trajectory-metric" v-if="trajectoryData.totalDistance">
          <span class="metric-label">传输距离</span>
          <span class="metric-value">{{ trajectoryData.totalDistance }} km</span>
        </div>
        <div class="trajectory-metric" v-if="trajectoryData.transportTime">
          <span class="metric-label">传输时长</span>
          <span class="metric-value">{{ trajectoryData.transportTime }} 小时</span>
        </div>
      </div>
      <div class="trajectory-description">
        <MarkdownRenderer :content="trajectoryData.summary || trajectoryData.description" />
      </div>
    </div>

    <!-- 可视化图表 -->
    <div v-if="hasVisualizations" class="visualization-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 3v18h18" />
          <path d="M18 17V9" />
          <path d="M13 17V5" />
          <path d="M8 17v-3" />
        </svg>
        数据可视化
      </h3>
      <VisualizationPanel
        :content="visualizationContent"
        :history="visualizationHistory"
      />
    </div>

    <!-- 工具执行详情 -->
    <div v-if="toolDetails && toolDetails.length" class="tools-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
        工具执行详情
      </h3>
      <div class="tools-list">
        <div
          v-for="tool in toolDetails"
          :key="tool.name"
          class="tool-item"
          :class="tool.status"
        >
          <div class="tool-status-indicator">
            <svg v-if="tool.status === 'success'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <svg v-else-if="tool.status === 'error'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div class="tool-info">
            <div class="tool-name">{{ tool.name }}</div>
            <div class="tool-purpose">{{ tool.purpose }}</div>
          </div>
          <div class="tool-time" v-if="tool.executionTime">
            {{ tool.executionTime }}ms
          </div>
        </div>
      </div>
    </div>

    <!-- 调试信息 -->
    <div class="debug-section">
      <details>
        <summary>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 9h6v6H9z" />
            <path d="M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9c2.49 0 4.75 1 6.36 2.64" />
            <path d="M15 3v6h6" />
          </svg>
          调试信息
        </summary>
        <pre>{{ JSON.stringify(debugInfo, null, 2) }}</pre>
      </details>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import VisualizationPanel from './VisualizationPanel.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  result: {
    type: Object,
    required: true
  },
  visualizationContent: {
    type: Object,
    default: null
  },
  visualizationHistory: {
    type: Array,
    default: () => []
  }
})

const resultTitle = computed(() => {
  return props.result?.title || '气象分析结果'
})

const summary = computed(() => {
  return props.result?.summary || ''
})

const expertType = computed(() => {
  return props.result?.expertType || '气象分析专家'
})

const location = computed(() => {
  return props.result?.location || ''
})

const timeRange = computed(() => {
  return props.result?.timeRange || ''
})

const meteorologicalMetrics = computed(() => {
  return props.result?.meteorologicalMetrics || null
})

const analysisConclusion = computed(() => {
  return props.result?.analysisConclusion || props.result?.analysis || ''
})

const trajectoryData = computed(() => {
  return props.result?.trajectoryData || null
})

const toolDetails = computed(() => {
  return props.result?.toolDetails || []
})

const debugInfo = computed(() => {
  return props.result || {}
})

const hasVisualizations = computed(() => {
  return props.visualizationContent ||
         (props.visualizationHistory && props.visualizationHistory.length > 0)
})

const getMetricCardClass = (key) => {
  const classMap = {
    'temperature': 'metric-temperature',
    'humidity': 'metric-humidity',
    'windSpeed': 'metric-wind',
    'windDirection': 'metric-direction',
    'pressure': 'metric-pressure',
    'visibility': 'metric-visibility'
  }
  return classMap[key] || ''
}

const getMetricIcon = (key) => {
  const iconMap = {
    'temperature': '🌡️',
    'humidity': '💧',
    'windSpeed': '💨',
    'windDirection': '🧭',
    'pressure': '🎯',
    'visibility': '👁️',
    'boundaryLayer': '📏',
    'precipitation': '🌧️'
  }
  return iconMap[key] || '📊'
}

const getMetricLabel = (key) => {
  const labelMap = {
    'temperature': '平均温度',
    'humidity': '平均湿度',
    'windSpeed': '平均风速',
    'windDirection': '主导风向',
    'pressure': '气压',
    'visibility': '能见度',
    'boundaryLayer': '边界层高度',
    'precipitation': '降水量'
  }
  return labelMap[key] || key
}
</script>

<style lang="scss" scoped>
.meteorology-result-display {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.result-header {
  border-bottom: 2px solid #e3f2fd;
  padding-bottom: 20px;
  margin-bottom: 24px;
}

.header-content {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.header-icon {
  font-size: 48px;
  line-height: 1;
}

.header-text {
  flex: 1;

  h2 {
    margin: 0 0 8px 0;
    font-size: 24px;
    font-weight: 600;
    color: #1976d2;
  }

  .result-summary {
    margin: 0;
    font-size: 15px;
    color: #666;
    line-height: 1.6;
  }
}

.header-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;

  .meta-label {
    font-size: 12px;
    color: #888;
    font-weight: 500;
  }

  .meta-value {
    font-size: 14px;
    color: #333;
    font-weight: 500;
  }
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.metric-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  padding: 20px;
  color: white;
  display: flex;
  align-items: center;
  gap: 16px;

  &.metric-temperature {
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  }

  &.metric-humidity {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  }

  &.metric-wind {
    background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
  }

  &.metric-direction {
    background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
  }

  &.metric-pressure {
    background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);
  }

  &.metric-visibility {
    background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
  }
}

.metric-icon {
  font-size: 36px;
  line-height: 1;
}

.metric-content {
  flex: 1;

  .metric-label {
    font-size: 13px;
    opacity: 0.9;
    margin-bottom: 4px;
  }

  .metric-value {
    font-size: 24px;
    font-weight: 700;
    line-height: 1;
  }
}

.analysis-section {
  margin-bottom: 32px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;

  svg {
    color: #1976d2;
  }
}

.analysis-content {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
  border-left: 4px solid #1976d2;

  :deep(p) {
    margin: 0 0 12px 0;
    line-height: 1.7;
    color: #444;

    &:last-child {
      margin-bottom: 0;
    }
  }

  :deep(ul), :deep(ol) {
    margin: 12px 0;
    padding-left: 24px;

    li {
      margin-bottom: 8px;
      line-height: 1.6;
      color: #444;
    }
  }

  :deep(strong) {
    color: #1976d2;
    font-weight: 600;
  }
}

.trajectory-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 16px;
  background: #e3f2fd;
  border-radius: 8px;
}

.trajectory-metric {
  display: flex;
  flex-direction: column;
  gap: 4px;

  .metric-label {
    font-size: 12px;
    color: #666;
  }

  .metric-value {
    font-size: 18px;
    font-weight: 600;
    color: #1976d2;
  }
}

.trajectory-description {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;

  :deep(p) {
    margin: 0 0 8px 0;
    line-height: 1.6;
    color: #444;
  }
}

.visualization-section {
  margin-bottom: 32px;
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 8px;
  border-left: 4px solid #e0e0e0;

  &.success {
    border-left-color: #2e7d32;

    .tool-status-indicator {
      color: #2e7d32;
    }
  }

  &.error {
    border-left-color: #d32f2f;

    .tool-status-indicator {
      color: #d32f2f;
    }
  }

  &.running {
    border-left-color: #f57c00;

    .tool-status-indicator {
      color: #f57c00;
    }
  }
}

.tool-status-indicator {
  flex-shrink: 0;
}

.tool-info {
  flex: 1;

  .tool-name {
    font-size: 14px;
    font-weight: 500;
    color: #333;
    margin-bottom: 2px;
  }

  .tool-purpose {
    font-size: 12px;
    color: #666;
  }
}

.tool-time {
  font-size: 12px;
  color: #888;
  font-family: monospace;
}

.debug-section {
  margin-top: 32px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;

  details {
    summary {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      font-size: 13px;
      color: #666;
      user-select: none;

      &:hover {
        color: #1976d2;
      }
    }

    pre {
      margin-top: 12px;
      padding: 16px;
      background: #f5f5f5;
      border-radius: 8px;
      font-size: 12px;
      line-height: 1.5;
      color: #666;
      max-height: 400px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
  }
}

@media (max-width: 768px) {
  .meteorology-result-display {
    padding: 16px;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .trajectory-summary {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
