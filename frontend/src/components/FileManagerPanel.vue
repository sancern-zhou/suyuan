<template>
  <div class="management-panel file-management-panel">
    <div class="panel-header">
      <h3>文件管理</h3>
      <button class="panel-btn close-btn" @click="$emit('close')">关闭</button>
    </div>

    <div class="file-manager-content">
    <!-- 面包屑导航 -->
    <div class="breadcrumb-bar">
      <div class="breadcrumb-path">
        <span class="root-label">/tmp</span>
        <template v-if="currentPath">
          <span v-for="(segment, index) in pathSegments" :key="index" class="breadcrumb-segment">
            <span class="separator">/</span>
            <span
              :class="['segment', { clickable: index < pathSegments.length - 1 }]"
              @click="navigateToSegment(index)"
            >
              {{ segment }}
            </span>
          </span>
        </template>
      </div>
      <button
        class="refresh-btn"
        @click="() => loadDirectory()"
        :disabled="loading"
        title="刷新"
      >
        {{ loading ? '加载中...' : '刷新' }}
      </button>
    </div>

    <!-- 文件列表 -->
    <div class="file-list-container">
      <div v-if="loading && !items.length" class="loading-state">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <div v-else-if="error" class="error-state">
        <p>{{ error }}</p>
        <button @click="loadDirectory" class="retry-btn">重试</button>
      </div>

      <div v-else-if="!items.length" class="empty-state">
        <p>此目录为空</p>
      </div>

      <div v-else class="file-list">
        <!-- 父目录链接 -->
        <div
          v-if="currentPath"
          class="file-item directory"
          @click="navigateToParent"
        >
          <div class="file-icon">..</div>
          <div class="file-info">
            <div class="file-name">返回上级</div>
          </div>
        </div>

        <!-- 目录和文件列表 -->
        <div
          v-for="item in items"
          :key="item.path"
          :class="['file-item', { directory: item.is_dir }]"
          @click="handleItemClick(item)"
        >
          <div class="file-icon">
            <svg v-if="item.is_dir" width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M3 7V17C3 18.1 3.9 19 5 19H19C20.1 19 21 18.1 21 17V9C21 7.9 20.1 7 19 7H12L10 5H5C3.9 5 3 5.9 3 7Z" fill="#FFC107"/>
              <path d="M3 7V17C3 18.1 3.9 19 5 19H19C20.1 19 21 18.1 21 17V9C21 7.9 20.1 7 19 7H12L10 5H5C3.9 5 3 5.9 3 7Z" stroke="currentColor" stroke-width="2"/>
            </svg>
            <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" fill="#90CAF9"/>
              <path d="M14 2V8H20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="file-info">
            <div class="file-name">{{ item.name }}</div>
            <div class="file-meta">
              <span v-if="item.is_dir" class="dir-indicator">目录</span>
              <span v-else class="file-size">{{ item.size_formatted }}</span>
              <span class="file-time">{{ item.modified_time_formatted }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const API_BASE = '/api/file-manager'

// 状态
const currentPath = ref('')
const parentPath = ref(null)
const items = ref([])
const loading = ref(false)
const error = ref('')

// 计算属性
const pathSegments = computed(() => {
  if (!currentPath.value) return []
  return currentPath.value.split('/').filter(s => s)
})

// 方法
const loadDirectory = async (path = null) => {
  loading.value = true
  error.value = ''

  try {
    const targetPath = path !== null ? path : currentPath.value
    const url = new URL(`${API_BASE}/list`, window.location.origin)
    if (targetPath) {
      url.searchParams.set('path', targetPath)
    }

    const response = await fetch(url)
    const data = await response.json()

    if (data.success) {
      currentPath.value = data.current_path
      parentPath.value = data.parent_path
      // 过滤隐藏文件（以 . 开头的文件/目录）
      items.value = data.items.filter(item => !item.name.startsWith('.'))
    } else {
      error.value = data.message || '加载目录失败'
    }
  } catch (e) {
    console.error('加载目录失败:', e)
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

const navigateToParent = () => {
  if (parentPath.value !== null) {
    loadDirectory(parentPath.value)
  }
}

const navigateToSegment = (index) => {
  const segments = pathSegments.value.slice(0, index + 1)
  const path = segments.join('/')
  loadDirectory(path)
}

const handleItemClick = (item) => {
  if (item.is_dir) {
    loadDirectory(item.path)
  } else {
    downloadFile(item.path)
  }
}

const downloadFile = (path) => {
  const url = new URL(`${API_BASE}/download`, window.location.origin)
  url.searchParams.set('path', path)
  window.open(url.toString(), '_blank')
}

// 生命周期
onMounted(() => {
  console.log('[FileManagerPanel] Component mounted, loading directory...')
  loadDirectory()
})
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow: hidden;
  background: white;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
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

.panel-btn:hover {
  background: #1976d2;
  color: white;
}

.file-manager-content {
  display: flex;
  flex-direction: column;
  height: calc(100% - 57px);
  overflow: hidden;
}

/* 面包屑导航 */
.breadcrumb-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
  background: #fafafa;
}

.breadcrumb-path {
  flex: 1;
  font-size: 14px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.root-label {
  color: #1890ff;
  font-weight: 500;
}

.breadcrumb-segment {
  display: inline-block;
}

.separator {
  color: #999;
  margin: 0 4px;
}

.segment {
  color: #666;
}

.segment.clickable {
  color: #1890ff;
  cursor: pointer;
  text-decoration: underline;
}

.segment.clickable:hover {
  color: #40a9ff;
}

.refresh-btn {
  padding: 6px 12px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.3s;
}

.refresh-btn:hover:not(:disabled) {
  border-color: #1890ff;
  color: #1890ff;
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 文件列表容器 */
.file-list-container {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

/* 加载状态 */
.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #999;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #f0f0f0;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.retry-btn {
  margin-top: 16px;
  padding: 8px 16px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  color: #1890ff;
}

.retry-btn:hover {
  border-color: #1890ff;
}

/* 文件列表 */
.file-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-item {
  display: flex;
  align-items: center;
  padding: 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.file-item:hover {
  background: #f0f0f0;
  border-color: #e8e8e8;
}

.file-item.directory {
  background: #fffbf0;
}

.file-item.directory:hover {
  background: #fff7e6;
}

.file-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
  color: #666;
}

.file-icon svg {
  width: 100%;
  height: 100%;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-size: 14px;
  color: #333;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
  color: #999;
}

.dir-indicator {
  color: #fa8c16;
  font-weight: 500;
}

.file-size {
  color: #52c41a;
}

/* 滚动条样式 */
.file-list-container::-webkit-scrollbar {
  width: 8px;
}

.file-list-container::-webkit-scrollbar-track {
  background: #f0f0f0;
}

.file-list-container::-webkit-scrollbar-thumb {
  background: #bfbfbf;
  border-radius: 4px;
}

.file-list-container::-webkit-scrollbar-thumb:hover {
  background: #999;
}
</style>
