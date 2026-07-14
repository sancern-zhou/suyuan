<template>
  <div class="management-panel session-history-panel">
    <div class="panel-header">
      <h3>会话历史</h3>
      <div class="panel-actions">
        <button v-if="isAdmin" class="panel-btn small" @click="$emit('cleanup-sessions')">清理过期</button>
        <button
          class="panel-btn small danger"
          :disabled="selectedSessionIds.length === 0"
          @click="emitDeleteSelected"
        >
          删除选中{{ selectedSessionIds.length ? ` ${selectedSessionIds.length}` : '' }}
        </button>
      </div>
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
          <div class="session-selection-toolbar">
            <label class="session-select-all">
              <input
                type="checkbox"
                :checked="allSessionsSelected"
                :indeterminate.prop="someSessionsSelected"
                @change="toggleSelectAll"
              >
              <span>选择全部</span>
            </label>
            <button
              v-if="selectedSessionIds.length > 0"
              type="button"
              class="selection-clear-btn"
              @click="clearSelection"
            >
              清空选择
            </button>
          </div>

          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            @click="$emit('restore-session', session.session_id)"
          >
            <label v-if="!rowLabels(session).readOnly" class="session-select-box" @click.stop>
              <input
                v-model="selectedSessionIds"
                type="checkbox"
                :value="session.session_id"
                :aria-label="`选择会话 ${getShortId(session.session_id)}`"
              >
            </label>
            <div class="session-info">
              <div class="session-query">{{ truncateQuery(session.query) }}</div>
              <div class="session-meta">
                <span class="session-id">{{ getShortId(session.session_id) }}</span>
                <span class="session-source-badge">{{ rowLabels(session).source }}</span>
                <span v-if="rowLabels(session).owner" class="session-owner">
                  {{ rowLabels(session).owner }}
                </span>
                <span v-if="rowLabels(session).readOnly" class="session-readonly-badge">只读</span>
                <span v-if="isSessionCase(session)" class="session-case-badge">案例</span>
                <span class="session-status" :class="`status-${getSessionStatus(session).key}`">
                  {{ getSessionStatus(session).label }}
                </span>
                <span class="session-time">{{ formatTime(session.updated_at) }}</span>
              </div>
            </div>
            <div class="session-actions">
              <button
                v-if="!rowLabels(session).readOnly"
                class="session-case-action"
                type="button"
                @click.stop="$emit('toggle-session-case', session)"
              >
                {{ isSessionCase(session) ? '取消案例' : '标记案例' }}
              </button>
              <button
                v-if="!rowLabels(session).readOnly"
                class="session-delete-action"
                type="button"
                @click.stop="emitDeleteSession(session.session_id)"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { historyRowLabels } from './sessionHistoryAccess.js'

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
  isAdmin: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'close',
  'refresh-sessions',
  'cleanup-sessions',
  'restore-session',
  'toggle-session-case',
  'delete-sessions'
])

const selectedSessionIds = ref([])

const sessionIds = computed(() => props.sessions
  .filter(session => !historyRowLabels(session, props.isAdmin).readOnly)
  .map(session => session.session_id)
  .filter(Boolean))
const allSessionsSelected = computed(() => sessionIds.value.length > 0 && selectedSessionIds.value.length === sessionIds.value.length)
const someSessionsSelected = computed(() => selectedSessionIds.value.length > 0 && !allSessionsSelected.value)

watch(sessionIds, (ids) => {
  const visibleIds = new Set(ids)
  selectedSessionIds.value = selectedSessionIds.value.filter(id => visibleIds.has(id))
})

const toggleSelectAll = () => {
  selectedSessionIds.value = allSessionsSelected.value ? [] : [...sessionIds.value]
}

const clearSelection = () => {
  selectedSessionIds.value = []
}

const emitDeleteSelected = () => {
  if (selectedSessionIds.value.length === 0) return
  emit('delete-sessions', [...selectedSessionIds.value])
  clearSelection()
}

const emitDeleteSession = (sessionId) => {
  if (!sessionId) return
  emit('delete-sessions', [sessionId])
  selectedSessionIds.value = selectedSessionIds.value.filter(id => id !== sessionId)
}

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

const getSessionStatus = (session) => {
  if (session?.is_running || session?.status === 'running' || session?.state === 'running') {
    return { key: 'running', label: '进行中' }
  }
  if (session?.has_error || session?.status === 'error' || session?.state === 'error') {
    return { key: 'error', label: '失败' }
  }
  if (session?.status === 'active' || session?.state === 'active') {
    return { key: 'active', label: '已保存' }
  }
  return { key: 'completed', label: '完成' }
}

const isSessionCase = (session) => session?.metadata?.is_case === true
const rowLabels = (session) => historyRowLabels(session, props.isAdmin)

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

</script>

<style scoped>
.management-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
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
  flex-shrink: 0;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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

.session-case-action {
  flex-shrink: 0;
  padding: 5px 10px;
  border: 1px solid #1976d2;
  border-radius: 4px;
  background: white;
  color: #1976d2;
  font-size: 12px;
  cursor: pointer;
}

.session-case-action:hover {
  background: #1976d2;
  color: white;
}

.session-delete-action {
  flex-shrink: 0;
  padding: 5px 10px;
  border: 1px solid #dc3545;
  border-radius: 4px;
  background: white;
  color: #dc3545;
  font-size: 12px;
  cursor: pointer;
}

.session-delete-action:hover {
  background: #dc3545;
  color: white;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.session-case-badge {
  padding: 2px 6px;
  border-radius: 4px;
  background: #fff4db;
  color: #9a6500;
  font-size: 11px;
  font-weight: 600;
}

.session-history-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 15px;
  overflow-y: auto;
  min-height: 0;
}

.session-stats {
  display: flex;
  gap: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
  flex-shrink: 0;
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
  flex-shrink: 0;
  min-height: 0;
}

.session-selection-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 2px;
  margin-bottom: 8px;
}

.session-select-all,
.session-select-box {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #495057;
  font-size: 13px;
  cursor: pointer;
}

.session-select-box {
  flex-shrink: 0;
}

.session-select-all input,
.session-select-box input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.selection-clear-btn {
  border: none;
  background: transparent;
  color: #1976d2;
  font-size: 12px;
  cursor: pointer;
}

.selection-clear-btn:hover {
  text-decoration: underline;
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
  display: flex;
  align-items: center;
  gap: 12px;
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
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #6c757d;
}

.session-status {
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.4;
  border: 1px solid transparent;
}

.session-source-badge,
.session-readonly-badge {
  padding: 2px 6px;
  border-radius: 999px;
  background: #eef3f8;
  color: #31507a;
  white-space: nowrap;
}

.session-readonly-badge {
  background: #fff6df;
  color: #8a5a00;
}

.session-owner {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-running {
  color: #0f7b3b;
  background: #e8f6ee;
  border-color: #b9e3c8;
}

.status-completed {
  color: #31507a;
  background: #eef3f8;
  border-color: #d5e0ec;
}

.status-active {
  color: #8a5a00;
  background: #fff6df;
  border-color: #f1d48a;
}

.status-error {
  color: #b42318;
  background: #fff1f0;
  border-color: #ffccc7;
}
</style>
