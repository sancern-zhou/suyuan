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
    <div v-if="showEra5HistoricalBackfill" class="era5-historical-card">
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
import { projectConfig } from '@/config/projectConfig.js'

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
    const showEra5HistoricalBackfill = projectConfig.isFeatureEnabled('era5HistoricalBackfill', true)

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
        const [systemData, fetchersData] = await Promise.all([
          api.getSystemStatus(),
          api.getFetchersStatus()
        ])
        systemStatus.value = {
          ...systemData,
          fetchers: fetchersData
        }
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
      showEra5HistoricalBackfill,
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
  color: var(--text-1);
  margin-bottom: 8px;
}

.subtitle {
  color: var(--text-2);
  font-size: 16px;
}

.header-actions {
  display: flex;
  align-items: center;
}

.view-switch {
  display: inline-flex;
  border: 1px solid var(--border-2);
  border-radius: 6px;
  overflow: hidden;
}

.view-btn {
  border: none;
  background: white;
  padding: 6px 12px;
  font-size: 13px;
  color: var(--text-2);
  cursor: pointer;
  border-left: 1px solid var(--border-2);

  &:first-child {
    border-left: none;
  }

  &.active {
    background: var(--color-primary);
    color: var(--bg-container);
    border-color: var(--color-primary);
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
  color: var(--text-1);
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
  background: var(--bg-muted);
  border-radius: 4px;
}

.status-item .label {
  font-weight: 500;
  color: var(--text-2);
}

.status-value {
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 4px;
}

.status-running {
  color: var(--color-success);
  background: var(--color-success-bg);
}

.status-stopped {
  color: var(--color-danger);
  background: var(--color-danger-bg);
}

.status-idle {
  color: var(--color-primary);
  background: var(--color-primary-bg);
}

.status-disabled {
  color: var(--text-2);
  background: var(--bg-hover);
}

.status-error {
  color: var(--color-danger);
  background: var(--color-danger-bg);
}

.fetchers-list h2 {
  font-size: 20px;
  margin-bottom: 16px;
  color: var(--text-1);
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
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-active);
}

.btn-secondary {
  background: var(--text-2);
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: var(--text-2);
}

.btn-warning {
  background: var(--color-warning);
  color: white;
}

.btn-warning:hover:not(:disabled) {
  background: var(--color-warning);
}

.btn-success {
  background: var(--color-success);
  color: white;
}

.btn-success:hover:not(:disabled) {
  background: var(--color-success);
}

.btn-refresh {
  background: var(--chart-5);
  color: white;
}

.btn-refresh:hover:not(:disabled) {
  background: var(--chart-5);
}

.loading, .error {
  text-align: center;
  padding: 40px;
  color: var(--text-2);
}

.spinner {
  border: 4px solid var(--bg-hover);
  border-top: 4px solid var(--color-primary);
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
  border-bottom: 2px solid var(--bg-muted);
}

.fetcher-header h3 {
  margin: 0;
  font-size: 18px;
  color: var(--text-1);
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
  color: var(--text-2);
  width: 100px;
  flex-shrink: 0;
}

.info-row .value {
  color: var(--text-1);
  flex: 1;
}

.schedule {
  background: var(--bg-muted);
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
  color: var(--text-1);
}

.modal p {
  color: var(--text-2);
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
  background: var(--bg-muted);
  border-radius: 4px;
  cursor: pointer;
}

.checkbox-label:hover {
  background: var(--bg-hover);
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
  background: var(--color-success);
}

.notification.error {
  background: var(--color-danger);
}

.notification.info {
  background: var(--color-primary);
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
  color: var(--text-1);
}

.era5-historical-card .description {
  color: var(--text-2);
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
  color: var(--text-2);
  white-space: nowrap;
}

.date-input {
  padding: 8px 12px;
  border: 1px solid var(--border-3);
  border-radius: 4px;
  font-size: 14px;
  color: var(--text-1);
  background: white;
}

.date-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(52,152,219,0.2);
}

/* 补采结果样式 */
.fetch-result {
  margin-top: 20px;
  border-radius: 8px;
  overflow: hidden;
}

.fetch-result.success {
  border: 1px solid var(--color-success);
  background: var(--color-success-bg);
}

.fetch-result.warning {
  border: 1px solid var(--color-warning);
  background: var(--color-warning-bg);
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
  color: var(--color-success);
}

.fetch-result.warning .result-icon {
  color: var(--color-warning);
}

.result-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
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
  color: var(--text-2);
  margin-right: 8px;
}

.result-row .value {
  color: var(--text-1);
  font-weight: 600;
}

.result-row .success-text {
  color: var(--color-success);
}

.result-row .error-text {
  color: var(--color-danger);
}
</style>
