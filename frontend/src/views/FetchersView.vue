<template>
  <div class="fetchers-view">
    <!-- 页面标题 -->
    <div class="header">
      <div class="header-main">
        <h1>数据获取后台管理</h1>
        <p class="subtitle">Fetchers 状态监控与控制</p>
      </div>
      <div class="header-actions">
        <div class="view-switch">
          <button
            class="view-btn"
            :class="{ active: isAnalysisActive }"
            @click="goAnalysis"
          >
            分析页面
          </button>
          <button
            class="view-btn"
            :class="{ active: isFetchersActive }"
            @click="goFetchers"
          >
            Fetchers管理
          </button>
        </div>
      </div>
    </div>

    <!-- 总体状态卡片 -->
    <div class="status-card">
      <h2>系统状态</h2>
      <div class="status-grid" v-if="systemStatus">
        <div class="status-item">
          <span class="label">调度器状态:</span>
          <span :class="['status-value', systemStatus.fetchers.scheduler_running ? 'status-running' : 'status-stopped']">
            {{ systemStatus.fetchers.scheduler_running ? '运行中' : '已停止' }}
          </span>
        </div>
        <div class="status-item">
          <span class="label">数据库:</span>
          <span :class="['status-value', systemStatus.database.enabled ? 'status-running' : 'status-stopped']">
            {{ systemStatus.database.enabled ? '已连接' : '未连接' }}
          </span>
        </div>
        <div class="status-item">
          <span class="label">注册Fetchers:</span>
          <span class="status-value">{{ Object.keys(systemStatus.fetchers.fetchers || {}).length }} 个</span>
        </div>
        <div class="status-item">
          <span class="label">LLM工具:</span>
          <span class="status-value">{{ systemStatus.llm_tools.count }} 个</span>
        </div>
      </div>
    </div>

    <!-- ERA5 历史数据补采区域 -->
    <div class="era5-historical-card">
      <h2>ERA5 历史数据补采</h2>
      <p class="description">手动补采指定日期的 ERA5 气象数据（广东省全境 825 个网格点）</p>

      <div class="date-picker-row">
        <div class="date-input-group">
          <label for="era5-date">选择日期：</label>
          <input
            type="date"
            id="era5-date"
            v-model="era5HistoricalDate"
            :max="todayStr"
            class="date-input"
          />
        </div>
        <button
          @click="fetchEra5Historical"
          :disabled="!era5HistoricalDate || isOperating"
          class="btn btn-primary"
        >
          开始补采
        </button>
      </div>

      <!-- 补采进度显示 -->
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
            <span class="label">跳过：</span>
            <span class="value">{{ era5FetchResult.skipped_count }}</span>
          </div>
          <div class="result-row">
            <span class="label">失败：</span>
            <span :class="['value', era5FetchResult.failed_count > 0 ? 'error-text' : '']">
              {{ era5FetchResult.failed_count }}
            </span>
          </div>
          <div class="result-row">
            <span class="label">成功率：</span>
            <span class="value">{{ era5FetchResult.success_rate }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Fetchers列表 -->
    <div class="fetchers-list">
      <h2>数据获取器列表</h2>
      <div class="actions-bar">
        <button @click="refreshStatus" :disabled="loading" class="btn btn-refresh">
          <span v-if="!loading">刷新状态</span>
          <span v-else>刷新中...</span>
        </button>
        <button @click="showCreateDialog = true" class="btn btn-primary">
          手动触发
        </button>
      </div>

      <div v-if="loading" class="loading">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <div v-else-if="error" class="error">
        <p>错误: {{ error }}</p>
        <button @click="refreshStatus" class="btn btn-retry">重试</button>
      </div>

      <div v-else class="fetcher-cards">
        <div
          v-for="(fetcher, name) in systemStatus?.fetchers?.fetchers || {}"
          :key="name"
          class="fetcher-card"
        >
          <div class="fetcher-header">
            <h3>{{ fetcher.name }}</h3>
            <span :class="['status-badge', getStatusClass(fetcher.status)]">
              {{ getStatusText(fetcher.status) }}
            </span>
          </div>

          <div class="fetcher-info">
            <div class="info-row">
              <span class="label">描述:</span>
              <span class="value">{{ fetcher.description }}</span>
            </div>
            <div class="info-row">
              <span class="label">调度周期:</span>
              <code class="schedule">{{ fetcher.schedule }}</code>
            </div>
            <div class="info-row">
              <span class="label">状态:</span>
              <span class="value">{{ fetcher.status }}</span>
            </div>
            <div class="info-row">
              <span class="label">版本:</span>
              <span class="value">{{ fetcher.version }}</span>
            </div>
          </div>

          <div class="fetcher-actions">
            <button
              @click="triggerFetcher(name)"
              :disabled="isOperating"
              class="btn btn-primary"
            >
              手动触发
            </button>
            <button
              v-if="fetcher.enabled"
              @click="pauseFetcher(name)"
              :disabled="isOperating"
              class="btn btn-warning"
            >
              暂停
            </button>
            <button
              v-else
              @click="resumeFetcher(name)"
              :disabled="isOperating"
              class="btn btn-success"
            >
              恢复
            </button>
            <button
              @click="viewLogs(name)"
              class="btn btn-secondary"
            >
              查看日志
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 手动触发对话框 -->
    <div v-if="showCreateDialog" class="modal-overlay" @click="showCreateDialog = false">
      <div class="modal" @click.stop>
        <h3>手动触发 Fetchers</h3>
        <p>选择要触发的数据获取器:</p>
        <div class="fetcher-selector">
          <label
            v-for="(fetcher, name) in systemStatus?.fetchers?.fetchers || {}"
            :key="name"
            class="checkbox-label"
          >
            <input
              type="checkbox"
              v-model="selectedFetchers"
              :value="name"
            />
            <span>{{ fetcher.name }} - {{ fetcher.description }}</span>
          </label>
        </div>
        <div class="modal-actions">
          <button @click="showCreateDialog = false" class="btn btn-secondary">
            取消
          </button>
          <button
            @click="triggerSelectedFetchers"
            :disabled="selectedFetchers.length === 0 || isOperating"
            class="btn btn-primary"
          >
            确认触发
          </button>
        </div>
      </div>
    </div>

    <!-- 操作结果通知 -->
    <div v-if="notification" :class="['notification', notification.type]">
      {{ notification.message }}
      <button @click="notification = null" class="close-btn">×</button>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/services/api.js'

export default {
  name: 'FetchersView',
  setup() {
    const systemStatus = ref(null)
    const loading = ref(false)
    const error = ref(null)
    const isOperating = ref(false)
    const showCreateDialog = ref(false)
    const selectedFetchers = ref([])
    const notification = ref(null)
    const refreshInterval = ref(null)

    // ERA5 历史数据补采相关
    const era5HistoricalDate = ref('')
    const era5FetchResult = ref(null)

    // 获取今天的日期字符串（用于日期选择器最大限制）
    const today = new Date()
    const todayStr = computed(() => {
      return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
    })

    const router = useRouter()
    const route = useRoute()

    const isAnalysisActive = computed(() =>
      route.path === '/' || route.path.startsWith('/session') || route.path.startsWith('/classic')
    )
    const isFetchersActive = computed(() => route.path.startsWith('/fetchers'))

    const goAnalysis = () => {
      if (!isAnalysisActive.value) router.push('/')
    }

    const goFetchers = () => {
      if (!isFetchersActive.value) router.push('/fetchers')
    }

    // 获取状态样式类
    const getStatusClass = (status) => {
      const classes = {
        'idle': 'status-idle',
        'running': 'status-running',
        'disabled': 'status-disabled',
        'error': 'status-error'
      }
      return classes[status] || 'status-unknown'
    }

    // 获取状态文本
    const getStatusText = (status) => {
      const texts = {
        'idle': '空闲',
        'running': '运行中',
        'disabled': '已禁用',
        'error': '错误'
      }
      return texts[status] || status
    }

    // 刷新系统状态
    const refreshStatus = async () => {
      loading.value = true
      error.value = null
      try {
        const data = await api.getSystemStatus()
        systemStatus.value = data
      } catch (err) {
        error.value = err.message
        console.error('Failed to fetch system status:', err)
      } finally {
        loading.value = false
      }
    }

    // 手动触发Fetcher
    const triggerFetcher = async (fetcherName) => {
      isOperating.value = true
      try {
        await api.triggerFetcher(fetcherName)
        showNotification('success', `Fetcher "${fetcherName}" 已触发`)
        await refreshStatus()
      } catch (err) {
        showNotification('error', `触发失败: ${err.message}`)
        console.error('Failed to trigger fetcher:', err)
      } finally {
        isOperating.value = false
      }
    }

    // 触发选中的Fetchers
    const triggerSelectedFetchers = async () => {
      isOperating.value = true
      try {
        for (const fetcherName of selectedFetchers.value) {
          await api.triggerFetcher(fetcherName)
        }
        showNotification('success', `已触发 ${selectedFetchers.value.length} 个Fetchers`)
        showCreateDialog.value = false
        selectedFetchers.value = []
        await refreshStatus()
      } catch (err) {
        showNotification('error', `触发失败: ${err.message}`)
        console.error('Failed to trigger fetchers:', err)
      } finally {
        isOperating.value = false
      }
    }

    // 暂停Fetcher
    const pauseFetcher = async (fetcherName) => {
      isOperating.value = true
      try {
        await api.pauseFetcher(fetcherName)
        showNotification('success', `Fetcher "${fetcherName}" 已暂停`)
        await refreshStatus()
      } catch (err) {
        showNotification('error', `暂停失败: ${err.message}`)
        console.error('Failed to pause fetcher:', err)
      } finally {
        isOperating.value = false
      }
    }

    // 恢复Fetcher
    const resumeFetcher = async (fetcherName) => {
      isOperating.value = true
      try {
        await api.resumeFetcher(fetcherName)
        showNotification('success', `Fetcher "${fetcherName}" 已恢复`)
        await refreshStatus()
      } catch (err) {
        showNotification('error', `恢复失败: ${err.message}`)
        console.error('Failed to resume fetcher:', err)
      } finally {
        isOperating.value = false
      }
    }

    // 查看日志
    const viewLogs = (fetcherName) => {
      showNotification('info', `日志功能开发中... (${fetcherName})`)
    }

    // ERA5 历史数据补采
    const fetchEra5Historical = async () => {
      if (!era5HistoricalDate.value) {
        showNotification('error', '请选择日期')
        return
      }

      isOperating.value = true
      era5FetchResult.value = null

      try {
        const response = await api.post('/fetchers/era5/historical', {
          date: era5HistoricalDate.value
        })

        if (response.data && response.data.data) {
          era5FetchResult.value = response.data.data
          if (response.data.data.success) {
            showNotification('success', `ERA5 数据补采成功`)
          } else {
            showNotification('warning', `ERA5 数据补采完成，部分失败`)
          }
        } else {
          showNotification('error', `补采失败: ${response.message || '未知错误'}`)
        }
      } catch (err) {
        const errorMsg = err.response?.data?.detail || err.message || '未知错误'
        showNotification('error', `ERA5 数据补采失败: ${errorMsg}`)
        console.error('Failed to fetch ERA5 historical data:', err)
      } finally {
        isOperating.value = false
      }
    }

    // 显示通知
    const showNotification = (type, message) => {
      notification.value = { type, message }
      setTimeout(() => {
        notification.value = null
      }, 5000)
    }

    // 组件挂载时刷新状态
    onMounted(() => {
      refreshStatus()
      // 每30秒自动刷新
      refreshInterval.value = setInterval(refreshStatus, 30000)
    })

    // 组件卸载时清理定时器
    onUnmounted(() => {
      if (refreshInterval.value) {
        clearInterval(refreshInterval.value)
      }
    })

    return {
      systemStatus,
      loading,
      error,
      isOperating,
      showCreateDialog,
      selectedFetchers,
      notification,
      getStatusClass,
      getStatusText,
      refreshStatus,
      triggerFetcher,
      triggerSelectedFetchers,
      pauseFetcher,
      resumeFetcher,
      viewLogs,
      fetchEra5Historical,
      era5HistoricalDate,
      era5FetchResult,
      todayStr,
      goAnalysis,
      goFetchers,
      isAnalysisActive,
      isFetchersActive
    }
  }
}
</script>

<style scoped>
.fetchers-view {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  margin-bottom: 30px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.header-main h1 {
  font-size: 32px;
  color: #2c3e50;
  margin-bottom: 8px;
}

.subtitle {
  color: #7f8c8d;
  font-size: 16px;
}

.header-actions {
  display: flex;
  align-items: center;
}

.view-switch {
  display: inline-flex;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  overflow: hidden;
}

.view-btn {
  border: none;
  background: white;
  padding: 6px 12px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
  border-left: 1px solid #e0e0e0;

  &:first-child {
    border-left: none;
  }

  &.active {
    background: #1976d2;
    color: #fff;
    border-color: #1976d2;
  }
}

.status-card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 30px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.status-card h2 {
  font-size: 20px;
  margin-bottom: 16px;
  color: #34495e;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 4px;
}

.status-item .label {
  font-weight: 500;
  color: #495057;
}

.status-value {
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 4px;
}

.status-running {
  color: #27ae60;
  background: #d4edda;
}

.status-stopped {
  color: #e74c3c;
  background: #f8d7da;
}

.status-idle {
  color: #3498db;
  background: #d1ecf1;
}

.status-disabled {
  color: #95a5a6;
  background: #e9ecef;
}

.status-error {
  color: #e74c3c;
  background: #f8d7da;
}

.fetchers-list h2 {
  font-size: 20px;
  margin-bottom: 16px;
  color: #34495e;
}

.actions-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #3498db;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2980b9;
}

.btn-secondary {
  background: #95a5a6;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #7f8c8d;
}

.btn-warning {
  background: #f39c12;
  color: white;
}

.btn-warning:hover:not(:disabled) {
  background: #e67e22;
}

.btn-success {
  background: #27ae60;
  color: white;
}

.btn-success:hover:not(:disabled) {
  background: #229954;
}

.btn-refresh {
  background: #9b59b6;
  color: white;
}

.btn-refresh:hover:not(:disabled) {
  background: #8e44ad;
}

.loading, .error {
  text-align: center;
  padding: 40px;
  color: #7f8c8d;
}

.spinner {
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.fetcher-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
}

.fetcher-card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  transition: transform 0.2s;
}

