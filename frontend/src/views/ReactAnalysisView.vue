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
      :pending-interaction="store.pendingInteraction"
      :interaction-resolving="interactionResolving"
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
      :human-feedback="store.pendingHumanFeedback"
      :human-feedback-submitting="store.isHumanFeedbackSubmitting"
      :human-feedback-error="store.humanFeedbackSubmitError"
      :active-module="workspace === 'platform' ? 'agent-platform' : (workspace === 'forecast' ? 'air-quality-forecast' : (workspace === 'task-center' ? 'task-scheduler-center' : (managementPanel === 'task-workspace' && taskWorkspaceTask ? `task-workspace:${taskWorkspaceTask.task_id}` : activeAssistant)))"
      :task-workspace-entries="taskWorkspaceEntries"
      :task-workspace-task="taskWorkspaceTask"
      :smart-event-command="smartEventCommand"
      :work-order-review-command="workOrderReviewCommand"
      :device-control-command="deviceControlCommand"
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
      @coordinator-submit="handleCoordinatorSubmit"
      @load-session="handleLoadSessionAndClosePanel"
      @start-drag="startDragging"
      @stop-drag="stopDragging"
      @reset-width="resetWidth"
      @tab-change="changeRightTab"
      @board-xml-change="handleBoardXmlChange"
      @board-selection-change="handleBoardSelectionChange"
      @board-snapshot-confirm="handleBoardSnapshotConfirm"
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
      @open-smart-event-task="handleSmartEventTaskOpen"
      @open-smart-event-task-side="handleSmartEventSideTaskOpen"
      @close-smart-event-panel="handleSmartEventPanelClose"
      @close-smart-event-task="handleSmartEventTaskClose"
      @close-work-order-review-panel="handleWorkOrderReviewPanelClose"
      @close-device-control-panel="handleDeviceControlPanelClose"
      @select-review="handleTodoReviewOpen"
      @refresh-session-history="refreshSessionHistory"
      @cleanup-sessions="handleSessionCleanup"
      @restore-session="handleSessionRestoreAndClosePanel"
      @toggle-session-case="handleToggleSessionCase"
      @delete-sessions="deleteSessions"
      @new-web-conversation="startNewWebConversation"
      @toggle-viz-panel="toggleVizPanel"
      @preview-message-attachment="openMessageAttachmentPreview"
      @resolve-interaction="handleInteractionResolve"
      @close-interaction="handleInteractionClose"
      @submit-human-feedback="handleHumanFeedbackSubmit"
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
import { useRoute, useRouter } from 'vue-router'
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
import { resolveCoordinatorMode } from '@/components/coordinator/coordinatorWorkspace.js'
import { extractSmartEventWorkspaceCommand } from '@/services/jiangsuSmartEventWorkspace.js'
import { extractWorkOrderReviewCommand } from '@/services/jiangsuWorkOrderReviewWorkspace.js'
import { extractDeviceControlWorkspaceCommand } from '@/services/jiangsuDeviceControlWorkspace.js'

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
const router = useRouter()
const store = useReactStore()
const defaultAgentMode = resolveProjectDefaultAgentMode(projectConfig, AGENT_MODE_IDS)
// 问数入口按项目启用情况选择模式：江苏使用 jiangsu_query，其他项目使用共享 query 模式。
const queryAgentMode = projectConfig.agentModeIds.includes('jiangsu_query') ? 'jiangsu_query' : 'query'
const kbStore = useKnowledgeBaseStore()
const scheduledTasksStore = useScheduledTasksStore()
const taskWorkspaceTask = ref(null)
const smartEventCommand = ref(null)
const suppressSmartEventCommandOpen = ref(false)
const lastSmartEventCommandKey = ref('')
const workOrderReviewCommand = ref(null)
const lastWorkOrderReviewCommandKey = ref('')
const deviceControlCommand = ref(null)
const lastDeviceControlCommandKey = ref('')
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
const resolvingInteractionId = ref(null)
const interactionResolving = computed(() => (
  Boolean(store.pendingInteraction?.interaction_id)
  && resolvingInteractionId.value === store.pendingInteraction.interaction_id
))

