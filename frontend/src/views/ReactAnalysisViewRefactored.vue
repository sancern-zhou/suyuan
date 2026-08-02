<template>
  <div class="react-analysis-view">
    <!-- 会话管理模态框 -->
    <SessionManagerModal
      v-model="showSessionManager"
      @restore="handleSessionRestore"
    />

    <!-- 主布局 -->
    <MainLayout
      :messages="currentModeMessages"
      :pending-steering-inputs="currentModePendingSteeringInputs"
      :is-analyzing="currentModeIsAnalyzing"
      :input-disabled="inputDisabled"
      :current-message="currentModeCurrentMessage"
      :show-reflexion="store.currentState.showReflexion"
      :reflexion-count="store.currentState.reflexionCount"
      :use-reranker="useReranker"
      :has-more-messages="store.currentState.pagination.hasMoreMessages"
      :total-message-count="store.currentState.pagination.totalMessageCount"
      :loading-more="store.currentState.pagination.loadingMore"
      :session-id="currentModeSessionId"
      :expert-results="currentModeExpertResults"
      :active-module="activeAssistant"
      :agent-mode="store.currentMode"
      :left-sidebar-collapsed="leftSidebarCollapsed"
      :management-panel="managementPanel"
      :right-panel-visible="rightPanelVisible"
      :knowledge-panel-visible="knowledgePanelVisible"
      :active-right-tab="activeRightTab"
      :viz-panel-style="vizPanelStyle"
      :board="store.currentState.board"
      :is-dragging="isDragging"
      :chat-area-drag-over="chatAreaDragOver"
      :selected-message-id="selectedMessageId"
      :fetcher-system-status="fetcherSystemStatus"
      :fetcher-loading="fetcherLoading"
      :fetcher-error="fetcherError"
      :fetcher-operating="fetcherOperating"
      :era5-fetch-result="era5FetchResult"
      :scheduled-tasks="scheduledTasksStore.tasks"
      :scheduled-tasks-stats="scheduledTasksStore.stats"
      :scheduled-tasks-refreshing="scheduledTasksRefreshing"
      :session-history-data="sessionHistoryData"
      :session-history-stats="sessionHistoryStats"
      :session-history-loading="sessionHistoryLoading"
      :conversation-read-only="currentConversationPolicy.readOnly"
      :conversation-read-only-notice="currentConversationPolicy.notice"
      @update:active-module="handleAssistantSelect"
      @update:left-sidebar-collapsed="leftSidebarCollapsed = $event"
      @update:layout-ref="setLayoutRef"
      @send="handleSend"
      @pause="handlePause"
      @update:use-reranker="handleRerankerChange"
      @update:agent-mode="handleAgentModeChange"
      @select-message="selectMessage"
      @load-more="handleLoadMore"
      @assistant-select="handleAssistantSelect"
      @sidebar-action="handleSidebarAction"
      @load-session="handleLoadSession"
      @start-drag="startDragging"
      @stop-drag="stopDragging"
      @reset-width="resetWidth"
      @tab-change="activeRightTab = $event"
      @preview-message-attachment="openMessageAttachmentPreview"
      @board-xml-change="handleBoardXmlChange"
      @board-selection-change="handleBoardSelectionChange"
      @board-snapshot-confirm="handleBoardSnapshotConfirm"
      @board-version-restore="handleBoardVersionRestore"
      @chat-area-drag-over="handleChatAreaDragOver"
      @chat-area-drag-leave="handleChatAreaDragLeave"
      @chat-area-drop="handleChatAreaDrop"
      @toggle-viz-panel="toggleVizPanel"
      @show-kb-create-dialog="openDialog('kbCreate')"
      @show-kb-edit-dialog="openDialog('kbEdit')"
      @close-management-panel="managementPanel = null"
      @view-kb-chunks="viewKbChunks"
      @retry-kb-doc="handleKbRetry"
      @delete-kb-doc="handleKbDeleteDoc"
      @fetch-era5="fetchEra5Historical"
      @refresh-fetcher-status="refreshFetcherStatus"
      @trigger-fetcher="triggerFetcher"
      @pause-fetcher="pauseFetcher"
      @resume-fetcher="resumeFetcher"
      @refresh-scheduled-tasks="refreshScheduledTasks"
      @toggle-scheduled-task="handleScheduledTaskToggle"
      @execute-scheduled-task="executeScheduledTask"
      @edit-scheduled-task="editScheduledTask"
      @delete-scheduled-task="deleteScheduledTask"
      @refresh-session-history="refreshSessionHistory"
      @cleanup-sessions="handleSessionCleanup"
      @restore-session="handleSessionRestore"
      @toggle-session-case="handleToggleSessionCase"
      @delete-sessions="deleteSessions"
      @new-web-conversation="startNewWebConversation"
    />

    <!-- 知识库创建对话框 -->
    <KnowledgeBaseCreateDialog
      :visible="showKbCreateDialog"
      @confirm="handleKbCreateConfirm"
      @close="closeDialog('kbCreate')"
    />

    <!-- 知识库编辑对话框 -->
    <KnowledgeBaseEditDialog
      :visible="showKbEditDialog"
      :knowledge-base="kbStore.currentKb"
      @confirm="handleKbUpdateConfirm"
      @close="closeDialog('kbEdit')"
    />

    <!-- 文档分段对话框 -->
    <KnowledgeBaseChunksDialog
      :visible="showKbChunksDialog"
      :document="kbStore.currentDoc"
      :chunks="kbStore.documentChunks"
      :loading="kbStore.chunksLoading"
      :error="kbStore.chunksError"
      @close="closeDialog('kbChunks')"
      @retry="viewKbChunksRetry"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useReactStore } from '@/stores/reactStore'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'
