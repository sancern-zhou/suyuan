<template>
  <div class="react-analysis-view">
    <!-- 会话管理模态框 -->
    <SessionManagerModal
      v-model="showSessionManager"
      @restore="handleSessionRestoreAndClosePanel"
    />

    <!-- 主布局 -->
    <MainLayout
      ref="mainLayoutRef"
      :workspace="workspace"
      :running-agent-modes="runningAgentModes"
      :selecting-agent-mode="selectingAgentMode"
      :agent-platform-error="agentPlatformError"
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
      :active-module="workspace === 'platform' ? 'agent-platform' : (workspace === 'forecast' ? 'air-quality-forecast' : (managementPanel === 'task-workspace' && taskWorkspaceTask ? `task-workspace:${taskWorkspaceTask.task_id}` : activeAssistant))"
      :task-workspace-entries="taskWorkspaceEntries"
      :task-workspace-task="taskWorkspaceTask"
      :agent-mode="store.currentMode"
      :left-sidebar-collapsed="leftSidebarCollapsed"
      :management-panel="managementPanel"
      :right-panel-visible="rightPanelVisible"
      :has-resource-content="hasResourceContent"
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
      :era5-historical-date="era5HistoricalDate"
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
      @update:layout-ref="layoutRef = $event"
      @send="handleSend"
      @pause="handlePause"
      @update:use-reranker="handleRerankerChange"
      @select-message="selectMessage"
      @load-more="handleLoadMore"
      @update:era5-historical-date="era5HistoricalDate = $event"
      @assistant-select="handleAssistantSelect"
      @sidebar-action="handleSidebarAction"
      @select-agent="handleAgentSelect"
      @load-session="handleLoadSessionAndClosePanel"
      @start-drag="startDragging"
      @stop-drag="stopDragging"
      @reset-width="resetWidth"
      @tab-change="changeRightTab"
      @board-xml-change="handleBoardXmlChange"
      @board-selection-change="handleBoardSelectionChange"
      @board-snapshot-confirm="handleBoardSnapshotConfirm"
      @board-version-restore="handleBoardVersionRestore"
      @chat-area-drag-over="handleChatAreaDragOver"
      @chat-area-drag-leave="handleChatAreaDragLeave"
      @chat-area-drop="handleChatAreaDrop"
      @show-kb-create-dialog="openDialog('kbCreate')"
      @show-kb-edit-dialog="openDialog('kbEdit')"
      @close-management-panel="managementPanel = null"
      @view-kb-chunks="handleViewKbChunks"
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
      @restore-execution-session="handleSessionRestoreAndClosePanel"
      @refresh-session-history="refreshSessionHistory"
      @cleanup-sessions="handleSessionCleanup"
      @restore-session="handleSessionRestoreAndClosePanel"
      @toggle-session-case="handleToggleSessionCase"
      @delete-sessions="deleteSessions"
      @new-web-conversation="startNewWebConversation"
      @toggle-viz-panel="toggleVizPanel"
      @preview-message-attachment="openMessageAttachmentPreview"
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
import { useRoute } from 'vue-router'
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
import { confirmResourcePreviewLeave } from '@/services/resourcePreviewLeaveGuard.js'
import { AGENT_MODE_IDS } from '@/config/agentModes.js'
import { projectConfig, resolveProjectDefaultAgentMode } from '@/config/projectConfig.js'
import {
  getRunningAgentSessionId,
  isAgentModeRunning,
  resolveAgentSelection
} from '@/components/agentPlatform/workspacePolicy.js'

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
const route = useRoute()
const store = useReactStore()
const defaultAgentMode = resolveProjectDefaultAgentMode(projectConfig, AGENT_MODE_IDS)
const kbStore = useKnowledgeBaseStore()
const scheduledTasksStore = useScheduledTasksStore()
const taskWorkspaceTask = ref(null)
const taskWorkspaceEntries = computed(() => scheduledTasksStore.tasks.filter(task => task.workspace_entry?.enabled))

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
  changeRightTab,
  showManagementPanel,
  hideManagementPanel,
  resetPanelState,
  startDragging,
  stopDragging,
  resetWidth,
  setupWatchers: setupPanelWatchers,
  setupGlobalListeners,
  cleanupGlobalListeners,
  openMessageAttachmentPreview,
  hasVizContent: hasResourceContent
} = usePanelManagement(store)

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
const mainLayoutRef = ref(null)
const workspace = ref('platform')
const selectingAgentMode = ref('')
const agentPlatformError = ref('')

