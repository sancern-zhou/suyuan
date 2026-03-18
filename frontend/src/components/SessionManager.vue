<template>
  <div class="session-manager">
    <!-- 管理器头部 -->
    <div class="manager-header">
      <div class="header-title">
        <span class="title-icon">📚</span>
        <h2>会话管理</h2>
      </div>
      <button class="close-button" @click="$emit('close')">
        <span>&times;</span>
      </button>
    </div>

    <!-- 过滤和操作栏 -->
    <div class="filter-bar">
      <div class="filter-tabs">
        <button
          v-for="filter in filters"
          :key="filter.value"
          class="filter-tab"
          :class="{ active: activeFilter === filter.value }"
          @click="activeFilter = filter.value"
        >
          <span class="tab-icon">{{ filter.icon }}</span>
          <span class="tab-label">{{ filter.label }}</span>
          <span v-if="getFilterCount(filter.value) > 0" class="tab-count">
            {{ getFilterCount(filter.value) }}
          </span>
        </button>
      </div>

      <div class="actions">
        <button class="action-button" @click="refreshSessions">
          <span class="action-icon">🔄</span>
          刷新
        </button>
        <button class="action-button" @click="cleanupExpiredSessions">
          <span class="action-icon">🧹</span>
          清理过期
        </button>
      </div>
    </div>

    <!-- 会话统计 -->
    <div v-if="stats" class="stats-panel">
      <div class="stat-card">
        <span class="stat-icon">📊</span>
        <div class="stat-info">
          <span class="stat-value">{{ stats.total }}</span>
          <span class="stat-label">总会话数</span>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-icon">💾</span>
        <div class="stat-info">
          <span class="stat-value">{{ stats.total_data_count }}</span>
          <span class="stat-label">数据项</span>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-icon">📈</span>
        <div class="stat-info">
          <span class="stat-value">{{ stats.total_visual_count }}</span>
          <span class="stat-label">可视化</span>
        </div>
      </div>
    </div>

    <!-- 会话列表 -->
    <div class="sessions-list">
      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <span class="spinner">⏳</span>
        <p>加载会话列表...</p>
      </div>

      <!-- 空状态 -->
      <div v-else-if="filteredSessions.length === 0" class="empty-state">
        <span class="empty-icon">📭</span>
        <p>{{ emptyMessage }}</p>
      </div>

      <!-- 会话项列表 -->
      <div v-else class="sessions-container">
        <SessionItem
          v-for="session in filteredSessions"
          :key="session.session_id"
          :session="session"
          @restore="handleRestore"
          @archive="handleArchive"
          @export="handleExport"
          @delete="handleDelete"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import SessionItem from './SessionItem.vue'
import {
  listSessions,
  getSessionStats,
  restoreSession,
  archiveSession,
  exportSession,
  deleteSession,
  cleanupSessions
} from '@/api/session'

const emit = defineEmits(['close', 'restore'])

// 状态
const sessions = ref([])
const stats = ref(null)
const loading = ref(false)
const activeFilter = ref('all')

// 过滤器选项
const filters = [
  { value: 'all', label: '全部', icon: '📚' },
  { value: 'active', label: '活跃', icon: '🔵' },
  { value: 'completed', label: '已完成', icon: '✅' },
  { value: 'failed', label: '失败', icon: '❌' },
  { value: 'archived', label: '已归档', icon: '📦' }
]

// 计算属性
const filteredSessions = computed(() => {
  if (activeFilter.value === 'all') {
    return sessions.value
  }
  return sessions.value.filter(s => s.state === activeFilter.value)
})

const emptyMessage = computed(() => {
  if (activeFilter.value === 'all') {
    return '暂无会话记录'
  }
  return `暂无${filters.find(f => f.value === activeFilter.value)?.label}会话`
})

// 方法
const getFilterCount = (filterValue) => {
  if (!stats.value) return 0
  if (filterValue === 'all') {
    return stats.value.total
  }
  return stats.value.by_state?.[filterValue] || 0
}

const fetchSessions = async () => {
  loading.value = true
  try {
    const response = await listSessions()
    sessions.value = response.sessions
  } catch (error) {
    console.error('Failed to fetch sessions:', error)
  } finally {
    loading.value = false
  }
}