import {
  deleteScheduledTask as deleteScheduledTaskAction,
  executeScheduledTask as executeScheduledTaskAction,
  refreshScheduledTaskManagement,
  toggleScheduledTask
} from '@/components/management/scheduledTaskActions.js'
import { PANEL_SIZES } from '@/utils/constants'

// 引入composables
import { usePanelManagement } from '@/composables/reactAnalysis/usePanelManagement'
import { useSessionManagement } from '@/composables/reactAnalysis/useSessionManagement'
import { useKnowledgeBaseOperations } from '@/composables/reactAnalysis/useKnowledgeBaseOperations'
import { useDataFetcher } from '@/composables/reactAnalysis/useDataFetcher'
import { useMessageOperations } from '@/composables/reactAnalysis/useMessageOperations'
import { useDialogManager } from '@/composables/reactAnalysis/useDialogManager'

// 引入组件
import MainLayout from '@/components/reactAnalysis/MainLayout.vue'
import SessionManagerModal from '@/components/SessionManagerModal.vue'
import KnowledgeBaseCreateDialog from '@/components/reactAnalysis/dialogs/KnowledgeBaseCreateDialog.vue'
import KnowledgeBaseEditDialog from '@/components/reactAnalysis/dialogs/KnowledgeBaseEditDialog.vue'
import KnowledgeBaseChunksDialog from '@/components/reactAnalysis/dialogs/KnowledgeBaseChunksDialog.vue'

// Stores
const router = useRouter()
const store = useReactStore()
const kbStore = useKnowledgeBaseStore()
const scheduledTasksStore = useScheduledTasksStore()

// ========== 使用Composables ==========

// 面板管理
const {
  managementPanel,
  rightPanelVisible,
  leftSidebarCollapsed,
  knowledgePanelVisible,
  activeRightTab,
  vizWidth,
  isDragging,
  layoutRef,
  vizPanelStyle,
  toggleVizPanel,
  showManagementPanel,
  hideManagementPanel,
  resetPanelState,
  startDragging,
  stopDragging,
  resetWidth,
  setLayoutRef,
  setupWatchers: setupPanelWatchers,
  openMessageAttachmentPreview
} = usePanelManagement(store)

// 定义折叠宽度
const collapsedVizWidth = PANEL_SIZES.COLLAPSED_VIZ_WIDTH