// 对话框状态（从dialogManager获取）
const showKbCreateDialog = computed(() => dialogs.value.kbCreate)
const showKbEditDialog = computed(() => dialogs.value.kbEdit)
const showKbChunksDialog = computed(() => dialogs.value.kbChunks)

// ========== 计算属性 ==========

const currentModeMessages = computed(() => store.currentState.messages)

const currentModeExpertResults = computed(() => store.currentState.lastExpertResults)
const currentModeSessionId = computed(() => store.currentState.sessionId)
const currentModeIsAnalyzing = computed(() => store.currentState.isAnalyzing)
const currentModeCurrentMessage = computed(() => store.currentState.currentMessage)
const currentModePendingSteeringInputs = computed(() => store.currentState.pendingSteeringInputs || [])
const runningAgentModes = computed(() => (
  AGENT_MODE_IDS.filter(mode => isAgentModeRunning(mode, store))
))

const inputDisabled = computed(() => {
  // 执行中允许用户预编辑下一条消息；发送由 InputBox 的 isAnalyzing 保护阻止。
  return false
})

// ========== 事件处理 ==========

const handleRerankerChange = (value) => {
  useReranker.value = value
}

const handleAgentSelect = async (mode) => {
  if (selectingAgentMode.value) return

  const decision = resolveAgentSelection(mode, store)
  if (decision.action === 'invalid') {
    agentPlatformError.value = '暂不支持该智能体模式'
    return
  }
  if (!await confirmResourcePreviewLeave()) return

  selectingAgentMode.value = mode
  agentPlatformError.value = ''

  try {
    if (decision.action === 'open-running') {
      const runningSessionId = getRunningAgentSessionId(mode, store)
      if (runningSessionId) {
        store._activateSession(runningSessionId, mode)
      } else {
        store.switchMode(mode)
      }
    } else {
      store.switchMode(mode)
      store.reset()
    }
    hideManagementPanel()
    resetPanelState()
    activeAssistant.value = 'general-agent'
    workspace.value = 'chat'
  } catch (error) {
    agentPlatformError.value = error?.message || '智能体初始化失败，请重试'
  } finally {
    selectingAgentMode.value = ''
  }
}

const handleLoadSessionAndClosePanel = async (sessionId) => {
  const restored = await handleLoadSession(sessionId)
  if (restored) {
    hideManagementPanel()
    workspace.value = 'chat'
  }
  return restored
}

const handleSessionRestoreAndClosePanel = async (sessionId) => {
  const restored = await handleSessionRestore(sessionId)
  if (restored) {
    hideManagementPanel()
    workspace.value = 'chat'
    if (taskWorkspaceTask.value) {
      rightPanelVisible.value = true
      activeRightTab.value = 'files'
    }
  }
  return restored
}

let routeSessionRestoreQueue = Promise.resolve()
const queueRouteSessionRestore = (sessionId) => {
  routeSessionRestoreQueue = routeSessionRestoreQueue
    .then(async () => {
      if (!sessionId || sessionId !== route.params.id) return false
      return handleSessionRestoreAndClosePanel(sessionId)
    })
    .catch((error) => {
      console.error('[ReactAnalysisView] 路由会话恢复失败:', error)
      return false
    })
  return routeSessionRestoreQueue
}

watch(
  () => route.params.id,
  (sessionId) => {
    if (sessionId) {
      queueRouteSessionRestore(sessionId)
      return
    }
    hideManagementPanel()
    resetPanelState()
    workspace.value = 'platform'
  }
)

const handleAssistantSelect = async (moduleId) => {
  if (moduleId !== 'general-agent' && store.currentState.isAnalyzing) {
    await store.pauseAnalysis()
  }
}