.fetcher-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.fetcher-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #ecf0f1;
}

.fetcher-header h3 {
  margin: 0;
  font-size: 18px;
  color: #2c3e50;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.fetcher-info {
  margin-bottom: 16px;
}

.info-row {
  display: flex;
  margin-bottom: 8px;
  font-size: 14px;
}

.info-row .label {
  font-weight: 600;
  color: #7f8c8d;
  width: 100px;
  flex-shrink: 0;
}

.info-row .value {
  color: #2c3e50;
  flex: 1;
}

.schedule {
  background: #f8f9fa;
  padding: 4px 8px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

.fetcher-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 8px;
  padding: 24px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
}

.modal h3 {
  margin-top: 0;
  margin-bottom: 8px;
  color: #2c3e50;
}

.modal p {
  color: #7f8c8d;
  margin-bottom: 20px;
}

.fetcher-selector {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: #f8f9fa;
  border-radius: 4px;
  cursor: pointer;
}

.checkbox-label:hover {
  background: #e9ecef;
}

.checkbox-label input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.notification {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 16px 20px;
  border-radius: 4px;
  color: white;
  display: flex;
  align-items: center;
  gap: 12px;
  z-index: 1001;
  min-width: 300px;
}

.notification.success {
  background: #27ae60;
}

.notification.error {
  background: #e74c3c;
}