// 会话管理
const {
  showSessionManager,
  sessionHistoryLoading,
  sessionHistoryData,
  sessionHistoryStats,
  handleSend,
  handlePause,
  handleSessionRestore,
  handleLoadSession,
  refreshSessionHistory,
  handleSessionCleanup,
  deleteSessions,
  handleToggleSessionCase,
  currentConversationPolicy,
  startNewWebConversation
} = useSessionManagement(store)

// 知识库操作
const {
  kbCreateForm,
  kbEditForm,
  kbAdminConfirm,
  kbUploadOptions,
  kbIsDragging,
  kbIsUploading,
  kbUploadProgress,
  kbFileInput,
  handleKbCreate,
  handleKbUpdate,
  handleDeleteKb,
  selectKb,
  handleKbBack,
  handleKbRetry,
  handleKbDeleteDoc,
  viewKbChunks,
  triggerKbFileInput,
  handleKbFileSelect,
  uploadFiles,
  resetKbCreateForm,
  resetKbEditForm
} = useKnowledgeBaseOperations()

// 数据抓取
const {
  fetcherSystemStatus,
  fetcherLoading,
  fetcherError,
  fetcherOperating,
  era5HistoricalDate,
  era5FetchResult,
  refreshFetcherStatus,
  triggerFetcher,
  pauseFetcher,
  resumeFetcher,
  stopFetcher,
  fetchEra5Historical
} = useDataFetcher()

// 消息操作
const {
  selectedMessageId,
  selectMessage,
  deselectMessage,
  handleLoadMore
} = useMessageOperations(store)

// 对话框管理
const {
  dialogs,
  dialogData,
  openDialog,
  closeDialog
} = useDialogManager()

// ========== 本地状态 ==========

const activeAssistant = ref('general-agent')
const inputBoxRef = ref(null)
const vizPanelRef = ref(null)
const chatAreaDragOver = ref(false)
const useReranker = ref(false)
const scheduledTasksRefreshing = ref(false)
const era5HistoricalDate = ref('')

// 对话框状态（从dialogManager获取）
const showKbCreateDialog = computed(() => dialogs.value.kbCreate)
const showKbEditDialog = computed(() => dialogs.value.kbEdit)
const showKbChunksDialog = computed(() => dialogs.value.kbChunks)

// 知识库表单（从dialogData获取）
const kbCreateForm = computed(() => dialogData.value.kbCreate)
const kbEditForm = computed(() => dialogData.value.kbEdit)

// ========== 计算属性 ==========

const currentModeMessages = computed(() => store.currentState.messages)

const currentModeExpertResults = computed(() => store.currentState.lastExpertResults)
const currentModeSessionId = computed(() => store.currentState.sessionId)
const currentModeIsAnalyzing = computed(() => store.currentState.isAnalyzing)
const currentModeCurrentMessage = computed(() => store.currentState.currentMessage)
const currentModePendingSteeringInputs = computed(() => store.currentState.pendingSteeringInputs || [])

const inputDisabled = computed(() => {
  // 执行中允许用户预编辑下一条消息；发送由 InputBox 的 isAnalyzing 保护阻止。
  return false
})

// ========== 事件处理 ==========

const handleRerankerChange = (value) => {
  useReranker.value = value
}

const handleAgentModeChange = (value) => {
  store.switchMode(value)
  console.log('[ReactAnalysisView] Agent模式切换:', value)
}

const handleAssistantSelect = async (moduleId) => {
  if (moduleId !== 'general-agent' && store.currentState.isAnalyzing) {
    await store.pauseAnalysis()
  }
}

