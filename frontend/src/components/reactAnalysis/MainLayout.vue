<template>
  <div class="main-layout">
    <!-- 左侧边栏 -->
    <AssistantSidebar
      :activeModule="activeModule"
      :collapsed="leftSidebarCollapsed"
      :task-workspace-entries="taskWorkspaceEntries"
      @update:collapsed="handleCollapseChange"
      @update:activeModule="handleActiveModuleChange"
      @select="handleAssistantSelect"
      @action="handleSidebarAction"
      @loadSession="handleLoadSession"
    />

    <!-- 主分析面板 -->
    <div class="analysis-panel" ref="layoutRef">
      <AgentPlatform
        v-if="workspace === 'platform'"
        :running-modes="runningAgentModes"
        :selecting-mode="selectingAgentMode"
        :error="agentPlatformError"
        :scheduled-tasks="taskWorkspaceEntries"
        @select="$emit('select-agent', $event)"
        @select-task="handleTaskWorkspaceSelect"
      />
      <component
        :is="AirQualityForecastView"
        v-else-if="workspace === 'forecast' && AirQualityForecastView"
        class="forecast-workspace"
        embedded
      />
      <template v-else>
        <div class="conversation-workspace">
          <ChatArea
        :agent-mode="agentMode"
        :messages="messages"
        :pending-steering-inputs="pendingSteeringInputs"
        :pending-interaction="pendingInteraction"
        :interaction-resolving="interactionResolving"
        :is-analyzing="isAnalyzing"
        :input-disabled="inputDisabled || conversationReadOnly"
        :read-only="conversationReadOnly"
        :read-only-notice="conversationReadOnlyNotice"
        :current-message="currentMessage"
        :session-id="sessionId"
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
        @drag-over="handleChatAreaDragOver"
        @drag-leave="handleChatAreaDragLeave"
        @drop="handleChatAreaDrop"
        @select-message="handleSelectMessage"
        @load-more="handleLoadMore"
        @preview-message-attachment="handleMessageAttachmentPreview"
        @toggle-viz-panel="handleToggleVizPanel"
        @new-web-conversation="$emit('new-web-conversation')"
        @resolve-interaction="$emit('resolve-interaction', $event)"
        @close-interaction="$emit('close-interaction')"
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
            @restore-execution-session="$emit('restore-execution-session', $event)"
          />

          <TaskExecutionWorkspace
            v-else-if="managementPanel === 'task-workspace'"
            :task="taskWorkspaceTask"
            @close="$emit('close-management-panel')"
            @restore-execution-session="$emit('restore-execution-session', $event)"
          />

          <SessionHistoryPanel
            v-else-if="managementPanel === 'session-history'"
            :sessions="sessionHistoryData"
            :session-history-stats="sessionHistoryStats"
            :session-history-loading="sessionHistoryLoading"
            :is-admin="auth.user?.admin === true"
            @close="$emit('close-management-panel')"
            @refresh-sessions="$emit('refresh-session-history')"
            @cleanup-sessions="$emit('cleanup-sessions')"
            @restore-session="$emit('restore-session', $event)"
            @toggle-session-case="$emit('toggle-session-case', $event)"
            @delete-sessions="$emit('delete-sessions', $event)"
          />

          <SocialPlatformPanel
            v-else-if="managementPanel === 'social-platform'"
            @close="$emit('close-management-panel')"
          />

          <ToolsManagementPanel
            v-else-if="managementPanel === 'tools-management'"
            @close="$emit('close-management-panel')"
          />

          <SkillsManagementPanel
            v-else-if="managementPanel === 'skills-management'"
            @close="$emit('close-management-panel')"
          />

          <FileManagerPanel
            v-else-if="managementPanel === 'file-manager'"
            @close="$emit('close-management-panel')"
          />
        </template>
          </ChatArea>
        </div>
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
        :knowledge-panel-visible="knowledgePanelVisible"
        :active-tab="activeRightTab"
        :panel-style="vizPanelStyle"
        :assistant-mode="agentMode"
        :board="board"
        :messages="messages"
        :selected-message-id="selectedMessageId"
        :session-id="sessionId"
        :expert-results="expertResults"
        :knowledge-sources="knowledgeSources"
        @tab-change="handleTabChange"
        @board-xml-change="handleBoardXmlChange"
        @board-selection-change="handleBoardSelectionChange"
        @board-snapshot-confirm="handleBoardSnapshotConfirm"
        />
      </template>
    </div>
  </div>
</template>

<script setup>
import { defineAsyncComponent, ref, computed, watch } from 'vue'
import AssistantSidebar from '@/components/AssistantSidebar.vue'
import AgentPlatform from '@/components/agentPlatform/AgentPlatform.vue'
import { projectConfig } from '@/config/projectConfig.js'
import ChatArea from './ChatArea.vue'
import RightPanelContainer from './RightPanelContainer.vue'
import WidthResizer from './WidthResizer.vue'
import KnowledgeBasePanel from '@/components/management/KnowledgeBasePanel.vue'
import FetchersPanel from '@/components/management/FetchersPanel.vue'
import ScheduledTasksPanel from '@/components/management/ScheduledTasksPanel.vue'
import TaskExecutionWorkspace from '@/components/management/TaskExecutionWorkspace.vue'
import SessionHistoryPanel from '@/components/management/SessionHistoryPanel.vue'
import SocialPlatformPanel from '@/components/management/SocialPlatformPanel.vue'
import ToolsManagementPanel from '@/components/management/ToolsManagementPanel.vue'
import SkillsManagementPanel from '@/components/management/SkillsManagementPanel.vue'
import FileManagerPanel from '@/components/FileManagerPanel.vue'
import { useAuthStore } from '@/auth/authStore.js'