const handleSidebarAction = async (actionId) => {
  if (typeof actionId === 'object' && actionId?.type === 'task-workspace') {
    await scheduledTasksStore.fetchTasks()
    const task = scheduledTasksStore.tasks.find(item => item.task_id === actionId.taskId)
    if (!task) return
    taskWorkspaceTask.value = task
    workspace.value = 'chat'
    showManagementPanel('task-workspace')
    rightPanelVisible.value = false
    return
  }
  console.log('[ReactAnalysisView] handleSidebarAction called:', actionId)
  const newTaskMode = actionId === 'restart-session'
    ? (workspace.value === 'platform' ? defaultAgentMode : store.currentMode)
    : null

  if (actionId === 'agent-platform') {
    if (!await confirmResourcePreviewLeave()) return
    hideManagementPanel()
    resetPanelState()
    agentPlatformError.value = ''
    workspace.value = 'platform'
    return
  }

  if (actionId === 'air-quality-forecast') {
    if (!await confirmResourcePreviewLeave()) return
    hideManagementPanel()
    resetPanelState()
    workspace.value = 'forecast'
    return
  }

  workspace.value = 'chat'
  switch (actionId) {
    case 'query-dashboard':
      if (!await confirmResourcePreviewLeave()) return
      store.switchMode('query')
      hideManagementPanel()
      resetPanelState()
      break
    case 'tools-management':
      console.log('[ReactAnalysisView] Showing tools-management panel')
      showManagementPanel('tools-management')
      break
    case 'skills-management':
      console.log('[ReactAnalysisView] Showing skills-management panel')
      showManagementPanel('skills-management')
      break
    case 'knowledge-base':
      console.log('[ReactAnalysisView] Showing knowledge-base panel')
      showManagementPanel('knowledge-base')
      await kbStore.fetchKnowledgeBases()
      break
    case 'fetchers':
      console.log('[ReactAnalysisView] Showing fetchers panel')
      showManagementPanel('fetchers')
      await refreshFetcherStatus()
      break
    case 'scheduled-tasks':
      console.log('[ReactAnalysisView] Showing scheduled-tasks panel')
      showManagementPanel('scheduled-tasks')
      await refreshScheduledTasks()
      break
    case 'session-history':
      console.log('[ReactAnalysisView] Showing session-history panel')
      showManagementPanel('session-history')
      await refreshSessionHistory()
      break
    case 'social-platform':
      console.log('[ReactAnalysisView] Showing social-platform panel')
      showManagementPanel('social-platform')
      break
    case 'file-manager':
      console.log('[ReactAnalysisView] Showing file-manager panel')
      showManagementPanel('file-manager')
      break
    case 'restart-session':
      if (!await confirmResourcePreviewLeave()) return
      console.log('[ReactAnalysisView] Restarting session')
      if (newTaskMode !== store.currentMode) store.switchMode(newTaskMode)
      store.restart()
      hideManagementPanel()
      resetPanelState()
      agentPlatformError.value = ''
      break
  }
  console.log('[ReactAnalysisView] managementPanel value after action:', managementPanel.value)
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

const handleViewKbChunks = async (doc) => {
  if (!doc || !doc.id || doc.id === 'undefined') {
    alert('文档ID无效')
    return
  }

  if (!kbStore.currentKb) {
    alert('请先选择知识库')
    return
  }

  try {
    await kbStore.fetchDocumentChunks(kbStore.currentKb.id, doc.id, doc.targetChunkId || null)
    openDialog('kbChunks')
  } catch (e) {
    alert('获取分块失败: ' + e.message)
  }
}

const viewKbChunksRetry = async () => {
  if (kbStore.currentDoc && kbStore.currentKb) {
    await kbStore.fetchDocumentChunks(kbStore.currentKb.id, kbStore.currentDoc.id)
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

onMounted(async () => {
  setupPanelWatchers()
  setupGlobalListeners()

  // layoutRef 会通过 MainLayout 的 @update:layout-ref 事件自动同步
  // 这里只需要检查是否同步成功
  nextTick(() => {
    console.log('[ReactAnalysisView] layoutRef status:', {
      hasLayoutRef: !!layoutRef.value,
      hasMainLayoutRef: !!mainLayoutRef.value,
      hasMainLayoutLayoutRef: !!mainLayoutRef.value?.layoutRef,
      hasMainLayoutLayoutRefValue: !!mainLayoutRef.value?.layoutRef?.value
    })
  })

  // 初始化日期
  const today = new Date()
  era5HistoricalDate.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  await refreshScheduledTasks()

  if (route.params.id) {
    await queueRouteSessionRestore(route.params.id)
  }
})

onBeforeUnmount(() => {
  cleanupGlobalListeners()
})
</script>

<style scoped>
/* 样式将在后续版本中添加 */
</style>
