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
      <AgentPlatform
        v-if="workspace === 'platform'"
        :running-modes="runningAgentModes"
        :selecting-mode="selectingAgentMode"
        :error="agentPlatformError"
        @select="$emit('select-agent', $event)"
      />
      <template v-else>
        <div class="conversation-workspace">
          <AgentWorkspaceHeader :mode="agentMode" />
          <QueryDashboardWorkspace
            v-if="agentMode === 'query'"
        :messages="messages"
        :pending-steering-inputs="pendingSteeringInputs"
        :is-analyzing="isAnalyzing"
        :input-disabled="inputDisabled || conversationReadOnly"
        :read-only="conversationReadOnly"
        :read-only-notice="conversationReadOnlyNotice"
        :current-message="currentMessage"
        :session-id="sessionId"
        :selected-message-id="selectedMessageId"
        :show-reflexion="showReflexion"
        :reflexion-count="reflexionCount"
        :assistant-mode="activeModule"
        :use-reranker="useReranker"
        :has-more-messages="hasMoreMessages"
        :total-message-count="totalMessageCount"
        :loading-more="loadingMore"
        :map-program="mapProgram"
        :drag-over="chatAreaDragOver"
        :right-panel-expanded="rightPanelExpanded"
        :has-viz-content="hasVizContent"
        :show-management-panel="!!managementPanel"
        @send="handleSend"
        @pause="handlePause"
        @update:useReranker="handleRerankerChange"
        @select-message="handleSelectMessage"
        @load-more="handleLoadMore"
        @drag-over="handleChatAreaDragOver"
        @drag-leave="handleChatAreaDragLeave"
        @drop="handleChatAreaDrop"
        @toggle-viz-panel="handleToggleVizPanel"
        @map-event="$emit('map-event', $event)"
        @new-web-conversation="$emit('new-web-conversation')"
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
      </QueryDashboardWorkspace>
          <ChatArea
            v-else
        :messages="messages"
        :pending-steering-inputs="pendingSteeringInputs"
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
        @toggle-viz-panel="handleToggleVizPanel"
        @new-web-conversation="$emit('new-web-conversation')"
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
        :viz-panel-visible="vizPanelVisible"
        :office-panel-visible="officePanelVisible"
        :knowledge-panel-visible="knowledgePanelVisible"
        :board-panel-visible="boardPanelVisible"
        :active-tab="activeRightTab"
        :panel-style="vizPanelStyle"
        :assistant-mode="agentMode"
        :visualization-content="visualizationContent"
        :board="board"
        :messages="messages"
        :selected-message-id="selectedMessageId"
        :session-id="sessionId"
        :expert-results="expertResults"
        :knowledge-sources="knowledgeSources"
        @tab-change="handleTabChange"
        @office-edit-submit="handleOfficeEditSubmit"
        @board-xml-change="handleBoardXmlChange"
        @board-selection-change="handleBoardSelectionChange"
        @board-snapshot-confirm="handleBoardSnapshotConfirm"
        @board-version-restore="handleBoardVersionRestore"
        />
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import AssistantSidebar from '@/components/AssistantSidebar.vue'
import AgentPlatform from '@/components/agentPlatform/AgentPlatform.vue'
import AgentWorkspaceHeader from '@/components/agentPlatform/AgentWorkspaceHeader.vue'
import ChatArea from './ChatArea.vue'
import QueryDashboardWorkspace from '@/components/queryDashboard/QueryDashboardWorkspace.vue'
import RightPanelContainer from './RightPanelContainer.vue'
import WidthResizer from './WidthResizer.vue'
import KnowledgeBasePanel from '@/components/management/KnowledgeBasePanel.vue'
import FetchersPanel from '@/components/management/FetchersPanel.vue'
import ScheduledTasksPanel from '@/components/management/ScheduledTasksPanel.vue'
import SessionHistoryPanel from '@/components/management/SessionHistoryPanel.vue'
import SocialPlatformPanel from '@/components/management/SocialPlatformPanel.vue'
import ToolsManagementPanel from '@/components/management/ToolsManagementPanel.vue'
import SkillsManagementPanel from '@/components/management/SkillsManagementPanel.vue'
import FileManagerPanel from '@/components/FileManagerPanel.vue'
import { useAuthStore } from '@/auth/authStore.js'

const auth = useAuthStore()

const props = defineProps({
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
  board: {
    type: Object,
    default: null
  },
  mapProgram: {
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
  vizPanelVisible: {
    type: Boolean,
    default: false
  },
  officePanelVisible: {
    type: Boolean,
    default: false
  },
  knowledgePanelVisible: {
    type: Boolean,
    default: false
  },
  boardPanelVisible: {
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
  'office-edit-submit',
  'board-xml-change',
  'board-selection-change',
  'board-snapshot-confirm',
  'board-version-restore',
  'chat-area-drag-over',
  'chat-area-drag-leave',
  'chat-area-drop',
  'toggle-viz-panel',
  'map-event',
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
  'restore-session',
  'toggle-session-case',
  'delete-sessions',
  'new-web-conversation',
  'select-agent'
])

const layoutRef = ref(null)

// 右侧面板展开状态（用于ChatArea的展开/隐藏按钮）
const rightPanelExpanded = ref(true)

// 计算是否有可视化内容（用于显示/隐藏ChatArea中的按钮）
const hasVizContent = computed(() => {
  // 只要有右侧面板可见，就显示按钮
  return props.vizPanelVisible || props.officePanelVisible || props.knowledgePanelVisible || props.boardPanelVisible
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

  // 3. 如果还没有sources，尝试从visualizationContent中提取
  if (sources.length === 0 && props.visualizationContent?.visuals && Array.isArray(props.visualizationContent.visuals)) {
    const knowledgeVisuals = props.visualizationContent.visuals
      .filter(v => v.type === 'knowledge_source')
      .map((v) => ({
        title: v.title || '未知标题',
        document_name: v.title || '未知标题',
        source: v.data?.source || '未知来源',
        knowledge_base_name: v.data?.source || '未知来源',
        relevance: v.data?.relevance || 0,
        score: v.data?.relevance || 0,
        chunk_index: v.data?.chunk_index,
        document_id: v.data?.document_id,
        knowledge_base_id: v.data?.knowledge_base_id,
        content: v.data?.content || ''
      }))
    sources = knowledgeVisuals
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

const handleBoardXmlChange = (xml) => {
  emit('board-xml-change', xml)
}

const handleBoardSelectionChange = (selection) => {
  emit('board-selection-change', selection)
}

const handleBoardSnapshotConfirm = (snapshot) => {
  emit('board-snapshot-confirm', snapshot)
}

const handleBoardVersionRestore = (versionId) => {
  emit('board-version-restore', versionId)
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