const fetchStats = async () => {
  try {
    const data = await getSessionStats()
    stats.value = data
  } catch (error) {
    console.error('Failed to fetch stats:', error)
  }
}

const refreshSessions = async () => {
  await Promise.all([fetchSessions(), fetchStats()])
}

const handleRestore = async (sessionId) => {
  try {
    const response = await restoreSession(sessionId)
    console.log('会话恢复成功:', response)

    // 通知父组件恢复会话
    emit('restore', sessionId)

    // 可选：显示成功提示
    alert(`会话 ${sessionId.substring(0, 12)}... 已恢复`)
  } catch (error) {
    console.error('Failed to restore session:', error)
    alert('会话恢复失败: ' + error.message)
  }
}

const handleArchive = async (sessionId) => {
  try {
    await archiveSession(sessionId)
    console.log('会话已归档:', sessionId)

    // 刷新列表
    await refreshSessions()

    alert(`会话 ${sessionId.substring(0, 12)}... 已归档`)
  } catch (error) {
    console.error('Failed to archive session:', error)
    alert('归档失败: ' + error.message)
  }
}

const handleExport = async (sessionId) => {
  try {
    await exportSession(sessionId)
    console.log('会话已导出:', sessionId)

    alert(`会话 ${sessionId.substring(0, 12)}... 已导出到服务器`)
  } catch (error) {
    console.error('Failed to export session:', error)
    alert('导出失败: ' + error.message)
  }
}

const handleDelete = async (sessionId) => {
  try {
    await deleteSession(sessionId)
    console.log('会话已删除:', sessionId)

    // 从列表中移除
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)

    // 刷新统计
    await fetchStats()
  } catch (error) {
    console.error('Failed to delete session:', error)
    alert('删除失败: ' + error.message)
  }
}

const cleanupExpiredSessions = async () => {
  if (!confirm('确定要清理所有过期会话吗？此操作将删除超过保留期限的已完成/失败会话。')) {
    return
  }

  try {
    const response = await cleanupSessions()
    const deletedCount = response.deleted_count

    alert(`已清理 ${deletedCount} 个过期会话`)

    // 刷新列表
    await refreshSessions()
  } catch (error) {
    console.error('Failed to cleanup sessions:', error)
    alert('清理失败: ' + error.message)
  }
}

// 生命周期
onMounted(() => {
  refreshSessions()
})
</script>

<style scoped>
.session-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

/* 管理器头部 */
.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-icon {
  font-size: 24px;
}

.header-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.close-button {
  width: 32px;
  height: 32px;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border-radius: 6px;
  font-size: 24px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-button:hover {
  background: rgba(255, 255, 255, 0.3);
}

/* 过滤栏 */
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
}

.filter-tabs {
  display: flex;
  gap: 8px;
  flex: 1;
  overflow-x: auto;
}

.filter-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: none;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}

.filter-tab:hover {
  background: #f0f0f0;
}

.filter-tab.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-weight: 500;
}

.tab-icon {
  font-size: 14px;
}

.tab-count {
  background: rgba(255, 255, 255, 0.3);
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.filter-tab.active .tab-count {
  background: rgba(255, 255, 255, 0.3);
}

.actions {
  display: flex;
  gap: 8px;
}

.action-button {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid #e0e0e0;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
  color: #666;
}

.action-button:hover {
  background: #f5f5f5;
  border-color: #d0d0d0;
}

.action-icon {
  font-size: 14px;
}

/* 统计面板 */
.stats-panel {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
}

.stat-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.stat-icon {
  font-size: 28px;
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #333;
  line-height: 1;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: #888;
}

/* 会话列表 */
.sessions-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #999;
}

.spinner {
  font-size: 32px;
  display: block;
  margin-bottom: 12px;
  animation: spin 2s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.empty-icon {
  font-size: 64px;
  display: block;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state p {
  font-size: 14px;
  margin: 0;
}

.sessions-container {
  /* SessionItem样式在SessionItem.vue中定义 */
}

/* 滚动条样式 */
.sessions-list::-webkit-scrollbar,
.filter-tabs::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.sessions-list::-webkit-scrollbar-track,
.filter-tabs::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.sessions-list::-webkit-scrollbar-thumb,
.filter-tabs::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 3px;
}

.sessions-list::-webkit-scrollbar-thumb:hover,
.filter-tabs::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