const handleSidebarAction = async (actionId) => {
  switch (actionId) {
    case 'query-dashboard':
      store.switchMode('query')
      hideManagementPanel()
      resetPanelState()
      break
    case 'tools-management':
      showManagementPanel('tools-management')
      break
    case 'knowledge-base':
      showManagementPanel('knowledge-base')
      await kbStore.fetchKnowledgeBases()
      break
    case 'fetchers':
      showManagementPanel('fetchers')
      await refreshFetcherStatus()
      break
    case 'scheduled-tasks':
      showManagementPanel('scheduled-tasks')
      await refreshScheduledTasks()
      break
    case 'session-history':
      showManagementPanel('session-history')
      await refreshSessionHistory()
      break
    case 'social-platform':
      showManagementPanel('social-platform')
      break
    case 'file-manager':
      // 显示右侧面板并切换到文件管理标签页
      activeRightTab.value = 'files'
      rightPanelVisible.value = true
      leftSidebarCollapsed.value = true
      vizWidth.value = collapsedVizWidth
      break
    case 'restart-session':
      store.restart()
      hideManagementPanel()
      resetPanelState()
      break
  }
}

const handleChatAreaDragOver = (e) => {
  if (e.dataTransfer.types.includes('Files')) {
    chatAreaDragOver.value = true
    e.dataTransfer.dropEffect = 'copy'
  }
}

const handleChatAreaDragLeave = (e) => {
  const rect = e.currentTarget.getBoundingClientRect()
  const x = e.clientX
  const y = e.clientY
  if (x < rect.left || x >= rect.right || y < rect.top || y >= rect.bottom) {
    chatAreaDragOver.value = false
  }
}

const handleChatAreaDrop = async (e) => {
  chatAreaDragOver.value = false
  const files = e.dataTransfer.files
  if (!files || files.length === 0) return

  if (inputBoxRef.value && typeof inputBoxRef.value.handleFilesDrop === 'function') {
    await inputBoxRef.value.handleFilesDrop(files)
  }
}

const handleBoardXmlChange = (xml) => {
  if (typeof store.updateDrawioBoardXml === 'function') {
    store.updateDrawioBoardXml(xml)
  }
}

const handleBoardSelectionChange = (selection) => {
  if (typeof store.updateDrawioBoardSelection === 'function') {
    store.updateDrawioBoardSelection(selection)
  }
}

const handleBoardSnapshotConfirm = async (snapshot) => {
  if (typeof store.confirmDrawioBoardSnapshot === 'function') {
    await store.confirmDrawioBoardSnapshot(snapshot)
  }
}

const handleBoardVersionRestore = (versionId) => {
  if (typeof store.restoreDrawioBoardVersion === 'function') {
    store.restoreDrawioBoardVersion(versionId)
  }
}

const handleKbCreateConfirm = async (formData) => {
  // 使用知识库composable的创建方法
  try {
    await kbStore.createKnowledgeBase(formData)
    closeDialog('kbCreate')
  } catch (e) {
    alert('创建失败: ' + e.message)
  }
}

const handleKbUpdateConfirm = async (formData) => {
  try {
    await kbStore.updateKnowledgeBase(formData.id, formData)
    closeDialog('kbEdit')
  } catch (e) {
    alert('更新失败: ' + e.message)
  }
}

const viewKbChunksRetry = async () => {
  if (kbStore.currentDoc) {
    await kbStore.fetchDocumentChunks(kbStore.currentDoc.id)
  }
}

// 定时任务管理
const refreshScheduledTasks = async () => {
  scheduledTasksRefreshing.value = true
  try {
    await refreshScheduledTaskManagement(scheduledTasksStore)
  } finally {
    scheduledTasksRefreshing.value = false
  }
}

const handleScheduledTaskToggle = async (task) => {
  await toggleScheduledTask(scheduledTasksStore, task)
}

const executeScheduledTask = async (task) => {
  try {
    await executeScheduledTaskAction(scheduledTasksStore, task)
    await refreshScheduledTasks()
  } catch (error) {
    console.error('Failed to execute scheduled task:', error)
    alert('立即执行失败: ' + (error.message || '未知错误'))
  }
}

const editScheduledTask = (task) => {
  console.log('编辑任务:', task)
}

const deleteScheduledTask = async (task) => {
  await deleteScheduledTaskAction(scheduledTasksStore, task)
}

// ========== 生命周期 ==========

onMounted(() => {
  setupPanelWatchers()
  // 初始化日期
  const today = new Date()
  era5HistoricalDate.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
})
</script>

<style scoped>
/* 样式将在后续版本中添加 */
</style>
