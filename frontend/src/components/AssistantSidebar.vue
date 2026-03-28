<template>
  <aside class="assistant-sidebar" :class="{ collapsed: isCollapsed }">
    <div class="sidebar-header">
      <template v-if="!isCollapsed">
        <div class="header-title-wrapper">
          <img src="/wechat-screenshot.png" alt="企业微信截图" class="header-image">
          <h2>风清气智</h2>
        </div>
      </template>
      <button class="collapse-btn" type="button" @click="toggleCollapse" :title="isCollapsed ? '展开' : '收起'">
        <span class="collapse-icon" :class="{ collapsed: isCollapsed }"></span>
      </button>
    </div>

    <!-- 新对话按钮固定在header下方 -->
    <div class="new-session-section">
      <button
        class="module-card new-session-btn"
        type="button"
        @click="handleModuleSelect('restart-session')"
      >
        <template v-if="isCollapsed">
          <span class="module-abbr">新对话</span>
        </template>
        <template v-else>
          <div class="module-info">
            <p class="module-title">新对话</p>
          </div>
        </template>
      </button>
    </div>

    <div class="module-list">
      <button
        v-for="module in filteredModules"
        :key="module.id"
        class="module-card"
        :class="{ active: isActive(module.id) }"
        type="button"
        @click="handleModuleSelect(module.id)"
        :title="isCollapsed ? module.name : ''"
      >
        <template v-if="isCollapsed">
          <span class="module-abbr">{{ module.abbr }}</span>
        </template>
        <template v-else>
          <div class="module-info">
            <p class="module-title">{{ module.name }}</p>
          </div>
        </template>
      </button>
    </div>

    <!-- 最近对话列表 -->
    <div v-if="!isCollapsed && recentSessions.length > 0" class="recent-sessions-section">
      <div class="recent-sessions-header">
        <span class="recent-sessions-title">最近对话</span>
        <button class="refresh-icon" @click="refreshRecentSessions" title="刷新">
          {{ refreshingSessions ? '⏳' : '🔄' }}
        </button>
      </div>
      <div class="recent-sessions-list">
        <div
          v-for="session in recentSessions"
          :key="session.session_id"
          class="recent-session-item"
          @click="loadSession(session)"
        >
          <span class="session-state">{{ getSessionStateIcon(session.state) }}</span>
          <span class="session-query">{{ truncateQuery(session.query, 30) }}</span>
          <span class="session-time">{{ formatTime(session.updated_at) }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const props = defineProps({
  activeModule: {
    type: String,
    default: 'general-agent'
  },
  collapsed: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:activeModule', 'select', 'action', 'loadSession', 'update:collapsed'])

// 内部折叠状态，优先使用外部传入的props
const isCollapsed = ref(props.collapsed)
const toggleCollapse = () => {
  const newValue = !isCollapsed.value
  isCollapsed.value = newValue
  emit('update:collapsed', newValue)
}

// 监听外部props变化
watch(() => props.collapsed, (newValue) => {
  isCollapsed.value = newValue
})

const recentSessions = ref([])
const refreshingSessions = ref(false)

const modules = [
  {
    id: 'restart-session',
    name: '新对话',
    abbr: '新对话',
    desc: '清空对话，开始新分析',
    badge: '操作',
    isAction: true
  },
  {
    id: 'knowledge-base',
    name: '知识库管理',
    abbr: '知识库',
    desc: '管理文档与知识检索',
    badge: '管理',
    isAction: true
  },
  {
    id: 'tools-management',
    name: '工具/技能管理',
    abbr: '工具',
    desc: '查看和管理分析工具',
    badge: '管理',
    isAction: true
  },
  {
    id: 'fetchers',
    name: '数据抓取管理',
    abbr: '数据',
    desc: '管理数据源和Fetchers',
    badge: '管理',
    isAction: true
  },
  {
    id: 'scheduled-tasks',
    name: '定时任务',
    abbr: '任务',
    desc: '创建和管理定时任务',
    badge: '工具',
    isAction: true
  },
  {
    id: 'session-history',
    name: '会话历史',
    abbr: '历史',
    desc: '查看和管理历史会话',
    badge: '记录',
    isAction: true
  },
  {
    id: 'social-platform',
    name: '社交管理',
    abbr: '社交',
    desc: '管理QQ、微信等社交机器人',
    badge: '管理',
    isAction: true
  }
]

const handleModuleSelect = (moduleId) => {
  const module = modules.find(m => m.id === moduleId)

  // 所有管理功能：触发事件（包括工具管理、知识库管理、社交账号管理等）
  emit('action', moduleId)
}

const isActive = (moduleId) => props.activeModule === moduleId

// 获取最近会话
const refreshRecentSessions = async () => {
  refreshingSessions.value = true
  try {
    const response = await fetch('/api/sessions?limit=10')
    if (!response.ok) throw new Error('Failed to fetch sessions')
    const data = await response.json()
    // 按更新时间排序，取最近10条
    const sessions = (data.sessions || []).sort((a, b) => {
      return new Date(b.updated_at) - new Date(a.updated_at)
    })
    recentSessions.value = sessions.slice(0, 10)
  } catch (error) {
    console.error('Failed to fetch recent sessions:', error)
  } finally {
    refreshingSessions.value = false
  }
}

// 加载会话
const loadSession = (session) => {
  emit('loadSession', session.session_id)
}

// 过滤后的模块列表（排除"新对话"）
const filteredModules = computed(() => {
  return modules.filter(m => m.id !== 'restart-session')
})

// 获取状态图标
const getSessionStateIcon = (state) => {
  const icons = {
    'active': '🔵',
    'paused': '⏸️',
    'completed': '✅',
    'failed': '❌',
    'archived': '📦'
  }
  return icons[state] || '⚪'
}

// 截断查询文本
const truncateQuery = (query, maxLength = 30) => {
  if (!query) return ''
  if (query.length <= maxLength) return query
  return query.substring(0, maxLength) + '...'
}

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  const days = Math.floor(diff / 86400000)
  if (days < 7) return `${days}天前`

  return date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 组件挂载时加载最近会话
onMounted(() => {
  refreshRecentSessions()
})
</script>

<style lang="scss" scoped>
.assistant-sidebar {
  width: 280px;
  background: #fafbff;
  display: flex;
  flex-direction: column;
  padding: 20px 16px;
  overflow-y: auto;
  transition: width 0.2s ease;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;

  &.collapsed {
    width: 60px;
    padding: 20px 8px;
  }
}

.sidebar-header {
  position: sticky;
  top: 0;
  z-index: 10;
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  background: #fafbff;
  padding-top: 4px;
  padding-bottom: 8px;

  .header-title-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
  }

  h2 {
    margin: 0;
    font-size: 18px;
    color: #1f2a44;
    font-weight: 600;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
  }

  p {
    margin: 6px 0 0;
    font-size: 13px;
    color: #7a86a0;
    width: 100%;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
  }

  .header-image {
    width: 60px;
    height: 60px;
    border-radius: 8px;
    object-fit: contain;
    flex-shrink: 0;
  }

  .collapsed & {
    justify-content: center;
    margin-bottom: 12px;
  }
}

.new-session-section {
  position: sticky;
  top: 84px;
  z-index: 9;
  background: #fafbff;
  padding-bottom: 8px;
  margin-bottom: 8px;

  .collapsed & {
    position: static;
    margin-bottom: 12px;
    padding-bottom: 0;
  }
}

.collapse-btn {
  background: transparent;
  border: none;
  padding: 4px;
  cursor: pointer;
  margin-left: auto;

  .collapsed & {
    margin: 0;
  }
}

.collapse-icon {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-left: 2px solid #9aa6c1;
  border-bottom: 2px solid #9aa6c1;
  transform: rotate(45deg);
  transition: transform 0.2s;

  &.collapsed {
    transform: rotate(-135deg);
  }
}

.module-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.module-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: none;
  border-radius: 12px;
  background: transparent;
  padding: 12px;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;

  &:hover {
    background: rgba(0, 0, 0, 0.04);
  }

  &.active {
    background: #e3f2fd;
  }

  &.disabled {
    opacity: 0.9;
  }

  .collapsed & {
    justify-content: center;
    padding: 10px;
  }
}

.module-abbr {
  font-size: 16px;
  font-weight: 400;
  color: #1976d2;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
}

.module-info {
  flex: 1;
}

.module-title {
  margin: 0;
  font-size: 15px;
  color: #1f2a44;
  font-weight: 400;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
}

.module-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: #7a86a0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
}

.new-session-btn {
  /* 继承默认的 .module-card 样式 */

  .module-title {
    color: #1f2a44;
  }
}

/* 最近对话列表样式 */
.recent-sessions-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e8e8e8;
}

.recent-sessions-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.recent-sessions-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
}

.refresh-icon {
  background: none;
  border: none;
  font-size: 14px;
  cursor: pointer;
  padding: 4px;
  opacity: 0.6;
  transition: opacity 0.2s;

  &:hover {
    opacity: 1;
  }
}

.recent-sessions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;

  &:hover {
    background: rgba(0, 0, 0, 0.04);
  }
}

.session-state {
  font-size: 14px;
  flex-shrink: 0;
}

.session-query {
  flex: 1;
  font-size: 12px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
}

.session-time {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
}

.status-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  flex-shrink: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;

  &.status-ready {
    border-color: #b3d5ff;
    color: #1976d2;
    background: #e9f3ff;
  }

  &.status-pending {
    border-color: #ffd6a5;
    color: #d9822b;
    background: #fff6ea;
  }
}
</style>
