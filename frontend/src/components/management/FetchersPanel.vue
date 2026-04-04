<template>
  <div class="management-panel fetchers-panel">
    <div class="panel-header">
      <h3>数据抓取管理</h3>
      <button class="panel-btn close-btn" @click="$emit('close')">关闭</button>
    </div>

    <div class="fetchers-content">
      <!-- 系统状态 -->
      <div class="fetchers-status-card">
        <h4>系统状态</h4>
        <div class="status-grid" v-if="fetcherSystemStatus">
          <div class="status-item">
            <span class="label">调度器:</span>
            <span :class="['status-value', fetcherSystemStatus.fetchers?.scheduler_running ? 'running' : 'stopped']">
              {{ fetcherSystemStatus.fetchers?.scheduler_running ? '运行中' : '已停止' }}
            </span>
          </div>
          <div class="status-item">
            <span class="label">数据库:</span>
            <span :class="['status-value', fetcherSystemStatus.database?.enabled ? 'running' : 'stopped']">
              {{ fetcherSystemStatus.database?.enabled ? '已连接' : '未连接' }}
            </span>
          </div>
          <div class="status-item">
            <span class="label">Fetchers:</span>
            <span class="status-value">{{ Object.keys(fetcherSystemStatus.fetchers?.fetchers || {}).length }} 个</span>
          </div>
          <div class="status-item">
            <span class="label">LLM工具:</span>
            <span class="status-value">{{ fetcherSystemStatus.llm_tools?.count || 0 }} 个</span>
          </div>
        </div>
      </div>

      <!-- ERA5 历史数据补采 -->
      <div class="era5-card">
        <h4>ERA5 历史数据补采</h4>
        <p class="era5-desc">手动补采指定日期的 ERA5 气象数据（广东省全境 825 个网格点）</p>

        <div class="era5-controls">
          <div class="date-input-group">
            <label>选择日期：</label>
            <input
              type="date"
              v-model="era5HistoricalDate"
              :max="todayStr"
              class="date-input"
            />
          </div>
          <button
            @click="$emit('fetch-era5', era5HistoricalDate)"
            :disabled="!era5HistoricalDate || fetcherOperating"
            class="panel-btn primary"
          >
            开始补采
          </button>
        </div>

        <!-- 补采结果 -->
        <div v-if="era5FetchResult" :class="['fetch-result', era5FetchResult.success ? 'success' : 'warning']">
          <div class="result-header">
            <span class="result-icon">{{ era5FetchResult.success ? '✓' : '!' }}</span>
            <span class="result-title">{{ era5FetchResult.message }}</span>
          </div>
          <div class="result-details">
            <div class="result-row">
              <span class="label">日期：</span>
              <span class="value">{{ era5FetchResult.date }}</span>
            </div>
            <div class="result-row">
              <span class="label">网格点数：</span>
              <span class="value">{{ era5FetchResult.grid_count }}</span>
            </div>
            <div class="result-row">
              <span class="label">成功：</span>
              <span class="value success-text">{{ era5FetchResult.success_count }}</span>
            </div>
            <div class="result-row">
              <span class="label">失败：</span>
              <span :class="['value', era5FetchResult.failed_count > 0 ? 'error-text' : '']">
                {{ era5FetchResult.failed_count }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Fetchers 列表 -->
      <div class="fetchers-list-section">
        <div class="section-header">
          <h4>数据获取器列表</h4>
          <button @click="$emit('refresh-status')" :disabled="fetcherLoading" class="panel-btn small">
            {{ fetcherLoading ? '刷新中...' : '刷新' }}
          </button>
        </div>

        <div v-if="fetcherLoading" class="fetcher-loading">
          <div class="spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else-if="fetcherError" class="fetcher-error">
          <p>错误: {{ fetcherError }}</p>
          <button @click="$emit('refresh-status')" class="panel-btn small">重试</button>
        </div>

        <div v-else class="fetcher-cards">
          <div
            v-for="(fetcher, name) in fetcherSystemStatus?.fetchers?.fetchers || {}"
            :key="name"
            class="fetcher-card"
          >
            <div class="fetcher-card-header">
              <h5>{{ fetcher.name }}</h5>
              <span :class="['status-badge', getFetcherStatusClass(fetcher.status)]">
                {{ getFetcherStatusText(fetcher.status) }}
              </span>
            </div>

            <div class="fetcher-card-info">
              <div class="info-row">
                <span class="label">描述:</span>
                <span class="value">{{ fetcher.description }}</span>
              </div>
              <div class="info-row">
                <span class="label">周期:</span>
                <code class="schedule">{{ fetcher.schedule }}</code>
              </div>
              <div class="info-row">
                <span class="label">版本:</span>
                <span class="value">{{ fetcher.version }}</span>
              </div>
            </div>

            <div class="fetcher-card-actions">
              <button
                @click="$emit('trigger-fetcher', name)"
                :disabled="fetcherOperating"
                class="panel-btn small primary"
              >
                触发
              </button>
              <button
                v-if="fetcher.enabled"
                @click="$emit('pause-fetcher', name)"
                :disabled="fetcherOperating"
                class="panel-btn small warning"
              >
                暂停
              </button>
              <button
                v-else
                @click="$emit('resume-fetcher', name)"
                :disabled="fetcherOperating"
                class="panel-btn small success"
              >
                恢复
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

// Props
const props = defineProps({
  fetcherSystemStatus: {
    type: Object,
    default: null
  },
  fetcherLoading: {
    type: Boolean,
    default: false
  },
  fetcherError: {
    type: String,
    default: null
  },
  fetcherOperating: {
    type: Boolean,
    default: false
  },
  era5FetchResult: {
    type: Object,
    default: null
  }
})

// State
const era5HistoricalDate = ref('')

// Computed
const todayStr = computed(() => {
  return new Date().toISOString().split('T')[0]
})

// Methods
const getFetcherStatusClass = (status) => {
  const classMap = {
    running: 'running',
    stopped: 'stopped',
    error: 'error',
    paused: 'paused'
  }
  return classMap[status] || 'unknown'
}

const getFetcherStatusText = (status) => {
  const textMap = {
    running: '运行中',
    stopped: '已停止',
    error: '错误',
    paused: '已暂停'
  }
  return textMap[status] || status
}

// Emit events
defineEmits(['close', 'fetch-era5', 'refresh-status', 'trigger-fetcher', 'pause-fetcher', 'resume-fetcher'])
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
  background: white;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid #1976d2;
  background: white;
  color: #1976d2;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.panel-btn:hover:not(:disabled) {
  background: #1976d2;
  color: white;
}