// 对话框状态（从dialogManager获取）
const showKbCreateDialog = computed(() => dialogs.value.kbCreate)
const showKbEditDialog = computed(() => dialogs.value.kbEdit)
const showKbChunksDialog = computed(() => dialogs.value.kbChunks)

const handleInteractionResolve = async (resolution) => {
  const interactionId = store.pendingInteraction?.interaction_id
  if (!interactionId || resolvingInteractionId.value === interactionId) return
  resolvingInteractionId.value = interactionId
  try {
    await store.resolvePendingInteraction(resolution)
  } catch (error) {
    console.error('[agent-interaction] resolution failed:', error)
  } finally {
    if (resolvingInteractionId.value === interactionId) {
      resolvingInteractionId.value = null
    }
  }
}

const handleInteractionClose = () => {
  void handleInteractionResolve({ decision: 'reject', response: null })
}

const handleHumanFeedbackSubmit = async (payload) => {
  try {
    await store.submitHumanFeedback(payload)
  } catch (error) {
    console.error('[human-feedback] submission failed:', error)
  }
}

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

// AI 工作区命令驱动的智能事件页面在右侧面板打开，保留对话窗口供用户继续交互；
// 侧边栏“智能事件中心”入口仍走整页管理面板
const openSmartEventSidePanel = () => {
  workspace.value = 'chat'
  hideManagementPanel()
  activeRightTab.value = 'smart-event'
  rightPanelVisible.value = true
  leftSidebarCollapsed.value = true
  vizWidth.value = Math.max(vizWidth.value, PANEL_SIZES.COLLAPSED_VIZ_WIDTH)
}

const handleSmartEventPanelClose = () => {
  rightPanelVisible.value = false
  leftSidebarCollapsed.value = false
}

const handleSmartEventTaskClose = () => {
  taskWorkspaceTask.value = null
}

// AI 取证命令驱动的故障工单审核页面在右侧面板打开，保留对话供用户继续交互
const openWorkOrderReviewSidePanel = () => {
  workspace.value = 'chat'
  hideManagementPanel()
  activeRightTab.value = 'work-order-review'
  rightPanelVisible.value = true
  leftSidebarCollapsed.value = true
  vizWidth.value = Math.max(vizWidth.value, PANEL_SIZES.COLLAPSED_VIZ_WIDTH)
}

const handleWorkOrderReviewPanelClose = () => {
  rightPanelVisible.value = false
  leftSidebarCollapsed.value = false
}

// AI 工作区命令驱动的远程质控页面在右侧面板打开，保留对话窗口供确认与后续交互
const openDeviceControlSidePanel = () => {
  workspace.value = 'chat'
  hideManagementPanel()
  activeRightTab.value = 'device-control'
  rightPanelVisible.value = true
  leftSidebarCollapsed.value = true
  vizWidth.value = Math.max(vizWidth.value, PANEL_SIZES.COLLAPSED_VIZ_WIDTH)
}

const handleDeviceControlPanelClose = () => {
  rightPanelVisible.value = false
  leftSidebarCollapsed.value = false
}

// 切换会话时重置右侧面板并清空上一个会话遗留的工作区命令与任务，避免面板串到当前会话
watch(currentModeSessionId, () => {
  rightPanelVisible.value = false
  activeRightTab.value = 'files'
  knowledgePanelVisible.value = false
  managementPanel.value = null
  leftSidebarCollapsed.value = false
  taskWorkspaceTask.value = null
  smartEventCommand.value = null
  workOrderReviewCommand.value = null
  deviceControlCommand.value = null
  lastSmartEventCommandKey.value = ''
  lastWorkOrderReviewCommandKey.value = ''
  lastDeviceControlCommandKey.value = ''
})

