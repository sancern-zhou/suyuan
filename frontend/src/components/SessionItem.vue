<template>
  <div class="session-item" :class="stateClass">
    <div class="session-header" @click="toggleExpand">
      <div class="header-left">
        <span class="state-icon">{{ stateIcon }}</span>
        <div class="session-info">
          <div class="session-query">{{ truncatedQuery }}</div>
          <div class="session-meta">
            <span class="session-id">{{ shortSessionId }}</span>
            <span class="session-time">{{ formatTime(session.updated_at) }}</span>
          </div>
        </div>
      </div>
      <div class="header-right">
        <span class="expand-icon">{{ isExpanded ? '▲' : '▼' }}</span>
      </div>
    </div>

    <!-- 展开的详情 -->
    <div v-if="isExpanded" class="session-details">
      <!-- 时间信息 -->
      <div class="detail-row">
        <span class="detail-label">创建时间:</span>
        <span class="detail-value">{{ formatFullTime(session.created_at) }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">更新时间:</span>
        <span class="detail-value">{{ formatFullTime(session.updated_at) }}</span>
      </div>
      <div v-if="session.has_error" class="detail-row error">
        <span class="detail-label">错误:</span>
        <span class="detail-value">会话执行失败</span>
      </div>

      <!-- 统计信息 -->
      <div class="stats-row">
        <div class="stat-box">
          <span class="stat-label">数据</span>
          <span class="stat-value">{{ session.data_count }}</span>
        </div>
        <div class="stat-box">
          <span class="stat-label">图表</span>
          <span class="stat-value">{{ session.visual_count }}</span>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="action-buttons">
        <button
          v-if="session.state !== 'archived'"
          class="btn-primary"
          @click.stop="$emit('restore', session.session_id)"
        >
          <span class="btn-icon">🔄</span>
          恢复会话
        </button>
        <button
          v-if="session.state !== 'archived'"
          class="btn-secondary"
          @click.stop="$emit('archive', session.session_id)"
        >
          <span class="btn-icon">📦</span>
          归档
        </button>
        <button
          class="btn-secondary"
          @click.stop="$emit('export', session.session_id)"
        >
          <span class="btn-icon">📥</span>
          导出
        </button>
        <button
          class="btn-danger"
          @click.stop="handleDelete"
        >
          <span class="btn-icon">🗑️</span>
          删除
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  session: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['restore', 'archive', 'export', 'delete'])

const isExpanded = ref(false)

// 计算属性
const stateClass = computed(() => {
  return `state-${props.session.state}`
})

const stateIcon = computed(() => {
  const icons = {
    active: '🔵',
    paused: '⏸️',
    completed: '✅',
    failed: '❌',
    archived: '📦'
  }
  return icons[props.session.state] || '⚪'
})

const truncatedQuery = computed(() => {
  const maxLength = 80
  if (props.session.query.length <= maxLength) {
    return props.session.query
  }
  return props.session.query.substring(0, maxLength) + '...'
})

const shortSessionId = computed(() => {
  return props.session.session_id.substring(0, 12)
})

// 方法
const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const formatTime = (timestamp) => {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date

  // 小于1分钟
  if (diff < 60000) {
    return '刚刚'
  }
  // 小于1小时
  if (diff < 3600000) {
    const minutes = Math.floor(diff / 60000)
    return `${minutes}分钟前`
  }
  // 小于1天
  if (diff < 86400000) {
    const hours = Math.floor(diff / 3600000)
    return `${hours}小时前`
  }
  // 大于1天
  const days = Math.floor(diff / 86400000)
  if (days < 7) {
    return `${days}天前`
  }

  // 超过7天显示日期
  return date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const formatFullTime = (timestamp) => {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const handleDelete = () => {
  if (confirm(`确定要删除会话 ${shortSessionId.value}... 吗？此操作不可恢复。`)) {
    emit('delete', props.session.session_id)
  }
}
</script>

<style scoped>
.session-item {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.session-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 状态相关样式 */
.state-active {
  border-left: 4px solid #2196f3;
}

.state-paused {
  border-left: 4px solid #ff9800;
}

.state-completed {
  border-left: 4px solid #4caf50;
}

.state-failed {
  border-left: 4px solid #f44336;
}

.state-archived {
  border-left: 4px solid #9e9e9e;
  opacity: 0.8;
}

/* 会话头部 */
.session-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}

.session-header:hover {
  background: #f8f9fa;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.state-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-query {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #666;
}

.session-id {
  font-family: monospace;
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
}

.session-time {
  color: #888;
}

.header-right {
  flex-shrink: 0;
}

.expand-icon {
  font-size: 12px;
  color: #888;
}

/* 会话详情 */
.session-details {
  padding: 16px;
  background: #f8f9fa;
  border-top: 1px solid #e0e0e0;
}

.detail-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
}

.detail-row.error {
  color: #f44336;
}

.detail-label {
  font-weight: 500;
  color: #666;
  width: 80px;
  flex-shrink: 0;
}

.detail-value {
  color: #333;
}

/* 统计信息 */
.stats-row {
  display: flex;
  gap: 12px;
  margin: 12px 0;
}

.stat-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e0e0e0;
}

.stat-label {
  font-size: 11px;
  color: #888;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.action-buttons button {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-icon {
  font-size: 14px;
}

.btn-primary {
  background: #2196f3;
  color: white;
}

.btn-primary:hover {
  background: #1976d2;
}

.btn-secondary {
  background: #fff;
  color: #666;
  border: 1px solid #e0e0e0;
}

.btn-secondary:hover {
  background: #f5f5f5;
  border-color: #d0d0d0;
}

.btn-danger {
  background: #fff;
  color: #f44336;
  border: 1px solid #ffcdd2;
}

.btn-danger:hover {
  background: #ffebee;
  border-color: #ef9a9a;
}
</style>
