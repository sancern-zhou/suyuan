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
      <!-- 过滤器 -->
      <div class="session-filters">
        <button
          v-for="filter in ['all', 'active', 'completed', 'failed', 'archived']"
          :key="filter"
          class="session-filter-btn"
          :class="{ active: sessionHistoryFilter === filter }"
          @click="$emit('set-filter', filter)"
        >
          <span class="filter-icon">{{ getFilterIcon(filter) }}</span>
          <span class="filter-label">{{ getFilterLabel(filter) }}</span>
          <span v-if="getFilterCount(filter) > 0" class="filter-count">
            {{ getFilterCount(filter) }}
          </span>
        </button>
      </div>

      <!-- 批量操作 -->
      <div v-if="selectedSessionIds.length > 0" class="session-batch-actions">
        <span class="batch-selected-count">已选择 {{ selectedSessionIds.length }} 个会话</span>
        <button class="panel-btn small danger" @click="$emit('batch-delete', selectedSessionIds)">批量删除</button>
        <button class="panel-btn small" @click="$emit('clear-selection')">取消选择</button>
      </div>

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
      </div>

      <!-- 会话列表 -->
      <div class="session-list">
        <div v-if="sessionHistoryLoading" class="session-loading">
          <span class="session-spinner">⏳</span>
          <p>加载会话列表...</p>
        </div>

        <div v-else-if="sessions.length === 0" class="session-empty">
          <span class="session-empty-icon">📭</span>
          <p>暂无{{ sessionHistoryFilter === 'all' ? '' : getFilterLabel(sessionHistoryFilter) }}会话</p>
        </div>

        <div v-else>
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            :class="[getStateClass(session.state), { 'session-expanded': session.isExpanded }]"
          >
            <!-- 会话头部 -->
            <div class="session-header" @click="$emit('toggle-expand', session)">
              <div class="session-header-left">
                <input
                  type="checkbox"
                  :checked="selectedSessionIds.includes(session.session_id)"
                  @click.stop="$emit('toggle-selection', session.session_id)"
                  class="session-checkbox"
                />
                <span class="session-state-icon">{{ getStateIcon(session.state) }}</span>
                <div class="session-info">
                  <div class="session-query">{{ truncateQuery(session.query) }}</div>
                  <div class="session-meta">
                    <span class="session-id">{{ getShortId(session.session_id) }}</span>
                    <span class="session-time">{{ formatTime(session.updated_at) }}</span>
                  </div>
                </div>
              </div>
              <div class="session-header-right">
                <span class="session-expand-icon">{{ session.isExpanded ? '▲' : '▼' }}</span>
              </div>
            </div>

            <!-- 展开的详情 -->
            <div v-if="session.isExpanded" class="session-details">
              <div class="session-detail-row">
                <span class="session-detail-label">创建时间:</span>
                <span class="session-detail-value">{{ formatFullTime(session.created_at) }}</span>
              </div>
              <div class="session-detail-row">
                <span class="session-detail-label">更新时间:</span>
                <span class="session-detail-value">{{ formatFullTime(session.updated_at) }}</span>
              </div>

              <div class="session-stats">
                <div class="session-stat-box">
                  <span class="session-stat-label-small">数据</span>
                  <span class="session-stat-value-small">{{ session.data_count }}</span>
                </div>
                <div class="session-stat-box">
                  <span class="session-stat-label-small">图表</span>
                  <span class="session-stat-value-small">{{ session.visual_count }}</span>
                </div>
              </div>

              <div class="session-actions">
                <button
                  v-if="session.state !== 'archived'"
                  class="session-btn session-btn-primary"
                  @click.stop="$emit('restore-session', session.session_id)"
                >
                  🔄 恢复
                </button>
                <button
                  v-if="session.state !== 'archived'"
                  class="session-btn session-btn-secondary"
                  @click.stop="$emit('archive-session', session.session_id)"
                >
                  📦 归档
                </button>
                <button
                  class="session-btn session-btn-secondary"
                  @click.stop="$emit('export-session', session.session_id)"
                >
                  📥 导出
                </button>
                <button
                  class="session-btn session-btn-danger"
                  @click.stop="$emit('delete-session', session.session_id)"
                >
                  🗑️ 删除
                </button>
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
  },
  sessionHistoryFilter: {
    type: String,
    default: 'all'
  },
  selectedSessionIds: {
    type: Array,
    default: () => []
  }
})