watch(currentModeMessages, messages => {
  const command = extractDeviceControlWorkspaceCommand(messages)
  if (!command) return
  const commandKey = JSON.stringify(command)
  if (commandKey === lastDeviceControlCommandKey.value) return
  lastDeviceControlCommandKey.value = commandKey
  deviceControlCommand.value = command
  openDeviceControlSidePanel()
}, { deep: true })

watch(currentModeMessages, messages => {
  const command = extractWorkOrderReviewCommand(messages)
  if (!command) return
  const commandKey = JSON.stringify(command)
  if (commandKey === lastWorkOrderReviewCommandKey.value) return
  lastWorkOrderReviewCommandKey.value = commandKey
  workOrderReviewCommand.value = command
  openWorkOrderReviewSidePanel()
}, { deep: true })

watch(currentModeMessages, messages => {
  const command = extractSmartEventWorkspaceCommand(messages)
  if (!command) return
  const commandKey = JSON.stringify(command)
  if (commandKey === lastSmartEventCommandKey.value) return
  lastSmartEventCommandKey.value = commandKey
  smartEventCommand.value = command
  if (suppressSmartEventCommandOpen.value) {
    // 待办卡进入对话回放时保留会话视图，不被历史工作区命令切走
    suppressSmartEventCommandOpen.value = false
    return
  }
  if (['show_event_list', 'filter_event_list', 'open_event_detail', 'focus_evidence', 'compare_events', 'show_operation_history', 'open_task'].includes(command.type)) {
    openSmartEventSidePanel()
  }
}, { deep: true })

const inputDisabled = computed(() => {
  // 执行中允许用户预编辑下一条消息；发送由 InputBox 的 isAnalyzing 保护阻止。
  return false
})

// ========== 事件处理 ==========

const handleRerankerChange = (value) => {
  useReranker.value = value
}

const handleAgentSelect = async (mode) => {
  if (selectingAgentMode.value) return false

  const decision = resolveAgentSelection(mode, store)
  if (decision.action === 'invalid') {
    agentPlatformError.value = '暂不支持该智能体模式'
    return false
  }
  if (!await confirmResourcePreviewLeave()) return false

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
    return true
  } catch (error) {
    agentPlatformError.value = error?.message || '智能体初始化失败，请重试'
    return false
  } finally {
    selectingAgentMode.value = ''
  }
}

const handleCoordinatorSubmit = async (payload) => {
  const query = String(payload?.query || '').trim()
  if (!query) return
  const mode = payload?.mode || resolveCoordinatorMode(
    query,
    projectConfig.coordinator?.routes || [],
    defaultAgentMode
  )
  const opened = await handleAgentSelect(mode)
  if (!opened) return
  await handleSend({ query, agentMode: mode })
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
  }
  return restored
}