const AirQualityForecastView = projectConfig.hasModule('xuchang-air-quality')
  ? defineAsyncComponent(() => import('@/views/AirQualityForecastView.vue'))
  : null

const auth = useAuthStore()

const props = defineProps({
  taskWorkspaceEntries: { type: Array, default: () => [] },
  taskWorkspaceTask: { type: Object, default: null },
  workspace: {
    type: String,
    default: 'platform'
  },
  runningAgentModes: {
    type: Array,
    default: () => []
  },
  selectingAgentMode: {
    type: String,
    default: ''
  },
  agentPlatformError: {
    type: String,
    default: ''
  },
  // Store状态
  messages: {
    type: Array,
    default: () => []
  },
  pendingSteeringInputs: {
    type: Array,
    default: () => []
  },
  pendingInteraction: {
    type: Object,
    default: null
  },
  interactionResolving: {
    type: Boolean,
    default: false
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
  expertResults: {
    type: Object,
    default: null
  },
  board: {
    type: Object,
    default: null
  },
  // 面板状态
  activeModule: {
    type: String,
    default: 'general-agent'
  },
  agentMode: {
    type: String,
    default: 'expert'
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
  hasResourceContent: {
    type: Boolean,
    default: false
  },
  knowledgePanelVisible: {
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
  },
  conversationReadOnly: {
    type: Boolean,
    default: false
  },
  conversationReadOnlyNotice: {
    type: String,
    default: ''
  }
})

const emit = defineEmits([
  'update:activeModule',
  'update:leftSidebarCollapsed',
  'update:layout-ref',
  'send',
  'pause',
  'update:useReranker',
  'select-message',
  'load-more',
  'assistant-select',
  'sidebar-action',
  'load-session',
  'start-drag',
  'stop-drag',
  'reset-width',
  'tab-change',
  'board-xml-change',
  'board-selection-change',
  'board-snapshot-confirm',
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
  'restore-execution-session',
  'refresh-session-history',
  'cleanup-sessions',
  'restore-session',
  'toggle-session-case',
  'delete-sessions',
  'new-web-conversation',
  'select-agent',
  'preview-message-attachment',
  'resolve-interaction',
  'close-interaction'
])

const layoutRef = ref(null)

// 右侧面板展开状态（用于ChatArea的展开/隐藏按钮）
const rightPanelExpanded = ref(true)

// 计算是否有可视化内容（用于显示/隐藏ChatArea中的按钮）
const hasVizContent = computed(() => {
  return Boolean(props.sessionId) || props.rightPanelVisible || props.hasResourceContent
})

// 计算知识溯源数据
const knowledgeSources = computed(() => {
  let sources = []

  // 1. 优先从选中消息的data.sources获取
  if (props.selectedMessageId && props.messages && props.messages.length > 0) {
    const selectedMsg = props.messages.find(msg => msg.id === props.selectedMessageId)
    if (selectedMsg) {
      if (selectedMsg?.data?.sources && Array.isArray(selectedMsg.data.sources)) {
        sources = selectedMsg.data.sources
      }
      // 兼容旧格式：直接在msg上的sources字段
      else if (selectedMsg?.sources && Array.isArray(selectedMsg.sources)) {
        sources = selectedMsg.sources
      }
    }
  }

  // 2. 如果没有选中的消息，从最后一条消息的data.sources获取
  if (sources.length === 0 && props.messages && props.messages.length > 0) {
    const lastMsg = props.messages[props.messages.length - 1]
    if (lastMsg?.data?.sources && Array.isArray(lastMsg.data.sources)) {
      sources = lastMsg.data.sources
    }
    // 兼容旧格式：直接在msg上的sources字段
    else if (lastMsg?.sources && Array.isArray(lastMsg.sources)) {
      sources = lastMsg.sources
    }
  }

  return sources
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

const handleTaskWorkspaceSelect = (task) => {
  emit('sidebar-action', { type: 'task-workspace', taskId: task.task_id })
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

const handleSelectMessage = (messageId) => {
  emit('select-message', messageId)
}

const handleLoadMore = () => {
  emit('load-more')
}

const handleMessageAttachmentPreview = (payload) => {
  emit('preview-message-attachment', payload)
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

const handleBoardXmlChange = (xml) => {
  emit('board-xml-change', xml)
}

const handleBoardSelectionChange = (selection) => {
  emit('board-selection-change', selection)
}

const handleBoardSnapshotConfirm = (snapshot) => {
  emit('board-snapshot-confirm', snapshot)
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

.forecast-workspace {
  flex: 1 1 0%;
  min-width: 0;
}

.conversation-workspace {
  display: flex;
  flex: 1 1 0%;
  flex-direction: column;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.conversation-workspace :deep(.chat-area),
.conversation-workspace :deep(.query-dashboard-workspace) {
  flex: 1 1 0%;
  min-height: 0;
  min-width: 0;
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