.panel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.panel-btn.small {
  padding: 4px 8px;
  font-size: 12px;
}

.panel-btn.primary {
  background: #1976d2;
  color: white;
}

.panel-btn.primary:hover:not(:disabled) {
  background: #1565c0;
}

.panel-btn.warning {
  border-color: #ff9800;
  color: #ff9800;
}

.panel-btn.warning:hover:not(:disabled) {
  background: #ff9800;
  color: white;
}

.panel-btn.success {
  border-color: #4caf50;
  color: #4caf50;
}

.panel-btn.success:hover:not(:disabled) {
  background: #4caf50;
  color: white;
}

.fetchers-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.fetchers-status-card {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
}

.fetchers-status-card h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #495057;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: white;
  border-radius: 6px;
}

.status-item .label {
  font-size: 13px;
  color: #6c757d;
}

.status-item .status-value {
  font-size: 13px;
  font-weight: 500;
}

.status-item .status-value.running {
  color: #28a745;
}

.status-item .status-value.stopped {
  color: #dc3545;
}

.era5-card {
  background: #e3f2fd;
  border-radius: 8px;
  padding: 15px;
}

.era5-card h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: #1565c0;
}

.era5-desc {
  margin: 0 0 12px 0;
  font-size: 12px;
  color: #6c757d;
}

.era5-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.date-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-input-group label {
  font-size: 13px;
  color: #495057;
}

.date-input {
  padding: 6px 10px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 13px;
}

.fetch-result {
  padding: 12px;
  border-radius: 6px;
  background: white;
}

.fetch-result.success {
  border-left: 4px solid #28a745;
}

.fetch-result.warning {
  border-left: 4px solid #ffc107;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.result-icon {
  font-size: 16px;
  font-weight: bold;
}

.result-title {
  font-weight: 500;
  color: #495057;
}

.result-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
}

.result-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.result-row .label {
  color: #6c757d;
}

.result-row .value {
  font-weight: 500;
  color: #495057;
}

.result-row .success-text {
  color: #28a745;
}

.result-row .error-text {
  color: #dc3545;
}

.fetchers-list-section {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #495057;
}

.fetcher-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  gap: 12px;
}

.spinner {
  width: 30px;
  height: 30px;
  border: 3px solid #f3f3f3;
  border-top: 3px solid #1976d2;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.fetcher-loading p {
  margin: 0;
  color: #6c757d;
  font-size: 14px;
}

.fetcher-error {
  padding: 20px;
  background: #f8d7da;
  border-radius: 6px;
  color: #721c24;
  text-align: center;
}

.fetcher-error p {
  margin: 0 0 12px 0;
}

.fetcher-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.fetcher-card {
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 12px;
}

.fetcher-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.fetcher-card-header h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #212529;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.status-badge.running {
  background: #d4edda;
  color: #155724;
}

.status-badge.stopped {
  background: #f8d7da;
  color: #721c24;
}

.status-badge.error {
  background: #f8d7da;
  color: #721c24;
}

.status-badge.paused {
  background: #fff3cd;
  color: #856404;
}

.status-badge.unknown {
  background: #e2e3e5;
  color: #383d41;
}

.fetcher-card-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.info-row .label {
  color: #6c757d;
}

.info-row .value {
  color: #495057;
}

.info-row code.schedule {
  padding: 2px 6px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 3px;
  font-size: 11px;
}

.fetcher-card-actions {
  display: flex;
  gap: 8px;
}
</style>