const handleTodoReviewOpen = async (review) => {
  let sessionId = null
  if (review?.execution_id && review?.task_id) {
    try {
      const { executions } = await scheduledTasksStore.fetchTaskExecutions(review.task_id, { page: 1, pageSize: 50 })
      sessionId = executions.find(item => item.execution_id === review.execution_id)?.session_id || null
    } catch (error) {
      console.warn('[ReactAnalysisView] 研判执行记录获取失败:', error)
    }
  }
  if (sessionId) {
    suppressSmartEventCommandOpen.value = true
    const restored = await handleSessionRestoreAndClosePanel(sessionId)
    await nextTick()
    if (restored) {
      rightPanelVisible.value = true
      if (!activeRightTab.value) activeRightTab.value = 'files'
      if (suppressSmartEventCommandOpen.value) suppressSmartEventCommandOpen.value = false
      return
    }
    suppressSmartEventCommandOpen.value = false
  }
  // 找不到执行会话时回退：打开智能事件工作区并聚焦该事件
  if (review?.subject_id) {
    const command = { type: 'open_event_detail', event_id: String(review.subject_id) }
    smartEventCommand.value = command
    lastSmartEventCommandKey.value = JSON.stringify(command)
    workspace.value = 'chat'
    showManagementPanel('smart-events')
    rightPanelVisible.value = false
  }
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

const resolveSmartEventTask = async (eventTask) => {
  // AI 传入的可能是事件任务卡片 task_id 或调度任务 ID，两者都尝试解析
  const candidates = [eventTask?.scheduled_task_id, eventTask?.task_id]
    .map(id => String(id || '').trim())
    .filter(Boolean)
  if (!candidates.length) return null
  await scheduledTasksStore.fetchTasks()
  for (const candidate of new Set(candidates)) {
    const task = scheduledTasksStore.tasks.find(item => item.task_id === candidate)
    if (task) return task
  }
  return null
}

// 事件中心（管理面板）里的任务卡片：维持整页任务工作区展示
const handleSmartEventTaskOpen = async (eventTask) => {
  const task = await resolveSmartEventTask(eventTask)
  if (!task) return
  taskWorkspaceTask.value = task
  workspace.value = 'chat'
  showManagementPanel('task-workspace')
  rightPanelVisible.value = false
}

// 右侧面板（AI 命令驱动）里的任务卡片：留在右侧面板，对话窗口不收起
const handleSmartEventSideTaskOpen = async (eventTask) => {
  const task = await resolveSmartEventTask(eventTask)
  if (!task) return
  taskWorkspaceTask.value = task
  openSmartEventSidePanel()
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
    if (route.name !== 'analysis') await router.replace({ name: 'analysis' })
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

  if (actionId === 'task-scheduler-center') {
    if (!await confirmResourcePreviewLeave()) return
    if (route.name !== 'analysis') await router.replace({ name: 'analysis' })
    hideManagementPanel()
    resetPanelState()
    workspace.value = 'task-center'
    return
  }

  if (actionId === 'smart-inspection' || actionId === 'operations-analysis' || actionId === 'device-control' || actionId === 'station-fault-diagnosis') {
    if (!await confirmResourcePreviewLeave()) return
    if (route.name !== 'analysis') await router.replace({ name: 'analysis' })
    hideManagementPanel()
    resetPanelState()
    workspace.value = 'chat'
    const targetMode = {
      'smart-inspection': 'smart_inspection',
      'operations-analysis': 'operations_analysis',
      'device-control': 'device_control',
      'station-fault-diagnosis': 'station_fault_diagnosis'
    }[actionId]
    if (store.currentMode !== targetMode) store.switchMode(targetMode)
    if (actionId === 'device-control') {
      activeRightTab.value = 'device-control'
      rightPanelVisible.value = true
      leftSidebarCollapsed.value = true
    }
    return
  }

  if (actionId === 'work-order-review') {
    if (!await confirmResourcePreviewLeave()) return
    if (route.name !== 'analysis') await router.replace({ name: 'analysis' })
    hideManagementPanel()
    resetPanelState()
    workspace.value = 'chat'
    if (store.currentMode !== 'ops') store.switchMode('ops')
    openWorkOrderReviewSidePanel()
    return
  }

  if (actionId === 'smart-event-external' || actionId === 'smart-event-instrument') {
    if (!await confirmResourcePreviewLeave()) return
    if (route.name !== 'analysis') await router.replace({ name: 'analysis' })
    hideManagementPanel()
    resetPanelState()
    workspace.value = 'chat'
    const targetMode = actionId === 'smart-event-instrument' ? 'smart_event_instrument' : 'smart_event_external'
    if (store.currentMode !== targetMode) store.switchMode(targetMode)
    activeRightTab.value = 'smart-event'
    rightPanelVisible.value = true
    leftSidebarCollapsed.value = true
    return
  }

  workspace.value = 'chat'
  switch (actionId) {
    case 'query-dashboard':
      if (!await confirmResourcePreviewLeave()) return
      store.switchMode(queryAgentMode)
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
    case 'smart-events':
      showManagementPanel('smart-events')
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
