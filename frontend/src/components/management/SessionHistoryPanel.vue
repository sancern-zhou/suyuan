<template>
  <div class="management-panel session-history-panel">
    <div class="panel-header">
      <h3>会话历史</h3>
      <button class="panel-btn small" @click="$emit('refresh-sessions')" :disabled="sessionHistoryLoading">
        {{ sessionHistoryLoading ? '刷新中...' : '刷新' }}
      </button>
      <button class="panel-btn small" @click="$emit('cleanup-sessions')">清理过期</button>
      <button class="panel-btn close-btn" @click="$emit('close')">关闭</button>
    </div>

    <div class="session-history-content">
      <!-- 统计信息 -->
      <div v-if="sessionHistoryStats" class="session-stats">
        <div class="session-stat-item">
          <span class="session-stat-icon">📊</span>
          <div class="session-stat-info">
            <span class="session-stat-value">{{ sessionHistoryStats.total }}</span>
            <span class="session-stat-label">总会话数</span>
          </div>
        </div>
        <div class="session-stat-item">
          <span class="session-stat-icon">💾</span>
          <div class="session-stat-info">
            <span class="session-stat-value">{{ sessionHistoryStats.total_data_count }}</span>
            <span class="session-stat-label">数据项</span>
          </div>
        </div>
        <div class="session-stat-item">
          <span class="session-stat-icon">📈</span>
          <div class="session-stat-info">
            <span class="session-stat-value">{{ sessionHistoryStats.total_visual_count }}</span>
            <span class="session-stat-label">可视化</span>
          </div>
        </div>
        <div class="session-stat-item">
          <span class="session-stat-icon">❌</span>
          <div class="session-stat-info">
            <span class="session-stat-value">{{ sessionHistoryStats.error_count || 0 }}</span>
            <span class="session-stat-label">失败</span>
          </div>
        </div>
      </div>

      <!-- 会话列表 -->
      <div class="session-list">
        <div v-if="sessionHistoryLoading" class="session-loading">
          <span class="session-spinner">⏳</span>
          <p>加载会话列表...</p>
        </div>

        <div v-else-if="sessions.length === 0" class="session-empty">
          <span class="session-empty-icon">📭</span>
          <p>暂无会话记录</p>
        </div>

        <div v-else>
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            @click="$emit('restore-session', session.session_id)"
          >
            <div class="session-info">
              <div class="session-query">{{ truncateQuery(session.query) }}</div>
              <div class="session-meta">
                <span class="session-id">{{ getShortId(session.session_id) }}</span>
                <span v-if="session.has_error" class="error-icon">❌</span>
                <span class="session-time">{{ formatTime(session.updated_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// Props
const props = defineProps({
  sessions: {
    type: Array,
    default: () => []
  },
  sessionHistoryStats: {
    type: Object,
    default: null
  },
  sessionHistoryLoading: {
    type: Boolean,
    default: false
  }
})

// Methods
const truncateQuery = (query, maxLength = 80) => {
  if (!query) return '无查询'
  if (query.length <= maxLength) return query
  return query.substring(0, maxLength) + '...'
}

const getShortId = (sessionId) => {
  if (!sessionId) return '未知'
  return sessionId.substring(0, 8)
}

const formatTime = (timestamp) => {
  if (!timestamp) return '未知'
  try {
    const date = new Date(timestamp)
    const now = new Date()
    const diff = now - date

    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  } catch {
    return '无效时间'
  }
}

const formatFullTime = (timestamp) => {
  if (!timestamp) return '未知'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return '无效时间'
  }
}

// Emit events
defineEmits([
  'close',
  'refresh-sessions',
  'cleanup-sessions',
  'restore-session'
])
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
  flex-wrap: wrap;
  gap: 10px;
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

.panel-btn.danger {
  border-color: #dc3545;
  color: #dc3545;
}

.panel-btn.danger:hover:not(:disabled) {
  background: #dc3545;
  color: white;
}

.session-history-content {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.session-stats {
  display: flex;
  gap: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
}

.session-stat-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: white;
  border-radius: 6px;
}

.session-stat-icon {
  font-size: 24px;
}

.session-stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #1976d2;
}

.session-stat-label {
  font-size: 12px;
  color: #6c757d;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.session-loading,
.session-empty {
  text-align: center;
  padding: 40px 20px;
  color: #6c757d;
}

.session-spinner {
  font-size: 32px;
  display: block;
  margin-bottom: 10px;
}

.session-empty-icon {
  font-size: 48px;
  display: block;
  margin-bottom: 10px;
}

.session-item {
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 12px 15px;
  cursor: pointer;
  transition: all 0.2s;
}

.session-item:hover {
  border-color: #1976d2;
  background: #f8f9fa;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.15);
}

.error-icon {
  font-size: 14px;
  margin-left: 8px;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-query {
  font-weight: 500;
  color: #212529;
  font-size: 14px;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #6c757d;
}
</style>