// Methods
const getFilterLabel = (filter) => {
  const labels = {
    all: '全部',
    active: '活跃',
    completed: '完成',
    failed: '失败',
    archived: '归档'
  }
  return labels[filter] || filter
}

const getFilterIcon = (filter) => {
  const icons = {
    all: '📋',
    active: '🟢',
    completed: '✅',
    failed: '❌',
    archived: '📦'
  }
  return icons[filter] || '📄'
}

const getFilterCount = (filter) => {
  if (filter === 'all') return props.sessions.length
  return props.sessions.filter(s => s.state === filter).length
}

const getStateIcon = (state) => {
  const icons = {
    active: '🟢',
    completed: '✅',
    failed: '❌',
    archived: '📦'
  }
  return icons[state] || '⚪'
}

const getStateClass = (state) => {
  return `session-state-${state}`
}

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
  'set-filter',
  'batch-delete',
  'clear-selection',
  'toggle-expand',
  'toggle-selection',
  'restore-session',
  'archive-session',
  'export-session',
  'delete-session'
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

.session-filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.session-filter-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #dee2e6;
  background: white;
  border-radius: 20px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.session-filter-btn:hover {
  border-color: #1976d2;
  background: #e3f2fd;
}

.session-filter-btn.active {
  border-color: #1976d2;
  background: #1976d2;
  color: white;
}

.filter-icon {
  font-size: 14px;
}

.filter-label {
  font-weight: 500;
}

.filter-count {
  padding: 2px 6px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.session-filter-btn.active .filter-count {
  background: rgba(255, 255, 255, 0.2);
}

.session-batch-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 15px;
  background: #fff3cd;
  border: 1px solid #ffc107;
  border-radius: 6px;
}

.batch-selected-count {
  font-size: 13px;
  color: #856404;
  font-weight: 500;
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
  overflow: hidden;
  transition: all 0.2s;
}

.session-item:hover {
  border-color: #1976d2;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.15);
}

.session-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px;
  cursor: pointer;
  user-select: none;
}

.session-header:hover {
  background: #f8f9fa;
}

.session-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.session-checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
  flex-shrink: 0;
}

.session-state-icon {
  font-size: 18px;
  flex-shrink: 0;
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

.session-id {
  font-family: monospace;
}

.session-header-right {
  flex-shrink: 0;
}

.session-expand-icon {
  font-size: 12px;
  color: #6c757d;
}

.session-details {
  padding: 15px;
  border-top: 1px solid #dee2e6;
  background: #f8f9fa;
}

.session-detail-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
}

.session-detail-label {
  color: #6c757d;
  font-weight: 500;
}

.session-detail-value {
  color: #495057;
}

.session-stats {
  display: flex;
  gap: 10px;
  margin: 15px 0;
}

.session-stat-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px;
  background: white;
  border-radius: 6px;
  border: 1px solid #dee2e6;
}

.session-stat-label-small {
  font-size: 11px;
  color: #6c757d;
  margin-bottom: 4px;
}

.session-stat-value-small {
  font-size: 16px;
  font-weight: 600;
  color: #1976d2;
}

.session-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.session-btn {
  padding: 4px 10px;
  border: 1px solid #dee2e6;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.session-btn:hover {
  background: #f8f9fa;
}

.session-btn-primary {
  background: #1976d2;
  color: white;
  border-color: #1976d2;
}

.session-btn-primary:hover {
  background: #1565c0;
}

.session-btn-secondary {
  color: #1976d2;
  border-color: #1976d2;
}

.session-btn-secondary:hover {
  background: #e3f2fd;
}

.session-btn-danger {
  color: #dc3545;
  border-color: #dc3545;
}

.session-btn-danger:hover {
  background: #f8d7da;
}

.session-state-active {
  border-left: 4px solid #28a745;
}

.session-state-completed {
  border-left: 4px solid #007bff;
}

.session-state-failed {
  border-left: 4px solid #dc3545;
}

.session-state-archived {
  border-left: 4px solid #6c757d;
  opacity: 0.7;
}
</style>