.notification.info {
  background: #3498db;
}

.close-btn {
  background: none;
  border: none;
  color: white;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ERA5 历史数据补采卡片样式 */
.era5-historical-card {
  background: white;
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 30px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.era5-historical-card h2 {
  font-size: 20px;
  margin-bottom: 8px;
  color: #34495e;
}

.era5-historical-card .description {
  color: #7f8c8d;
  font-size: 14px;
  margin-bottom: 20px;
}

.date-picker-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.date-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-input-group label {
  font-size: 14px;
  color: #495057;
  white-space: nowrap;
}

.date-input {
  padding: 8px 12px;
  border: 1px solid #dcdcdc;
  border-radius: 4px;
  font-size: 14px;
  color: #2c3e50;
  background: white;
}

.date-input:focus {
  outline: none;
  border-color: #3498db;
  box-shadow: 0 0 0 2px rgba(52,152,219,0.2);
}

/* 补采结果样式 */
.fetch-result {
  margin-top: 20px;
  border-radius: 8px;
  overflow: hidden;
}

.fetch-result.success {
  border: 1px solid #27ae60;
  background: #d4edda;
}

.fetch-result.warning {
  border: 1px solid #f39c12;
  background: #fff3cd;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(0,0,0,0.1);
}

.result-icon {
  font-size: 20px;
  font-weight: bold;
}

.fetch-result.success .result-icon {
  color: #27ae60;
}

.fetch-result.warning .result-icon {
  color: #f39c12;
}

.result-title {
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
}

.result-details {
  padding: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.result-row {
  display: flex;
  align-items: center;
  font-size: 14px;
}

.result-row .label {
  color: #7f8c8d;
  margin-right: 8px;
}

.result-row .value {
  color: #2c3e50;
  font-weight: 600;
}

.result-row .success-text {
  color: #27ae60;
}

.result-row .error-text {
  color: #e74c3c;
}
</style>
