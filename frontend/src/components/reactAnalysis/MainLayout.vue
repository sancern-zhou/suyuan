<template>
  <div class="main-layout">
    <!-- 左侧边栏 -->
    <AssistantSidebar
      :activeModule="activeModule"
      :collapsed="leftSidebarCollapsed"
      @update:collapsed="handleCollapseChange"
      @update:activeModule="handleActiveModuleChange"
      @select="handleAssistantSelect"
      @action="handleSidebarAction"
      @loadSession="handleLoadSession"
    />

    <!-- 主分析面板 -->
    <div class="analysis-panel" ref="layoutRef">
      <ChatArea
        :messages="messages"
        :is-analyzing="isAnalyzing"
        :input-disabled="inputDisabled"
        :current-message="currentMessage"
        :drag-over="chatAreaDragOver"
        :selected-message-id="selectedMessageId"
        :show-reflexion="showReflexion"
        :reflexion-count="reflexionCount"
        :assistant-mode="activeModule"
        :use-reranker="useReranker"
        :has-more-messages="hasMoreMessages"
        :total-message-count="totalMessageCount"
        :loading-more="loadingMore"
        :show-management-panel="!!managementPanel"
        :right-panel-expanded="rightPanelExpanded"
        :has-viz-content="hasVizContent"
        @send="handleSend"
        @pause="handlePause"
        @update:useReranker="handleRerankerChange"
        @update:agentMode="handleAgentModeChange"
        @drag-over="handleChatAreaDragOver"
        @drag-leave="handleChatAreaDragLeave"
        @drop="handleChatAreaDrop"
        @select-message="handleSelectMessage"
        @load-more="handleLoadMore"
        @toggle-viz-panel="handleToggleVizPanel"
      >
        <template #management-panels>
          <!-- 管理面板插槽 -->
          <KnowledgeBasePanel
            v-if="managementPanel === 'knowledge-base'"
            @show-create-dialog="$emit('show-kb-create-dialog')"
            @show-edit-dialog="$emit('show-kb-edit-dialog')"
            @close="$emit('close-management-panel')"
            @view-chunks="$emit('view-kb-chunks', $event)"
            @retry-doc="$emit('retry-kb-doc', $event)"
            @delete-doc="$emit('delete-kb-doc', $event)"
          />

          <FetchersPanel
            v-else-if="managementPanel === 'fetchers'"
            :fetcher-system-status="fetcherSystemStatus"
            :fetcher-loading="fetcherLoading"
            :fetcher-error="fetcherError"
            :fetcher-operating="fetcherOperating"
            :era5-historical-date="era5HistoricalDate"
            :era5-fetch-result="era5FetchResult"
            @close="$emit('close-management-panel')"
            @fetch-era5="$emit('fetch-era5', $event)"
            @refresh-status="$emit('refresh-fetcher-status')"
            @trigger-fetcher="$emit('trigger-fetcher', $event)"
            @pause-fetcher="$emit('pause-fetcher', $event)"
            @resume-fetcher="$emit('resume-fetcher', $event)"
            @update:era5-historical-date="handleEra5DateChange"
          />

          <ScheduledTasksPanel
            v-else-if="managementPanel === 'scheduled-tasks'"
            :tasks="scheduledTasks"
            :stats="scheduledTasksStats"
            :scheduled-tasks-refreshing="scheduledTasksRefreshing"
            @close="$emit('close-management-panel')"
            @refresh-tasks="$emit('refresh-scheduled-tasks')"
            @toggle-task="$emit('toggle-scheduled-task', $event)"
            @execute-task="$emit('execute-scheduled-task', $event)"
            @edit-task="$emit('edit-scheduled-task', $event)"
            @delete-task="$emit('delete-scheduled-task', $event)"
          />

          <SessionHistoryPanel
            v-else-if="managementPanel === 'session-history'"
            :sessions="sessionHistoryData"
            :session-history-stats="sessionHistoryStats"
            :session-history-loading="sessionHistoryLoading"
            @close="$emit('close-management-panel')"
            @refresh-sessions="$emit('refresh-session-history')"
            @cleanup-sessions="$emit('cleanup-sessions')"
            @restore-session="$emit('restore-session', $event)"
          />

          <SocialPlatformPanel
            v-else-if="managementPanel === 'social-platform'"
            @close="$emit('close-management-panel')"
          />

          <ToolsManagementPanel
            v-else-if="managementPanel === 'tools-management'"
            @close="$emit('close-management-panel')"
          />
        </template>
      </ChatArea>

      <!-- 宽度调整器 -->
      <WidthResizer
        v-if="rightPanelVisible"
        :visible="rightPanelVisible"
        :is-dragging="isDragging"
        @start-drag="handleStartDrag"
        @stop-drag="handleStopDrag"
        @reset="handleResetWidth"
      />

      <!-- 右侧面板 -->
      <RightPanelContainer
        v-if="rightPanelVisible"
        :visible="rightPanelVisible"
        :viz-panel-visible="vizPanelVisible"
        :office-panel-visible="officePanelVisible"
        :active-tab="activeRightTab"
        :panel-style="vizPanelStyle"
        :assistant-mode="activeModule"
        :visualization-content="visualizationContent"
        :messages="messages"
        :selected-message-id="selectedMessageId"
        :session-id="sessionId"
        :expert-results="expertResults"
        @tab-change="handleTabChange"
        @office-edit-submit="handleOfficeEditSubmit"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import AssistantSidebar from '@/components/AssistantSidebar.vue'
