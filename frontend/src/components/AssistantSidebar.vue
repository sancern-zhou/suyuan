<template>
  <aside class="assistant-sidebar" :class="{ collapsed: isCollapsed }">
    <div class="sidebar-header">
      <template v-if="!isCollapsed">
        <div class="header-title-wrapper">
          <div class="brand-copy">
            <h2>{{ projectConfig.brandName }}</h2>
          </div>
        </div>
      </template>
      <button class="collapse-btn" type="button" @click="toggleCollapse" :title="isCollapsed ? '展开' : '收起'">
        <span class="collapse-icon" :class="{ collapsed: isCollapsed }"></span>
      </button>
    </div>

    <!-- 核心工作入口固定在 header 下方 -->
    <div class="primary-navigation">
      <div class="new-session-section">
        <button
          class="module-card"
          :class="{ active: isActive('agent-platform') }"
          type="button"
          @click="handleModuleSelect('agent-platform')"
          :title="isCollapsed ? platformEntryLabel : ''"
        >
          <span class="module-icon" v-html="getModuleIcon('agent-platform')"></span>
          <div v-if="!isCollapsed" class="module-info">
            <p class="module-title">{{ platformEntryLabel }}</p>
          </div>
        </button>
        <button
          class="module-card"
          type="button"
          @click="handleModuleSelect('restart-session')"
        >
          <span class="module-icon" v-html="getModuleIcon('restart-session')"></span>
          <div v-if="!isCollapsed" class="module-info">
            <p class="module-title">新建对话</p>
          </div>
        </button>
        <button
          v-if="projectConfig.hasModule('xuchang-air-quality')"
          class="module-card"
          :class="{ active: isActive('air-quality-forecast') }"
          type="button"
          @click="handleModuleSelect('air-quality-forecast')"
          :title="isCollapsed ? '预报预测' : ''"
        >
          <span class="module-icon" v-html="getModuleIcon('air-quality-forecast')"></span>
          <div v-if="!isCollapsed" class="module-info">
            <p class="module-title">预报预测</p>
          </div>
        </button>
        <button
          class="module-card"
          :class="{ active: isActive('query-dashboard') }"
          type="button"
          @click="handleModuleSelect('query-dashboard')"
          :title="isCollapsed ? '智能问数' : ''"
        >
          <span class="module-icon" v-html="getModuleIcon('query-dashboard')"></span>
          <div v-if="!isCollapsed" class="module-info">
            <p class="module-title">智能问数</p>
          </div>
        </button>
        <button
          v-for="task in taskWorkspaceEntries"
          :key="task.task_id"
          class="module-card"
          :class="{ active: activeModule === `task-workspace:${task.task_id}` }"
          type="button"
          @click="$emit('action', { type: 'task-workspace', taskId: task.task_id })"
          :title="isCollapsed ? task.workspace_entry?.title || task.name : ''"
        >
          <span class="module-icon" v-html="getModuleIcon('scheduled-tasks')"></span>
          <div v-if="!isCollapsed" class="module-info">
            <p class="module-title">{{ task.workspace_entry?.title || task.name }}</p>
          </div>
        </button>
        <button
          class="module-card"
          :class="{ active: isActive('knowledge-base') }"
          type="button"
          @click="handleModuleSelect('knowledge-base')"
          :title="isCollapsed ? '知识管理' : ''"
        >
          <span class="module-icon" v-html="getModuleIcon('knowledge-base')"></span>
          <div v-if="!isCollapsed" class="module-info">
            <p class="module-title">知识管理</p>
          </div>
        </button>
      </div>

      <div class="module-list">
        <div
          v-for="group in moduleGroups"
          :key="group.id"
          class="module-group"
        >
          <button
            v-for="module in group.modules"
            :key="module.id"
            class="module-card"
            :class="{ active: isActive(module.id) }"
            type="button"
            @click="handleModuleSelect(module.id)"
            :title="isCollapsed ? module.name : ''"
          >
            <span class="module-icon" v-html="getModuleIcon(module.id)"></span>
            <div v-if="!isCollapsed" class="module-info">
              <p class="module-title">{{ module.name }}</p>
            </div>
          </button>
        </div>
      </div>
    </div>

    <div class="sidebar-scroll-area">
      <!-- 最近对话列表 -->
      <div v-if="!isCollapsed" class="recent-sessions-section">
        <div class="recent-sessions-header">
          <span class="recent-sessions-title">{{ conversationListTitle }}</span>
          <div class="conversation-view-actions">
            <button
              class="conversation-view-icon"
              :class="{ active: conversationListView === CONVERSATION_LIST_VIEW.CASES }"
              type="button"
              @click="toggleConversationView(CONVERSATION_LIST_VIEW.CASES)"
              title="查看案例库"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 4.5h12a1 1 0 0 1 1 1v14l-7-3.5-7 3.5v-14a1 1 0 0 1 1-1Z" />
                <path d="M9 8h6" />
                <path d="M9 11h4" />
              </svg>
            </button>
            <button
              class="conversation-view-icon"
              :class="{ active: conversationListView === CONVERSATION_LIST_VIEW.IM }"
              type="button"
              @click="toggleConversationView(CONVERSATION_LIST_VIEW.IM)"
              title="查看IM对话"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M5 5.5h14v10H9l-4 3v-13Z" />
                <path d="M8.5 9h7" />
                <path d="M8.5 12h4.5" />
              </svg>
            </button>
          </div>
        </div>
        <div class="recent-sessions-list">
          <div v-if="activeSessionList.length === 0" class="recent-session-empty">
            {{ conversationListEmptyText }}
          </div>
          <div
            v-for="session in activeSessionList"
            :key="session.session_id"
            class="recent-session-item"
            :class="{ running: session.is_running }"
            @click="loadSession(session)"
          >
            <span class="session-query">{{ truncateQuery(session.query, 30) }}</span>
            <span class="session-time">{{ session.is_running ? '运行中' : formatTime(session.updated_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div ref="settingsFooterRef" class="user-settings-footer">
      <div
        v-if="settingsMenuOpen"
        id="sidebar-user-settings-menu"
        class="user-settings-menu"
        role="menu"
        aria-label="系统管理"
      >
        <button
          v-for="module in settingsModules"
          :key="module.id"
          class="settings-menu-item"
          :class="{ active: isActive(module.id) }"
          type="button"
          role="menuitem"
          @click="handleSettingsSelect(module.id)"
        >
          <span class="module-icon" v-html="getModuleIcon(module.id)"></span>
          <span>{{ module.name }}</span>
        </button>
      </div>

      <div class="user-identity" :title="userDisplayName">
        <span v-if="isCollapsed" class="user-initial" aria-hidden="true">{{ userInitial }}</span>
        <span v-else class="user-name">{{ userDisplayName }}</span>
      </div>
      <button
        class="settings-toggle"
        type="button"
        aria-label="打开系统设置"
        aria-controls="sidebar-user-settings-menu"
        :aria-expanded="settingsMenuOpen"
        @click.stop="toggleSettingsMenu"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.86 2.86-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21H9.55v-.1A1.7 1.7 0 0 0 8.5 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.86-2.86.06-.06A1.7 1.7 0 0 0 4.1 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H2.3V9.55h.1A1.7 1.7 0 0 0 4.1 8.5a1.7 1.7 0 0 0-.34-1.88l-.06-.06L6.56 3.7l.06.06A1.7 1.7 0 0 0 8.5 4.1a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V2.3h4.05v.1A1.7 1.7 0 0 0 15 4.1a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.86 2.86-.06.06A1.7 1.7 0 0 0 19.4 8.5a1.7 1.7 0 0 0 .6 1 1.7 1.7 0 0 0 1.1.4h.1v4.05h-.1A1.7 1.7 0 0 0 19.4 15Z" />
        </svg>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { authFetch } from '@/auth/http.js'
import { projectConfig } from '@/config/projectConfig.js'
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/auth/authStore.js'
import { useReactStore } from '@/stores/reactStore'
import {
  CONVERSATION_LIST_VIEW,
  filterSidebarConversations,
  toggleConversationListView
} from './conversationListPolicy.js'
import { filterSidebarModules } from './sidebarProjectModules.js'

const router = useRouter()
const auth = useAuthStore()
const store = useReactStore()

const props = defineProps({
  activeModule: {
    type: String,
    default: 'general-agent'
  },
  collapsed: {
    type: Boolean,
    default: false
  },
  taskWorkspaceEntries: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:activeModule', 'select', 'action', 'loadSession', 'update:collapsed'])

// 内部折叠状态，优先使用外部传入的props
const isCollapsed = ref(props.collapsed)
const settingsFooterRef = ref(null)
const settingsMenuOpen = ref(false)
const closeSettingsMenu = () => {
  settingsMenuOpen.value = false
}
const toggleSettingsMenu = () => {
  settingsMenuOpen.value = !settingsMenuOpen.value
}
const toggleCollapse = () => {
  closeSettingsMenu()
  const newValue = !isCollapsed.value
  isCollapsed.value = newValue
  emit('update:collapsed', newValue)
}

// 监听外部props变化
watch(() => props.collapsed, (newValue) => {
  isCollapsed.value = newValue
  closeSettingsMenu()
})

const userDisplayName = computed(() => {
  const name = auth.user?.name || auth.user?.userName || '当前用户'
  return String(name).trim() || '当前用户'
})
const userInitial = computed(() => Array.from(userDisplayName.value)[0] || '用')

const recentSessions = ref([])
const refreshingSessions = ref(false)
const conversationListView = ref(CONVERSATION_LIST_VIEW.RECENT)
const RECENT_SESSIONS_LIMIT = 30
const SESSION_FETCH_LIMIT = 200
let recentSessionsTimer = null

const handleSessionCaseUpdated = () => {
  refreshRecentSessions({ silent: true })
}

const mergedRecentSessions = computed(() => {
  const localSessions = Object.values(store.sessionStates || {})
    .filter(session => session.sessionId)
    .map(session => {
      const firstUser = session.messages?.find(m => m.type === 'user')
      const lastMessage = session.messages?.[session.messages.length - 1]

      // 获取会话标题：优先使用文本内容，其次使用附件名称，最后使用默认标题
      let queryTitle = '新对话'
      if (firstUser?.content && firstUser.content.trim()) {
        queryTitle = firstUser.content.trim()
      } else if (firstUser?.attachments && firstUser.attachments.length > 0) {
        const firstAttachment = firstUser.attachments[0]
        queryTitle = firstAttachment.name || firstAttachment.filename || '附件'
      }

      return {
        session_id: session.sessionId,
        query: queryTitle,
        updated_at: lastMessage?.timestamp || new Date().toISOString(),
        is_running: !!session.isAnalyzing,
        is_local: true,
        ...(session.conversationAccess?.source
          ? { source: session.conversationAccess.source }
          : {})
      }
    })

  const byId = new Map()
  for (const session of recentSessions.value) {
    byId.set(session.session_id, session)
  }
  for (const session of localSessions) {
    byId.set(session.session_id, {
      ...(byId.get(session.session_id) || {}),
      ...session
    })
  }

  return Array.from(byId.values())
    .sort((a, b) => {
      if (a.is_running !== b.is_running) return a.is_running ? -1 : 1
      return new Date(b.updated_at) - new Date(a.updated_at)
    })
})

const displayedRecentSessions = computed(() => {
  return filterSidebarConversations(
    mergedRecentSessions.value,
    CONVERSATION_LIST_VIEW.RECENT
  ).slice(0, RECENT_SESSIONS_LIMIT)
})

const caseLibrarySessions = computed(() => {
  return filterSidebarConversations(
    mergedRecentSessions.value,
    CONVERSATION_LIST_VIEW.CASES
  )
    .sort((a, b) => {
      const aMarked = a.metadata?.case_marked_at || a.updated_at || 0
      const bMarked = b.metadata?.case_marked_at || b.updated_at || 0
      return new Date(bMarked) - new Date(aMarked)
    })
})

const imConversationSessions = computed(() => {
  return filterSidebarConversations(
    mergedRecentSessions.value,
    CONVERSATION_LIST_VIEW.IM
  ).slice(0, RECENT_SESSIONS_LIMIT)
})

const activeSessionList = computed(() => {
  if (conversationListView.value === CONVERSATION_LIST_VIEW.CASES) {
    return caseLibrarySessions.value
  }
  if (conversationListView.value === CONVERSATION_LIST_VIEW.IM) {
    return imConversationSessions.value
  }
  return displayedRecentSessions.value
})

const conversationListTitle = computed(() => ({
  [CONVERSATION_LIST_VIEW.RECENT]: '最近对话',
  [CONVERSATION_LIST_VIEW.CASES]: '案例库',
  [CONVERSATION_LIST_VIEW.IM]: 'IM对话'
})[conversationListView.value])

const conversationListEmptyText = computed(() => ({
  [CONVERSATION_LIST_VIEW.RECENT]: '暂无最近对话',
  [CONVERSATION_LIST_VIEW.CASES]: '暂无案例',
  [CONVERSATION_LIST_VIEW.IM]: '暂无IM对话'
})[conversationListView.value])

const platformEntryLabel = computed(() => (
  projectConfig.agentPlatformLayout === 'coordinator'
    ? `${projectConfig.coordinator?.name || '智能助手'}首页`
    : '智能体平台'
))

const allModules = [
  {
    id: 'agent-platform',
    name: '智能体平台',
    abbr: '平台',
    desc: '选择适合任务的智能体',
    badge: '工作台',
    isAction: true
  },
  {
    id: 'restart-session',
    name: '新建对话',
    abbr: '新建对话',
    desc: '清空对话，开始新分析',
    badge: '操作',
    isAction: true
  },
  {
    id: 'query-dashboard',
    name: '智能问数',
    abbr: '问数',
    desc: '进入AI智能问数对话与数据联动大屏',
    badge: '问数',
    isAction: true,
    requiredModule: 'legacy'
  },
  {
    id: 'air-quality-forecast',
    name: '预报预测',
    abbr: '预报',
    desc: '查看许昌市逐小时空气质量预报与观测',
    badge: '预报',
    isAction: true,
    requiredModule: 'xuchang-air-quality'
  },
  {
    id: 'knowledge-base',
    name: '知识管理',
    abbr: '知识',
    desc: '管理文档与知识检索',
    badge: '管理',
    isAction: true,
    requiredModule: 'legacy'
  },
  {
    id: 'tools-management',
    name: '工具管理',
    abbr: '工具',
    desc: '查看和管理分析工具',
    badge: '管理',
    isAction: true,
    requiredModule: 'legacy'
  },
  {
    id: 'skills-management',
    name: '技能管理',
    abbr: '技能',
    desc: '查看和管理技能文档',
    badge: '管理',
    isAction: true,
    requiredModule: 'legacy'
  },
  {
    id: 'fetchers',
    name: '数据管理',
    abbr: '数据',
    desc: '管理数据源和Fetchers',
    badge: '管理',
    isAction: true,
    requiredModule: 'legacy'
  },
  {
    id: 'scheduled-tasks',
    name: '定时任务',
    abbr: '任务',
    desc: '创建和管理定时任务',
    badge: '工具',
    isAction: true,
    requiredModule: 'legacy'
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
    isAction: true,
    requiredModule: 'legacy'
  },
  {
    id: 'file-manager',
    name: '文件管理',
    abbr: '文件',
    desc: '浏览和下载/tmp目录文件',
    badge: '工具',
    isAction: true,
    requiredModule: 'legacy'
  }
]

const modules = filterSidebarModules(allModules, projectConfig.hasModule)

const SETTINGS_MODULE_IDS = Object.freeze([
  'session-history',
  'skills-management',
  'scheduled-tasks',
  'tools-management',
  'file-manager',
  'fetchers',
  'social-platform'
])

const settingsModules = computed(() => {
  const byId = new Map(modules.map(module => [module.id, module]))
  return SETTINGS_MODULE_IDS.map(id => byId.get(id)).filter(Boolean)
})

const moduleIcons = {
  'agent-platform': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3.5 20 8v8l-8 4.5L4 16V8l8-4.5Z" />
      <path d="m4.5 8 7.5 4.2L19.5 8" />
      <path d="M12 12.2v8" />
      <path d="m8.5 6 7 4" />
    </svg>
  `,
  'restart-session': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </svg>
  `,
  'query-dashboard': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 16v-5" />
      <path d="M12 16V8" />
      <path d="M16 16v-7" />
      <path d="M20 8.5 16 6l-4 2-4-3" />
    </svg>
  `,
  'air-quality-forecast': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M7.5 16v-4" />
      <path d="M11.5 16V8" />
      <path d="M15.5 16v-6" />
      <path d="m7 8 4-3 3 2 5-3" />
    </svg>
  `,
  'session-history': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 5h16" />
      <path d="M4 12h12" />
      <path d="M4 19h8" />
      <path d="M17 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
      <path d="M17 11.5V13l1 1" />
    </svg>
  `,
  'knowledge-base': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 5.5C5 4.67 5.67 4 6.5 4h11c.83 0 1.5.67 1.5 1.5v13c0 .83-.67 1.5-1.5 1.5h-11A1.5 1.5 0 0 1 5 18.5v-13Z" />
      <path d="M8 8h8" />
      <path d="M8 11.5h8" />
      <path d="M8 15h5" />
    </svg>
  `,
  'file-manager': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3.5 6.5h6l2 2h9v9.5a2 2 0 0 1-2 2h-15v-13.5Z" />
      <path d="M3.5 10h17" />
    </svg>
  `,
  'tools-management': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m14.5 6.5 3-3 3 3-3 3-3-3Z" />
      <path d="M4 20l8.8-8.8" />
      <path d="M9 4h4v4H9z" />
      <path d="M4 11h4v4H4z" />
    </svg>
  `,
  'skills-management': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 4 5 7.5l7 3.5 7-3.5L12 4Z" />
      <path d="M5 12l7 3.5L19 12" />
      <path d="M5 16.5 12 20l7-3.5" />
    </svg>
  `,
  fetchers: `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
      <path d="M8 4v16" />
      <path d="M16 4v16" />
    </svg>
  `,
  'scheduled-tasks': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
      <path d="M5 4 3 6" />
      <path d="m19 4 2 2" />
    </svg>
  `,
  'social-platform': `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 9.5a4 4 0 1 1 8 0v3a4 4 0 0 1-8 0v-3Z" />
      <path d="M15 11h1.5a3.5 3.5 0 0 1 0 7H14" />
      <path d="M7 11H5.5a3.5 3.5 0 0 0 0 7H10" />
    </svg>
  `
}

const getModuleIcon = (moduleId) => moduleIcons[moduleId] || moduleIcons['tools-management']

const handleModuleSelect = (moduleId) => {
  const module = modules.find(m => m.id === moduleId)

  // 所有管理功能：触发事件（包括工具管理、知识库管理、社交账号管理等）
  emit('action', moduleId)
}

const handleSettingsSelect = (moduleId) => {
  handleModuleSelect(moduleId)
  closeSettingsMenu()
}

const handleDocumentPointerDown = (event) => {
  if (!settingsMenuOpen.value) return
  if (!settingsFooterRef.value?.contains(event.target)) closeSettingsMenu()
}

const handleDocumentKeydown = (event) => {
  if (event.key === 'Escape') closeSettingsMenu()
}

const isActive = (moduleId) => props.activeModule === moduleId

// 获取最近会话
const refreshRecentSessions = async (options = {}) => {
  const { silent = false } = options
  if (!silent) refreshingSessions.value = true
  try {
    const response = await authFetch(`/api/sessions?limit=${SESSION_FETCH_LIMIT}`)
    if (!response.ok) throw new Error('Failed to fetch sessions')
    const data = await response.json()
    // 按更新时间排序，取最近会话
    const sessions = (data.sessions || []).sort((a, b) => {
      return new Date(b.updated_at) - new Date(a.updated_at)
    })
    recentSessions.value = sessions.slice(0, SESSION_FETCH_LIMIT)
  } catch (error) {
    console.error('Failed to fetch recent sessions:', error)
  } finally {
    if (!silent) refreshingSessions.value = false
  }
}

// 加载会话
const loadSession = (session) => {
  emit('loadSession', session.session_id)
}

const toggleConversationView = (targetView) => {
  conversationListView.value = toggleConversationListView(
    conversationListView.value,
    targetView
  )
}

const moduleGroups = computed(() => [])

// 截断查询文本
const truncateQuery = (query, maxLength = 30) => {
  if (!query) return ''
  if (query.length <= maxLength) return query
  return query.substring(0, maxLength) + '...'
}

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  // 修正时区：数据库存储的是UTC时间，需要+8小时转换为北京时间
  const date = new Date(timestamp)
  const beijingDate = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  const now = new Date()
  const diff = now - beijingDate

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  const days = Math.floor(diff / 86400000)
  if (days < 7) return `${days}天前`

  return beijingDate.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 组件挂载时加载最近会话
onMounted(() => {
  refreshRecentSessions()
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
  window.addEventListener('session-case-updated', handleSessionCaseUpdated)
  recentSessionsTimer = window.setInterval(() => {
    refreshRecentSessions({ silent: true })
  }, 15000)
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
  window.removeEventListener('session-case-updated', handleSessionCaseUpdated)
  if (recentSessionsTimer) {
    window.clearInterval(recentSessionsTimer)
    recentSessionsTimer = null
  }
})
</script>

<style lang="scss" scoped>
.assistant-sidebar {
  width: 272px;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  padding: 0 12px 14px;
  overflow: visible;
  transition: width 0.2s ease, padding 0.2s ease;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
  border-right: 1px solid #edf1f7;

  &.collapsed {
    width: 60px;
    padding: 0 8px 14px;
  }
}

.sidebar-scroll-area {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.sidebar-header {
  position: sticky;
  top: 0;
  z-index: 20;
  margin-bottom: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  background: #f8fafc;
  padding-top: 10px;
  padding-bottom: 10px;

  .header-title-wrapper {
    display: flex;
    align-items: center;
    gap: 9px;
    flex: 1;
    min-width: 0;
  }

  .brand-copy {
    display: block;
    min-width: 0;
  }

  h2 {
    margin: 0;
    font-size: 16px;
    color: #1f2a44;
    font-weight: 600;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
  }

  .header-image {
    width: 34px;
    height: 34px;
    border-radius: 8px;
    flex-shrink: 0;
    object-fit: cover;
  }

  .header-mark {
    display: block;
  }

  .collapsed & {
    justify-content: center;
    margin-bottom: 12px;
  }
}

.primary-navigation {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: 4px;
}

.new-session-section {
  background: #f8fafc;
  padding-bottom: 0;
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;

  .collapsed & {
    padding-bottom: 0;
    margin-bottom: 0;
  }
}

.collapse-btn {
  background: transparent;
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  cursor: pointer;
  margin-left: auto;
  border-radius: 8px;

  &:hover {
    background: #eef4fb;
  }

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
  flex: 0 0 auto;
  flex-direction: column;
  gap: 4px;

  .collapsed & {
    align-items: center;
    gap: 4px;
  }
}

.module-group {
  display: flex;
  flex-direction: column;
  gap: 4px;

  .collapsed & {
    align-items: center;
    gap: 4px;
  }
}

.module-card {
  display: flex;
  align-items: center;
  gap: 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  min-height: 38px;
  padding: 8px 10px;
  color: #526173;
  cursor: pointer;
  text-align: left;
  transition: background 0.16s ease, color 0.16s ease;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;

  &:hover {
    background: #eef4fb;
    color: #1976d2;
  }

  &.active {
    background: #e3f2fd;
    color: #1976d2;
  }

  &.disabled {
    opacity: 0.9;
  }

  .collapsed & {
    justify-content: center;
    width: 44px;
    height: 40px;
    padding: 0;
    gap: 0;
  }
}

.module-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  flex: 0 0 auto;

  :deep(svg) {
    width: 18px;
    height: 18px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
}

.module-info {
  flex: 1;
  min-width: 0;
}

.module-title {
  margin: 0;
  font-size: 14px;
  color: inherit;
  font-weight: 500;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
}

.module-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: #7a86a0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
}

.user-settings-footer {
  position: relative;
  z-index: 30;
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  min-height: 48px;
  margin-top: 10px;
  padding: 9px 4px 0;
  border-top: 1px solid #e4eaf2;
  background: #f8fafc;

  .collapsed & {
    gap: 0;
    justify-content: space-between;
    padding-right: 0;
    padding-left: 0;
  }
}

.user-identity {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
}

.user-name {
  min-width: 0;
  overflow: hidden;
  color: #35425f;
  font-size: 13px;
  font-weight: 500;
  line-height: 32px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-initial {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: #526173;
  background: #e8eef6;
  font-size: 11px;
  font-weight: 600;
}

.settings-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  padding: 0;
  border: none;
  border-radius: 8px;
  color: #69758c;
  background: transparent;
  cursor: pointer;

  svg {
    width: 18px;
    height: 18px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.55;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  &:hover,
  &[aria-expanded='true'] {
    color: #1976d2;
    background: #eaf2fb;
  }

  &:focus-visible {
    outline: 2px solid #8abfff;
    outline-offset: 2px;
  }
}

.user-settings-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 196px;
  padding: 6px;
  border: 1px solid #e0e7f0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 30px rgba(31, 42, 68, 0.14);

  .collapsed & {
    right: auto;
    bottom: 0;
    left: 52px;
    width: 196px;
  }
}

.settings-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 36px;
  padding: 7px 9px;
  border: none;
  border-radius: 7px;
  color: #526173;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  text-align: left;

  &:hover,
  &:focus-visible {
    color: #1976d2;
    background: #eef4fb;
    outline: none;
  }

  &.active {
    color: #1976d2;
    background: #e3f2fd;
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

.conversation-view-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.conversation-view-icon {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: #64748b;
  cursor: pointer;
  padding: 0;
  transition: all 0.2s;

  svg {
    width: 16px;
    height: 16px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  &:hover {
    background: #eef4ff;
    color: #1565c0;
  }

  &.active {
    border-color: #b7d4ff;
    background: #e9f3ff;
    color: #1565c0;
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

  &.running {
    background: #eef7f1;
  }
}

.recent-session-empty {
  padding: 10px;
  color: #8a94a6;
  font-size: 12px;
  text-align: center;
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

@media (max-width: 760px) {
  .assistant-sidebar,
  .assistant-sidebar.collapsed {
    width: 60px;
    padding: 0 8px 14px;
  }

  .sidebar-header {
    justify-content: center;
  }

  .sidebar-header .header-title-wrapper,
  .module-info,
  .recent-sessions-section,
  .user-identity {
    display: none;
  }

  .collapse-btn {
    margin: 0;
  }

  .primary-navigation,
  .new-session-section,
  .module-list,
  .module-group {
    align-items: center;
  }

  .module-card {
    width: 44px;
    height: 40px;
    justify-content: center;
    gap: 0;
    padding: 0;
  }

  .sidebar-scroll-area {
    display: none;
  }

  .user-settings-footer {
    justify-content: center;
    padding-right: 0;
    padding-left: 0;
  }

  .user-settings-menu {
    right: auto;
    bottom: 0;
    left: 52px;
    width: 196px;
  }
}
</style>