import ChatArea from './ChatArea.vue'
import RightPanelContainer from './RightPanelContainer.vue'
import WidthResizer from './WidthResizer.vue'
import KnowledgeBasePanel from '@/components/management/KnowledgeBasePanel.vue'
import FetchersPanel from '@/components/management/FetchersPanel.vue'
import ScheduledTasksPanel from '@/components/management/ScheduledTasksPanel.vue'
import SessionHistoryPanel from '@/components/management/SessionHistoryPanel.vue'
import SocialPlatformPanel from '@/components/management/SocialPlatformPanel.vue'
import ToolsManagementPanel from '@/components/management/ToolsManagementPanel.vue'

const props = defineProps({
  // Store状态
  messages: {
    type: Array,
    default: () => []
  },
  isAnalyzing: {
    type: Boolean,
    default: false
  },
  inputDisabled: {
    type: Boolean,
    default: false
  },
  currentMessage: {
    type: String,
    default: ''
  },
  showReflexion: {
    type: Boolean,
    default: false
  },
  reflexionCount: {
    type: Number,
    default: 0
  },
  useReranker: {
    type: Boolean,
    default: false
  },
  hasMoreMessages: {
    type: Boolean,
    default: false
  },
  totalMessageCount: {
    type: Number,
    default: 0
  },
  loadingMore: {
    type: Boolean,
    default: false
  },
  sessionId: {
    type: String,
    default: ''
  },
  visualizationContent: {
    type: Object,
    default: null
  },
  expertResults: {
    type: Object,
    default: null
  },

  // 面板状态
  activeModule: {
    type: String,
    default: 'general-agent'
  },
  leftSidebarCollapsed: {
    type: Boolean,
    default: false
  },
  managementPanel: {
    type: String,
    default: null
  },
  rightPanelVisible: {
    type: Boolean,
    default: false
  },
  vizPanelVisible: {
    type: Boolean,
    default: false
  },
  officePanelVisible: {
    type: Boolean,
    default: false
  },
  activeRightTab: {
    type: String,
    default: 'visualization'
  },
  vizPanelStyle: {
    type: Object,
    default: () => ({})
  },
  isDragging: {
    type: Boolean,
    default: false
  },
  chatAreaDragOver: {
    type: Boolean,
    default: false
  },
  selectedMessageId: {
    type: String,
    default: null
  },

  // 抓取器状态
  fetcherSystemStatus: {
    type: Object,
    default: null
  },
  fetcherLoading: {
    type: Boolean,
    default: false
  },
  fetcherError: {
    type: String,
    default: null
  },
  fetcherOperating: {
    type: Boolean,
    default: false
  },
  era5FetchResult: {
    type: Object,
    default: null
  },
  era5HistoricalDate: {
    type: String,
    default: ''
  },

  // 定时任务状态
  scheduledTasks: {
    type: Array,
    default: () => []
  },
  scheduledTasksStats: {
    type: Object,
    default: null
  },
  scheduledTasksRefreshing: {
    type: Boolean,
    default: false
  },

  // 会话历史状态
  sessionHistoryData: {
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

const emit = defineEmits([
  'update:activeModule',
  'update:leftSidebarCollapsed',
  'update:layout-ref',
  'send',
  'pause',
  'update:useReranker',
  'update:agentMode',
  'select-message',
  'load-more',
  'assistant-select',
  'sidebar-action',
  'load-session',
  'start-drag',
  'stop-drag',
  'reset-width',
  'tab-change',
  'office-edit-submit',
  'chat-area-drag-over',
  'chat-area-drag-leave',
  'chat-area-drop',
  'toggle-viz-panel',
  'update:era5HistoricalDate',
  'close-management-panel',
  'show-kb-create-dialog',
  'show-kb-edit-dialog',
  'view-kb-chunks',
  'retry-kb-doc',
  'delete-kb-doc',
  'fetch-era5',
  'refresh-fetcher-status',
  'trigger-fetcher',
  'pause-fetcher',
  'resume-fetcher',
  'refresh-scheduled-tasks',
  'toggle-scheduled-task',
  'execute-scheduled-task',
  'edit-scheduled-task',
  'delete-scheduled-task',
  'refresh-session-history',
  'cleanup-sessions',
  'restore-session'
])

const layoutRef = ref(null)

// 右侧面板展开状态（用于ChatArea的展开/隐藏按钮）
const rightPanelExpanded = ref(true)

// 计算是否有可视化内容（用于显示/隐藏ChatArea中的按钮）
const hasVizContent = computed(() => {
  // 只要有右侧面板可见，就显示按钮
  return props.vizPanelVisible || props.officePanelVisible
})

// 监听 layoutRef 变化并通知父组件
watch(layoutRef, (newEl) => {
  emit('update:layout-ref', newEl)
})

// 同步右侧面板展开状态
watch(() => props.rightPanelVisible, (newValue) => {
  rightPanelExpanded.value = newValue
}, { immediate: true })

// 事件处理
const handleCollapseChange = (value) => {
  emit('update:leftSidebarCollapsed', value)
}

const handleActiveModuleChange = (value) => {
  emit('update:activeModule', value)
}

const handleAssistantSelect = (moduleId) => {
  emit('assistant-select', moduleId)
}

const handleSidebarAction = (actionId) => {
  emit('sidebar-action', actionId)
}

const handleLoadSession = (sessionId) => {
  emit('load-session', sessionId)
}

const handleSend = (payload) => {
  emit('send', payload)
}

const handlePause = () => {
  emit('pause')
}

const handleRerankerChange = (value) => {
  emit('update:useReranker', value)
}

const handleAgentModeChange = (value) => {
  emit('update:agentMode', value)
}

const handleSelectMessage = (messageId) => {
  emit('select-message', messageId)
}

const handleLoadMore = () => {
  emit('load-more')
}

const handleStartDrag = (event) => {
  emit('start-drag', event)
}

const handleStopDrag = () => {
  emit('stop-drag')
}

const handleResetWidth = () => {
  emit('reset-width')
}

const handleTabChange = (tab) => {
  emit('tab-change', tab)
}

const handleOfficeEditSubmit = (data) => {
  emit('office-edit-submit', data)
}

// 处理右侧面板展开/隐藏
const handleToggleVizPanel = () => {
  rightPanelExpanded.value = !rightPanelExpanded.value
  // 通知父组件切换右侧面板状态
  emit('toggle-viz-panel')
}

const handleChatAreaDragOver = (e) => {
  emit('chat-area-drag-over', e)
}

const handleChatAreaDragLeave = (e) => {
  emit('chat-area-drag-leave', e)
}

const handleChatAreaDrop = (e) => {
  emit('chat-area-drop', e)
}

const handleEra5DateChange = (date) => {
  emit('update:era5HistoricalDate', date)
}

defineExpose({ layoutRef })
</script>

<style scoped>
.main-layout {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.analysis-panel {
  flex: 1;
  display: flex;
  height: 100%;
  overflow: hidden;
}

/* ChatArea 占据剩余空间，min-width: 0 防止内容撑开 */
.analysis-panel :deep(.chat-area) {
  flex: 1 1 0%;
  min-width: 0;
}

/* WidthResizer 固定宽度 */
.analysis-panel :deep(.resize-handle) {
  flex: 0 0 4px;
}
</style>
